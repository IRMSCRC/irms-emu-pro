"""Analyse des tours : re-echantillonnage par distance, virages, ecarts.

Tout est calcule a partir des tours du pilote avec la voiture choisie :
aucune base de donnees de circuits ou de voitures n'est necessaire, et les
reperes s'adaptent automatiquement a chaque voiture.
"""
import math

RS_CHANNELS = ("t", "speed", "gas", "brake", "steer", "gear", "rpm", "glat", "x", "z")
BRAKE_ON = 0.08
GAS_ON = 0.20
GAS_FULL = 0.95


def grid_size(length):
    return int(min(3000, max(300, round(length / 2.0))))


def resample(samples, length, lap_seconds, n=None):
    """Projette un tour sur une grille de distance reguliere (n + 1 points)."""
    n = n or grid_size(length)
    step = length / float(n)
    src_d = samples["d"]
    keep = []
    last = -1.0
    for i, d in enumerate(src_d):
        if d > last + 1e-3:
            keep.append(i)
            last = d
    out = {"n": n, "step": step, "length": length}
    if not keep:
        for name in RS_CHANNELS:
            out[name] = [0.0] * (n + 1)
        return out
    ds = [0.0] + [src_d[i] for i in keep] + [max(length, src_d[keep[-1]] + 1e-3)]
    for name in RS_CHANNELS:
        col = samples[name]
        vals = [col[keep[0]]] + [col[i] for i in keep] + [col[keep[-1]]]
        if name == "t":
            vals[0] = 0.0
            vals[-1] = max(lap_seconds, vals[-2])
        res = [0.0] * (n + 1)
        j = 0
        top = len(ds) - 2
        nearest = name == "gear"
        for k in range(n + 1):
            d = k * step
            while j < top and ds[j + 1] < d:
                j += 1
            span = ds[j + 1] - ds[j]
            f = (d - ds[j]) / span if span > 0 else 0.0
            f = 0.0 if f < 0 else 1.0 if f > 1 else f
            if nearest:
                res[k] = vals[j + 1] if f > 0.5 else vals[j]
            else:
                res[k] = vals[j] + f * (vals[j + 1] - vals[j])
        out[name] = res
    return out


def smooth_cyclic(values, half):
    if half <= 0:
        return list(values)
    n = len(values)
    window = 2 * half + 1
    total = 0.0
    for i in range(-half, half + 1):
        total += values[i % n]
    out = [0.0] * n
    for i in range(n):
        out[i] = total / window
        total += values[(i + half + 1) % n] - values[(i - half) % n]
    return out


def geometry(rs, has_pos=True):
    """Courbure signee (positive = virage a droite) et orientation du plan."""
    n, step = rs["n"], rs["step"]
    steer = rs["steer"][:n]
    speed = rs["speed"]
    result = {"has_pos": False, "flip": False, "kappa": None}
    if has_pos:
        xs = smooth_cyclic(rs["x"][:n], max(1, int(round(6.0 / step))))
        zs = smooth_cyclic(rs["z"][:n], max(1, int(round(6.0 / step))))
        spread = (max(xs) - min(xs)) + (max(zs) - min(zs))
        if spread > 50.0:
            k = max(1, int(round(5.0 / step)))
            heading = [math.atan2(zs[(i + k) % n] - zs[i - k], xs[(i + k) % n] - xs[i - k]) for i in range(n)]
            kappa = [0.0] * n
            for i in range(n):
                d = heading[(i + 1) % n] - heading[i - 1]
                d = (d + math.pi) % (2 * math.pi) - math.pi
                kappa[i] = d / (2.0 * step)
            kappa = smooth_cyclic(kappa, max(1, int(round(8.0 / step))))
            # Le plan est-il vu en miroir ? On compare la courbure au volant.
            corr = sum(kappa[i] * steer[i] for i in range(n) if speed[i] > 30.0)
            flip = corr < 0
            if flip:
                kappa = [-v for v in kappa]
            result.update(has_pos=True, flip=flip, kappa=kappa)
            return result
    # Repli sans position : le volant sert d'indicateur de courbure.
    result["steer_smooth"] = smooth_cyclic(steer, max(1, int(round(8.0 / step))))
    return result


def _runs(flags):
    runs = []
    start = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, len(flags) - 1])
    return runs


