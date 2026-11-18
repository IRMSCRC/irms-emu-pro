import copy
import unittest
from irms.assistant_plan import build_plan

class Assistant301Tests(unittest.TestCase):
    def setUp(self):
        self.overview={"combo":{"id":1},"laps":[{"valid":True,"source":"evo","time_ms":90000,"conditions":{"compound":"A"}}],"ref_lap_id":1}
        self.card={"id":"corner-2","title":"T2","corner":2,"pattern":"récurrent","gain_s":.4}
        self.coach={"ready":True,"cards":[self.card]}
    def test_empty(self):self.assertIsNone(build_plan({}, {})["focus"])
    def test_recurrent(self):self.assertEqual(build_plan(self.overview,self.coach)["focus"]["id"],"corner-2")
    def test_isolated(self):
        self.card["pattern"]="ponctuel";self.assertIsNone(build_plan(self.overview,self.coach)["focus"])
    def test_provisional(self):
        self.overview["ref_provisional"]=True;self.assertIsNone(build_plan(self.overview,self.coach)["focus"])
    def test_global_without_valid_reference(self):
        self.overview["ref_provisional"]=True;self.coach["cards"].append({"id":"invalid","corner":None})
        self.assertEqual(build_plan(self.overview,self.coach)["focus"]["id"],"invalid")
    def test_mixed_sources(self):
        self.overview["laps"].append({"source":"demo"});self.assertIsNone(build_plan(self.overview,self.coach)["focus"])
    def test_mixed_tyres(self):
        self.overview["laps"].append({"valid":True,"source":"evo","conditions":{"compound":"B"}})
        self.assertIsNone(build_plan(self.overview,self.coach)["focus"])
    def test_demo(self):
        self.overview["laps"][0]["source"]="demo";self.assertTrue(build_plan(self.overview,self.coach)["demo"])
    def test_ten(self):
        self.overview["laps"]*=15;self.assertEqual(len(build_plan(self.overview,self.coach)["recent_laps"]),10)
    def test_inputs_unchanged(self):
        old=copy.deepcopy((self.overview,self.coach));build_plan(self.overview,self.coach);self.assertEqual(old,(self.overview,self.coach))

if __name__=="__main__":unittest.main()
