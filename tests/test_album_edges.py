"""Optional regression against user-supplied album photos (not bundled)."""
import importlib.util, sys
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
if len(sys.argv)!=2:
 raise SystemExit('Usage: python tests/test_album_edges.py PHOTO_FOLDER')
files=sorted(Path(sys.argv[1]).glob('PXL*.jpg'))
assert files, 'No photos found'
for p in files:
 rgb,_=m.load_image(p)
 initial=m.detect(rgb,60)
 counts=[]
 for threshold in (5,15,30,60,90,120,180,250):
  found=m.detect(rgb,threshold);counts.append(len(found))
  for q in found:m.valid_quad(q,rgb.shape[1],rgb.shape[0])
 reset=m.detect(rgb,60)
 assert len(reset)==len(initial) and all(np.array_equal(a,b) for a,b in zip(initial,reset))
 assert max(counts)>0,(p.name,counts)
 print(p.name,'candidate counts:',counts,'reset reproducible')
