import importlib.util, tempfile, queue, threading, sys, types
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageTk
spec=importlib.util.spec_from_file_location('m',str(Path(__file__).resolve().parents[1]/'fotos_beschneiden_v2.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
y,x=np.mgrid[:160,:200]
rgb=np.stack((60+x//2,80+y//2,30+x//3),axis=-1).astype('uint8')
rgb[50:80,50:100] = 190
rgb[30,30] = 255
original=rgb.copy()
for mode in m.FILTERS:
 out=m.optimize_image(rgb,dict(filter=mode))
 assert out.shape==rgb.shape and out.dtype==np.uint8
 assert np.array_equal(m.optimize_image(rgb,dict(filter=mode,filter_strength=0)),rgb)
 assert np.array_equal(rgb,original)
 if mode!='none':assert not np.array_equal(out,rgb),mode
sep=m.optimize_image(rgb,{'filter':'sepia'});assert np.all(sep[:,:,0]>=sep[:,:,1]) and np.all(sep[:,:,1]>=sep[:,:,2])
for mode in ('gray','paper','bw'):
 a=m.optimize_image(rgb,{'filter':mode});assert np.array_equal(a[:,:,0],a[:,:,1]) and np.array_equal(a[:,:,1],a[:,:,2])
assert set(np.unique(m.optimize_image(rgb,{'filter':'bw'}))) <= {0,255}
# Shaded paper with dark text: brighter background with preserved dark text.
paper=np.repeat(np.tile(np.linspace(100,210,200,dtype='uint8'),(160,1))[:,:,None],3,axis=2)
paper[60:66,20:180]=20
p=m.optimize_image(paper,{'filter':'paper'})
assert p[20,50,0]>paper[20,50,0]+70 and p[62,50,0]<80
# Exercise real review callbacks using a headless widget adapter.
widgets=[];canvases=[];roots=[]
class Var:
 def __init__(self,value=None):self.value=value;self.traces=[]
 def get(self):return self.value
 def set(self,v):self.value=v;[f() for f in self.traces]
 def trace_add(self,k,f):self.traces.append(f)
class Widget:
 def __init__(self,*a,**kw):self.kw=kw;self.bindings={};widgets.append(self)
 def pack(self,*a,**kw):pass
 def grid(self,*a,**kw):pass
 def columnconfigure(self,*a,**kw):pass
 def configure(self,**kw):self.kw.update(kw)
 def bind(self,k,f,**kw):self.bindings[k]=f
class Canvas(Widget):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);canvases.append(self)
 def winfo_width(self):return self.kw['width']
 def winfo_height(self):return self.kw['height']
 def create_image(self,*a,**kw):
  if not hasattr(self,'images'):self.images=[]
  self.images.append((a,kw));return 1
 def itemconfigure(self,i,**kw):self.picture=kw['image']
 def coords(self,*a):pass
 def delete(self,*a):pass
 def create_polygon(self,*a,**kw):pass
 def create_oval(self,*a,**kw):pass
 def create_text(self,*a,**kw):pass
 def create_line(self,*a,**kw):
  if not hasattr(self,'lines'):self.lines=[]
  self.lines.append((a,kw))
 def create_rectangle(self,*a,**kw):pass
 def focus_force(self):pass
class Root(Widget):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.jobs={};self.serial=0;roots.append(self)
 def title(self,*a):pass
 def minsize(self,*a):pass
 def winfo_screenwidth(self):return 1200
 def winfo_screenheight(self):return 1000
 def protocol(self,*a):pass
 def update_idletasks(self):pass
 def geometry(self,*a):return '800x800'
 def state(self,*a):return 'normal'
 def after(self,t,fn):self.serial+=1;self.jobs[self.serial]=fn;return self.serial
 def after_cancel(self,j):self.jobs.pop(j,None)
 def winfo_viewable(self):return True
 def lift(self):pass
 def destroy(self):pass
 def flush(self):
  jobs=list(self.jobs.values());self.jobs.clear()
  for f in jobs:f()
 def mainloop(self):
  canvas=canvases[-1]
  combo=next(w for w in widgets if 'values' in w.kw)
  compare=next(w for w in widgets if w.kw.get('text')=='Zeige Original')
  reset=next(w for w in widgets if w.kw.get('text')=='Default-Werte')
  for mode, (label,_) in m.FILTERS.items():
   combo.kw['textvariable'].set(label);self.flush()
   assert np.array_equal(np.asarray(canvas.picture),m.optimize_image(rgb,settings['adjustments'])),mode
  combo.kw['textvariable'].set(m.FILTERS['sepia'][0]);self.flush()
  compare.bindings['<ButtonPress-1>']()
  assert np.array_equal(np.asarray(canvas.picture),rgb)
  assert settings['adjustments']['filter']=='sepia'
  # Moving off the button does not end the hold; root release does.
  assert '<Leave>' not in compare.bindings or compare.bindings['<Leave>'].__name__ == 'hide'
  self.bindings['<ButtonRelease-1>']()
  assert np.array_equal(np.asarray(canvas.picture),m.optimize_image(rgb,settings['adjustments']))
  reset.kw['command']();self.flush()
  assert settings['adjustments']['filter']=='none' and settings['adjustments']['gamma']==1
  assert np.array_equal(np.asarray(canvas.picture),rgb)
  assert not any(w.kw.get('text') in ('Manuellen Schwellwert verwenden','Rahmen neu erkennen') for w in widgets)
  assert len({w.kw['length'] for w in widgets if 'resolution' in w.kw})==1
  slider=next(w for w in widgets if w.kw.get('from_')==5)
  expected=np.float32([[10,10],[180,10],[180,140],[10,140]])
  with patch.object(m,'detect',return_value=[expected]) as detection:
   slider.kw['variable'].set(80);slider.kw['variable'].set(90)
   assert detection.call_count==0
   self.flush();assert detection.call_count==1 and detection.call_args.args[1]==90
  assert settings['edges']==dict(enabled=True,threshold=90)
  with patch.object(m,'detect',return_value=[]):
   slider.kw['variable'].set(100);self.flush()
  with patch.object(m,'detect',return_value=[]):
   next(w for w in widgets if w.kw.get('text')=='Schwelle zurücksetzen').kw['command']();self.flush()
  assert settings['edges']['threshold']==60
  with patch.object(m,'detect',return_value=[]) as detection:
   next(w for w in widgets if w.kw.get('text')=='Schwelle zurücksetzen').kw['command']()
   assert detection.call_count==1
  # Exercise actual edge-drag callbacks with a known nearby detected line.
  with patch.object(m,'detect',return_value=[]),patch.object(m,'detected_lines',return_value=[np.float64([[20,40],[180,40]])]):
   next(w for w in widgets if w.kw.get('text')=='Schwelle zurücksetzen').kw['command']()
  assert not any(w.kw.get('text') in ('Ganze Kanten verschieben','Erkannte Linien anzeigen') for w in widgets)
  canvas.lines=[];canvas.images=[]
  canvas.bindings['<Motion>'](types.SimpleNamespace(x=100,y=16))
  assert any(kw.get('tags')=='crosshair' for _,kw in canvas.images)
  canvas.lines=[];canvas.images=[]
  canvas.bindings['<Motion>'](types.SimpleNamespace(x=25,y=16))
  assert not any(kw.get('tags')=='crosshair' for _,kw in canvas.images)
  canvas.bindings['<Button-1>'](types.SimpleNamespace(x=100,y=16))
  canvas.bindings['<B1-Motion>'](types.SimpleNamespace(x=100,y=37))
  canvas.bindings['<ButtonRelease-1>'](types.SimpleNamespace(x=100,y=37))
  next(w for w in widgets if w.kw.get('text')=='Speichern & weiter').kw['command']()
settings={'adjustments':dict(m.ADJUSTMENT_DEFAULTS)}
fake=types.ModuleType('tkinter')
for k,v in dict(Tk=Root,Toplevel=Root,Canvas=Canvas,Frame=Widget,LabelFrame=Widget,Label=Widget,Button=Widget,Checkbutton=Widget,Scale=Widget,StringVar=Var,DoubleVar=Var,BooleanVar=Var,TclError=RuntimeError).items():setattr(fake,k,v)
fake.ttk=types.SimpleNamespace(Combobox=Widget);fake.messagebox=types.SimpleNamespace(showerror=lambda *a:(_ for _ in ()).throw(AssertionError(a)))
with patch.dict(sys.modules,{'tkinter':fake}),patch.object(ImageTk,'PhotoImage',lambda im:im.copy()),patch.object(m,'apply_window_icon',lambda r:None):
 result=m.review(rgb,[np.float32([[0,0],[199,0],[199,159],[0,159]])],'test',output_settings=settings)
 assert result is not None
 assert np.array_equal(result[0],np.float32([[20,40],[180,40],[180,144],[20,144]]))
print('PASS: all filters, strength zero, source untouched, scan normalization, real review selection/preview/original comparison/reset/save callbacks')
