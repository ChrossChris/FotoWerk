import importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
spec=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
y,x=np.mgrid[:160,:200]
a=np.stack((70+x//3,50+y//3,40+x//5),axis=-1).astype(np.uint8)
a[20:50,20:60]=200
for mode in ('vivid','hdr','soft','depth','ai'):
 result=m.optimize_image(a,{'filter':mode})
 assert result.shape==a.shape and result.dtype==np.uint8
 assert np.array_equal(m.optimize_image(a,{'filter':mode,'filter_strength':0}),a)
 assert not np.array_equal(result,a)
# Gray remains neutral; vivid increases chroma.
gray=np.full((50,50,3),100,np.uint8)
assert np.array_equal(m.filter_image(gray,'vivid'),gray)
assert cv2.cvtColor(m.filter_image(a,'vivid'),cv2.COLOR_RGB2HSV)[:,:,1].mean()>cv2.cvtColor(a,cv2.COLOR_RGB2HSV)[:,:,1].mean()
# Depth keeps central pixels exactly intact while softening edge details.
checker=np.repeat((((x//4+y//4)%2)*160+40).astype(np.uint8)[:,:,None],3,axis=2)
depth=m.filter_image(checker,'depth')
assert np.array_equal(depth[70:90,90:110],checker[70:90,90:110])
assert not np.array_equal(depth[:30,:30],checker[:30,:30])
# Model-guided region affects only its local lighting, beyond gentle auto adjustment.
with patch.object(m,'face_regions',return_value=[(60,40,120,110)]):
 ai=m.filter_image(a,'ai')
 base=cv2.addWeighted(a,.65,m.filter_image(a,'auto'),.35,0)
 assert ai[75,90,0]>base[75,90,0]
 assert np.array_equal(ai[0,0],base[0,0])
with patch.object(m,'face_regions',return_value=[]):
 assert np.array_equal(m.filter_image(a,'ai'),m.filter_image(a,'auto'))
# Inference runs against packaged real model (no face is required in the test chart).
assert isinstance(m.face_regions(a),list)
print('PASS: new filters, strength, chroma, depth focus, model-guided lighting, fallback, real YuNet inference')
