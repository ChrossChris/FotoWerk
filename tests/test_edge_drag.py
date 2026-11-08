import importlib.util
from pathlib import Path
import numpy as np
import cv2
spec=importlib.util.spec_from_file_location('app',Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
q=np.float64([[20,20],[180,20],[170,180],[30,180]])
lines=[np.float64([[15,50],[185,50]]),np.float64([[15,80],[185,80]])]
a,snapped=m.move_quad_edge(q,0,np.array([0,27]),lines,8,200,200)
assert snapped and np.allclose(a[:2,1],50) and np.array_equal(a[2:],q[2:])
b,snapped=m.move_quad_edge(q,0,np.array([0,57]),lines,8,200,200)
assert snapped and np.allclose(b[:2,1],80)
c,snapped=m.move_quad_edge(q,0,np.array([0,27]),lines,0,200,200)
assert not snapped and np.allclose(c[:2,1],47)
# Reject crossing/inverted/out-of-bounds movements.
d,_=m.move_quad_edge(q,0,np.array([0,300]),[],0,200,200)
assert np.array_equal(d,q)
# A gapped rectangular border still supplies individual straight-line candidates.
im=np.zeros((400,500,3),np.uint8)
for p1,p2 in [((70,60),(220,60)),((245,60),(430,60)),((70,340),(430,340)),((70,60),(70,340)),((430,60),(430,340))]:
 cv2.line(im,p1,p2,(180,180,180),2)
found=m.detected_lines(im,60)
assert len(found)>=4
frames=m.line_frames(im,60)
assert frames
# Original-coordinate line relocation remains valid under all display rotations.
for rotation in (0,90,180,270):
 moved=m.rotate_points(np.array([[100.,20.],[100.,47.]]),200,200,rotation)
 back=m.rotate_points(moved,200,200,-rotation)
 out,hit=m.move_quad_edge(q,0,back[1]-back[0],lines,8,200,200)
 assert hit and np.allclose(out,a)
print('PASS: whole-edge movement, nearest line, next line, snap disabled, perspective intersections, invalid moves, gapped lines, all rotations')
