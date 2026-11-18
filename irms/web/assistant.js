(function(){
'use strict';
var active=null,plan=null,proposal=null,saved=null,busy=false,serial=0,signature='';
function el(id){return document.getElementById(id);}
function text(id,value){el(id).textContent=value==null?'—':String(value);}
function read(key){try{return JSON.parse(localStorage.getItem('irms301:'+key)||'null');}catch(e){return null;}}
function store(key,value){try{localStorage.setItem('irms301:'+key,JSON.stringify(value));return true;}catch(e){return false;}}
function validPlan(value){return value&&value.version==='3.0.1'&&value.stats&&typeof value.stats==='object'&&Array.isArray(value.warnings)&&Array.isArray(value.recent_laps)&&value.reference&&value.context;}
function request(url,callback){var x=new XMLHttpRequest(),finished=false;function done(error,value){if(finished)return;finished=true;callback(error,value);}x.open('GET',url,true);x.timeout=12000;x.onreadystatechange=function(){if(x.readyState!==4)return;if(x.status!==200){done(new Error('HTTP '+x.status));return;}var value;try{value=JSON.parse(x.responseText);}catch(e){done(e);return;}done(null,value);};x.onerror=function(){done(new Error('network'));};x.ontimeout=function(){done(new Error('timeout'));};x.send();}
function time(ms){if(typeof ms!=='number'||!isFinite(ms))return '—';var minutes=Math.floor(ms/60000),seconds=((ms%60000)/1000).toFixed(3);return minutes+':'+(Number(seconds)<10?'0':'')+seconds;}
function contextKey(value){return JSON.stringify({demo:value.demo,context:value.context});}
function held(){var goal=read('goal:'+active);return goal&&goal.version==='3.0.1'&&goal.focus&&typeof goal.focus.title==='string'&&goal.context===contextKey(plan)&&plan.focus?goal:null;}
function showGoal(){
 proposal=plan.focus;var goal=held(),focus=goal?goal.focus:proposal;
 text('title',focus?focus.title:'Construire une référence personnelle');
 text('observation',focus?focus.observation:'Pas de difficulté récurrente suffisamment établie. Accumule des tours valides et comparables.');
 text('hypothesis',focus?focus.hypothesis:'Aucune cause affirmée sans données suffisantes.');
 text('exercise',focus?focus.exercise:'Conserve tes repères et ne modifie pas plusieurs paramètres à la fois.');
 text('validation',focus?focus.validation:'Compare les mêmes tronçons dans Analyse après quelques tours.');
 var info=goal?'Objectif conservé le '+goal.at+' · référence initiale '+(goal.reference==null?'non définie':goal.reference):'Suggestion actuelle';
 if(goal&&goal.reference!==plan.reference.lap_id)info+=' · Référence changée : le constat conservé est historique, pas une nouvelle mesure.';
 if(focus)info+=' · Confiance du moteur : '+(focus.confidence||'non précisée')+' ; elle ne prouve pas la cause.';
 text('origin',info);el('keep').disabled=!proposal;el('current').disabled=!goal;
}
function showSummary(){
 var value=read('summary:'+active);saved=value&&value.version==='3.0.1'&&validPlan(value.plan)?value:null;
 text('summary',saved?'Instantané du '+saved.at+'\n'+saved.profile+'\nMeilleur valide : '+time(saved.plan.best_ms)+'\nObjectif : '+(saved.focus?saved.focus.title:'non défini'):'Aucun bilan conservé dans ce navigateur pour ce profil.');
 el('export').disabled=!saved;
}
function render(value,cached){
 if(!validPlan(value))return false;plan=value;
 var c=plan.combo||{};text('profile',(c.car||'')+' · '+(c.track||'')+(c.config?' · '+c.config:''));
 text('stats','Meilleur valide : '+time(plan.best_ms)+' · Valides / total : '+(plan.stats.valid||0)+' / '+(plan.stats.total||0));text('pedals',plan.pedal_note);
 el('warnings').textContent='';var notes=plan.warnings.slice();if(cached)notes.unshift('Instantané local non actualisé.');
 notes.forEach(function(note){var p=document.createElement('p');p.textContent=note;el('warnings').appendChild(p);});
 el('laps').textContent='';plan.recent_laps.slice().reverse().forEach(function(lap){var li=document.createElement('li');li.textContent='Tour '+(lap.no||lap.id)+' · '+time(lap.time_ms)+' · '+(lap.created_at||'');el('laps').appendChild(li);});
 showGoal();showSummary();el('save').disabled=!!cached;return true;
}
function fetchPlan(){
 if(!active)return;var id=active,token=serial;
 request('/api/assistant?combo='+encodeURIComponent(id),function(error,value){
 if(token!==serial)return;
 if(error||!validPlan(value)){text('status','Analyse indisponible : dernier affichage conservé.');el('save').disabled=true;signature='';return;}
 store('cache:'+id,value);render(value,false);
 });
}
function selectProfile(id){
 active=String(id);serial++;signature='';plan=null;proposal=null;store('last',active);
 var cache=read('cache:'+active);
 if(!render(cache,true)){text('profile','Chargement du profil…');text('stats','');text('pedals','');text('title','Construire une référence');text('origin','');text('observation','En attente de données.');text('hypothesis','');text('exercise','');text('validation','');el('laps').textContent='';el('warnings').textContent='';el('save').disabled=true;el('keep').disabled=true;el('current').disabled=true;showSummary();}
 fetchPlan();
}
function hasOption(id){return Array.prototype.some.call(el('combo').options,function(option){return option.value===String(id);});}
function loadProfiles(){
 request('/api/combos',function(error,data){
 if(error||!data||!Array.isArray(data.combos)){text('status','PC injoignable : dernier instantané conservé.');return;}
 var select=el('combo');select.textContent='';data.combos.forEach(function(c){var option=document.createElement('option');option.value=String(c.id);option.textContent=c.car+' · '+c.track+(c.config?' · '+c.config:'');select.appendChild(option);});
 var wanted=el('follow').checked&&data.current?data.current:active;
 if(wanted&&hasOption(wanted))select.value=String(wanted);
 if(select.value&&select.value!==active)selectProfile(select.value);
 if(!select.value)text('status','Aucun profil disponible : roule des tours complets puis actualise.');
 });
}
function poll(){
 if(busy)return;busy=true;
 request('/api/status',function(error,state){busy=false;
 if(error||!state){text('status','PC injoignable : affichage conservé, pas de direct.');el('save').disabled=true;signature='';return;}
 text('status',(state.connected?'Jeu connecté':'En attente du jeu')+' · '+(state.message||'')+' · '+new Date().toLocaleTimeString());
 if(el('follow').checked&&state.combo_id&&String(state.combo_id)!==active){if(hasOption(state.combo_id)){el('combo').value=String(state.combo_id);selectProfile(state.combo_id);}else loadProfiles();return;}
 var next=String(active)+':'+state.revision;if(next!==signature){signature=next;fetchPlan();}
 });
}
el('combo').onchange=function(){el('follow').checked=false;selectProfile(this.value);};
el('refresh').onclick=function(){signature='';loadProfiles();poll();};
el('keep').onclick=function(){if(!proposal)return;var value={version:'3.0.1',at:new Date().toISOString(),reference:plan.reference.lap_id,context:contextKey(plan),focus:proposal};if(store('goal:'+active,value))showGoal();else text('status','Stockage du navigateur indisponible : objectif non conservé.');};
el('current').onclick=function(){store('goal:'+active,null);showGoal();};
el('save').onclick=function(){if(!plan||!plan.combo)return;var goal=held(),value={version:'3.0.1',at:new Date().toISOString(),profile:el('profile').textContent,plan:plan,focus:goal?goal.focus:plan.focus};if(store('summary:'+active,value))showSummary();else text('summary','Stockage du navigateur indisponible : bilan non conservé.');};
el('export').onclick=function(){if(!saved)return;var blob=new Blob([JSON.stringify(saved,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='IRMS-bilan-'+active+'.json';document.body.appendChild(a);a.click();document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(url);},30000);};
['keep','current','save','export'].forEach(function(id){el(id).disabled=true;});
var last=read('last');if(typeof last==='string'){active=last;render(read('cache:'+active),true);}
loadProfiles();poll();setInterval(poll,4000);
}());
