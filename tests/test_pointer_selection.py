import importlib.util
from pathlib import Path
import numpy as np
s=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
q=np.array([[100.,100.],[500.,120.],[480.,500.],[120.,480.]])
for angle in (0,90,180,270):
 for zoom in (.5,1,2):
  points=m.rotate_points(q,600,600,angle)*zoom
  for i in range(4):
   for t in (0,.05,.1,.1001,.5,.8999,.9,.95,1):
    p=points[i]+t*(points[(i+1)%4]-points[i])
    expected=('corner',i) if t<=.1 else ('corner',(i+1)%4) if t>=.9 else ('edge',i)
    assert m.pick_frame_target(points,p)==expected,(angle,zoom,i,t)
   d=points[(i+1)%4]-points[i];n=np.array([-d[1],d[0]])/np.linalg.norm(d)
   mid=(points[i]+points[(i+1)%4])/2
   assert m.pick_frame_target(points,mid+n*7)==('edge',i)
   assert m.pick_frame_target(points,mid+n*10)[0]=='corner'
  p=points.mean(axis=0)
  assert m.pick_frame_target(points,p)==('corner',int(np.argmin(np.linalg.norm(points-p,axis=1))))
print('PASS: all edges, 10-percent boundaries, arbitrary click, screen hit tolerance, zoom, four rotations')

for angle in (0,90,180,270):
 points=m.rotate_points(q,600,600,angle)
 for i in range(4):
  center=(points[i]+points[(i+1)%4])/2
  arrow=m.edge_arrow(points,i,center).reshape(2,2)
  delta=arrow[1]-arrow[0];edge=points[(i+1)%4]-points[i]
  assert abs(np.dot(delta,edge))<1e-7
  assert np.isclose(np.linalg.norm(delta),28)
  assert np.allclose(arrow.mean(axis=0),center)
print('PASS: perpendicular centered double arrow with constant screen length in all rotations')
