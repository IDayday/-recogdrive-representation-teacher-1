import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from selector import choose
from seeds import scene_seed

class SelectionSemantics(unittest.TestCase):
    def matrix(self,quality):
        x=np.ones(np.array(quality).shape+(7,));x[...,0]=quality;return x
    def test_historical_fixed_method_still_uses_per_draw_failure_gate(self):
        a=self.matrix([[[.2,.9]],[[1.,.1]]])
        i,h=choose(a,'historical_failure_only');self.assertEqual(i.tolist(),[1]);self.assertEqual(h[:,:,0].ravel().tolist(),[.9,1.])
        j,c=choose(a,'teacher_consistent');self.assertEqual(j.tolist(),[0]);self.assertEqual(c[:,:,0].ravel().tolist(),[.2,1.])
    def test_safe_teacher_rejects_new_collision(self):
        a=self.matrix([[[.2,.9,.7]],[[.3,.9,.8]]]);a[0,0,1,1]=0
        i,c=choose(a,'teacher_safe');self.assertEqual(i.tolist(),[2])
    def test_safe_teacher_preserves_base_when_one_noise_worsens(self):
        a=self.matrix([[[.3,.9]],[[1.,.99]]]);i,c=choose(a,'teacher_safe');self.assertEqual(i.tolist(),[0])
    def test_ties_keep_base(self):
        a=self.matrix([[[.5,.5]],[[.6,.6]]]);i,c=choose(a);self.assertEqual(i.tolist(),[0])
    def test_saved_seed_examples(self):
        p=Path(__file__).resolve().parents[1]/'reference/seeds.json';d=json.loads(p.read_text())
        for row in d['records']:self.assertEqual([scene_seed(row['token'],j) for j in d['indices']],row['seeds'])
    def test_rank_does_not_enter_seed(self):
        self.assertEqual(scene_seed('scene',3),scene_seed('scene',3));self.assertNotEqual(scene_seed('scene',3),scene_seed('scene',4))

if __name__=='__main__':unittest.main()