def detect_corners(rs, geo):
    """Repere les virages sur le tour de reference."""
    n, step = rs["n"], rs["step"]
    speed = rs["speed"]
    if geo["has_pos"]:
        kappa = geo["kappa"]
        sign = [0] * n
        for i in range(n):
            k = abs(kappa[i])
            v = speed[i] / 3.6
            if k > 1.0 / 250.0 or (k > 1.0 / 700.0 and v * v * k > 6.0):
                sign[i] = 1 if kappa[i] > 0 else -1
    else:
        sm = geo["steer_smooth"]
        ranked = sorted(abs(v) for v in sm)
        threshold = max(0.03, 0.25 * ranked[int(0.95 * (n - 1))])
        sign = [(1 if v > 0 else -1) if abs(v) > threshold else 0 for v in sm]
    regions = []
    for direction in (1, -1):
        for a, b in _runs([s == direction for s in sign]):
            regions.append([a, b, direction])
    regions.sort()
    merged = []
    for region in regions:
        if merged and merged[-1][2] == region[2] and (region[0] - merged[-1][1]) * step < 30.0 \
                and not any(sign[i] == -region[2] for i in range(merged[-1][1], region[0])):
            merged[-1][1] = region[1]
        else:
            merged.append(region)
    corners = []
    for a, b, direction in merged:
        if (b - a) * step < 15.0:
            continue
        angle = None
        if geo["has_pos"]:
            angle = abs(sum(geo["kappa"][a:b + 1]) * step) * 180.0 / math.pi
            if angle < 15.0:
                continue
        apex = min(range(a, b + 1), key=lambda i: speed[i])
        vmin = speed[apex]
        edge = max(1, (b - a) // 10)
        if geo["has_pos"] and (apex - a < edge or b - apex < edge):
            # virage pris sans ralentir : la corde est le point le plus serre
            apex = max(range(a, b + 1), key=lambda i: abs(geo["kappa"][i]))
        if angle is not None and angle >= 120.0 and vmin < 110.0:
            kind = "épingle"
        elif vmin >= 170.0:
            kind = "rapide"
        elif vmin >= 110.0:
            kind = "moyen"
        else:
            kind = "lent"
        corners.append({"start": a, "end": b, "apex": apex, "dir": "droite" if direction > 0 else "gauche",
                        "angle": angle, "kind": kind})
    for index, corner in enumerate(corners):
        corner["index"] = index
        corner["name"] = "T%d" % (index + 1)
    # limites de troncons : un troncon par virage, freinage compris
    for index, corner in enumerate(corners):
        lo = corners[index - 1]["end"] + 1 if index else 0
        m = corner_metrics(rs, lo, corner["end"], corner)
        corner["ref_brake_on"] = m["brake_on"]
    for index, corner in enumerate(corners):
        if index == 0:
            corner["seg_start"] = 0
        else:
            prev = corners[index - 1]
            mid = (prev["end"] + corner["start"]) // 2
            bound = mid
            if corner["ref_brake_on"] is not None:
                bound = min(mid, corner["ref_brake_on"] - int(round(40.0 / step)))
            bound = max(prev["end"] + 2, min(corner["start"] - 2, bound))
            corner["seg_start"] = bound
            prev["seg_end"] = bound
    if corners:
        corners[-1]["seg_end"] = n
    return corners


def corner_metrics(rs, i0, i1, corner):
    """Mesures de pilotage d'un tour dans un troncon [i0, i1]."""
    step = rs["step"]
    speed, gas, brake, steer, t, gear = rs["speed"], rs["gas"], rs["brake"], rs["steer"], rs["t"], rs["gear"]
    pad = int(round(40.0 / step))
    lo = max(i0, corner["start"] - pad)
    hi = min(i1, corner["end"] + pad)
    i_min = min(range(lo, hi + 1), key=lambda i: speed[i])
    m = {"min_speed": speed[i_min], "min_at": i_min, "min_gear": int(round(gear[i_min])),
         "time": t[i1] - t[i0], "brake_on": None, "brake_off": None, "brake_peak": 0.0,
         "lift_on": None, "gas_on": None, "full_on": None, "lifts": 0, "trail": 0.0}
    # freinage principal avant la corde
    limit = min(i1, i_min + int(round(10.0 / step)))
    best = None
    start = None
    area = 0.0
    for i in range(i0, limit + 2):
        on = i <= limit and brake[i] > BRAKE_ON
        if on:
            if start is None:
                start, area = i, 0.0
            area += brake[i]
        elif start is not None:
            if best is None or area > best[2]:
                best = (start, i - 1, area)
            start = None
    if best and best[2] * step > 1.5:
        m["brake_on"], m["brake_off"] = best[0], best[1]
        m["brake_peak"] = max(brake[best[0]:best[1] + 1])
        m["entry_speed"] = speed[best[0]]
        # freinage degressif : distance freinee une fois le volant braque
        peak_steer = max(abs(steer[i]) for i in range(corner["start"], corner["end"] + 1)) or 1.0
        for i in range(best[0], best[1] + 1):
            if abs(steer[i]) > 0.3 * peak_steer:
                m["trail"] = (best[1] - i) * step
                break
    else:
        m["entry_speed"] = speed[max(i0, corner["start"] - int(round(20.0 / step)))]
        seen_full = False
        for i in range(i0, i_min + 1):
            if gas[i] >= 0.9:
                seen_full = True
            elif seen_full and gas[i] < 0.5:
                m["lift_on"] = i
                break
    # reprise des gaz
    hold = max(1, int(round(8.0 / step)))
    if m["brake_off"] is not None:
        begin = m["brake_off"]
    else:
        begin = max(i0, i_min - int(round(15.0 / step)))
    for i in range(begin, i1 + 1):
        if gas[i] > GAS_ON and all(gas[j] > GAS_ON for j in range(i, min(i1, i + hold) + 1)):
            m["gas_on"] = i
            break
    if m["gas_on"] is not None:
        for i in range(m["gas_on"], i1 + 1):
            if gas[i] >= GAS_FULL:
                m["full_on"] = i
                break
        peak = gas[m["gas_on"]]
        for i in range(m["gas_on"], i1 + 1):
            if gas[i] > peak:
                peak = gas[i]
            elif peak > 0.5 and gas[i] < peak - 0.3 and brake[i] < BRAKE_ON:
                # un lever de pied suivi d'un freinage est l'approche du virage suivant
                ahead = min(i1, i + int(round(40.0 / step)))
                if max(brake[i:ahead + 1]) < BRAKE_ON:
                    m["lifts"] += 1
                peak = gas[i]
    coast = 0.0
    overlap = 0.0
    for i in range(i0, i1):
        dt = t[i + 1] - t[i]
        if gas[i] < 0.05 and brake[i] < 0.05:
            coast += dt
        elif gas[i] > 0.1 and brake[i] > 0.1:
            overlap += dt
    m["coast"] = coast
    m["overlap"] = overlap
    m["exit_speed"] = speed[min(i1, corner["end"] + int(round(60.0 / step)))]
    m["seg_entry_speed"] = speed[i0]
    return m


def lap_metrics(rs, corners):
    return [corner_metrics(rs, c["seg_start"], c["seg_end"], c) for c in corners]


def delta(rs, ref):
    t, rt = rs["t"], ref["t"]
    return [t[i] - rt[i] for i in range(len(rt))]


def sectors(rs, count=3):
    n = rs["n"]
    bounds = [int(round(n * k / float(count))) for k in range(count + 1)]
    return [rs["t"][bounds[k + 1]] - rs["t"][bounds[k]] for k in range(count)]


def percentile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = min(len(ordered) - 1, lo + 1)
    return ordered[lo] + (pos - lo) * (ordered[hi] - ordered[lo])


def mean(values):
    return sum(values) / len(values) if values else 0.0


def stdev(values):
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def car_profile(rs):
    """Ce que la voiture a montre sur ce tour : sert a situer ses limites."""
    n, step = rs["n"], rs["step"]
    speed = rs["speed"]
    acc = []
    for i in range(n):
        v0, v1 = speed[i] / 3.6, speed[i + 1] / 3.6
        acc.append((v1 * v1 - v0 * v0) / (2.0 * step) / 9.81)
    acc = smooth_cyclic(acc, max(1, int(round(10.0 / step))))
    gears = [int(round(g)) for g in rs["gear"]]
    return {
        "top_speed": max(speed),
        "min_speed": min(speed),
        "brake_g": max(0.0, -percentile(acc, 0.02)),
        "accel_g": max(0.0, percentile(acc, 0.98)),
        "lat_g": percentile([abs(v) for v in rs["glat"]], 0.98),
        "max_gear": max(gears),
        "max_rpm": max(rs["rpm"]),
        "full_throttle": 100.0 * sum(1 for g in rs["gas"] if g >= GAS_FULL) / float(n + 1),
        "braking": 100.0 * sum(1 for b in rs["brake"] if b > BRAKE_ON) / float(n + 1),
    }
