import unittest
from types import SimpleNamespace
import numpy as np
from pcb_landmarks.parsa_tiling import tile_inference, non_max_suppression


class TilingTests(unittest.TestCase):
    def test_native_tile_offsets_edges_and_nms(self):
        calls = []
        class Tensor:
            def cpu(self): return self
            def numpy(self): return np.array([[10, 20, 30, 40, .9, 0]])
        class Model:
            def predict(self, **options):
                calls.append(options['source'].shape)
                return [SimpleNamespace(boxes=SimpleNamespace(data=Tensor()))]
        boxes = tile_inference(Model(), np.zeros((1300, 1500, 3), np.uint8), tile_size=1024)
        self.assertEqual(calls, [(1024, 1024, 3)]*4)
        self.assertEqual({tuple(b[:4]) for b in boxes},
                         {(10,20,30,40),(486,20,506,40),(10,296,30,316),(486,296,506,316)})
        self.assertEqual(len(non_max_suppression([[1,1,20,20,.9,0],[2,2,20,20,.8,0]])), 1)
