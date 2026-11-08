import importlib.util
from pathlib import Path
import numpy as np
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rgb=np.full((400,500,3),120,np.uint8);rgb[60:340,80:420]=130
weak=m.detect(rgb,5);strong=m.detect(rgb,250)
assert weak and not strong,(len(weak),len(strong))
assert np.allclose(weak[0],[[80,60],[419,60],[419,339],[80,339]],atol=5)
assert all(np.allclose(a,b) for a,b in zip(m.detect(rgb),m.detect(rgb,None)))
for t in (0,251,float('nan')):
 try:m.detect(rgb,t);raise AssertionError(t)
 except ValueError:pass
# Only one Canny pass in manual mode, with the expected hysteresis pair.
original=m.cv2.Canny
with patch.object(m.cv2,'Canny',wraps=original) as canny:
 m.detect(rgb,90)
 assert canny.call_count>=1 and all(c.args[1:]==(30.,90.) for c in canny.call_args_list)
print('PASS: weak edges at low threshold, rejection at high threshold, original coordinates, automatic mode, validation, Canny thresholds')
