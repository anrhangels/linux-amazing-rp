"""Select the Xwayland primary output and fullscreen only the Amazing game, without focus changes."""
import ctypes as C,ctypes.util,json,subprocess,time,threading,re,shutil
from pathlib import Path
TITLE=b'AMAZING ONLINE'
def select_screen():
 if not shutil.which('hyprctl'):return select_x11_screen()
 monitors=json.loads(subprocess.check_output(['hyprctl','monitors','-j']))
 active=[m for m in monitors if not m.get('disabled') and m.get('dpmsStatus',True)]
 if not active:raise RuntimeError('No active monitor')
 workspaces=json.loads(subprocess.check_output(['hyprctl','workspaces','-j']))
 target=next((w.get('monitor') for w in workspaces if w.get('id')==1),None)
 m=next((m for m in active if m['name']==target),None) or next((m for m in active if m.get('focused')),active[0])
 w,h=m['width'],m['height']
 if m.get('transform',0)%2:w,h=h,w
 scale=m.get('scale',1) or 1
 return {'monitor':m['name'],'physical_width':w,'physical_height':h,'scale':scale,'width':round(w/scale),'height':round(h/scale),'refresh_hz':m['refreshRate'],'workspace':1}
def fit_game(stop):
 X=C.CDLL(ctypes.util.find_library('X11'));P=C.c_void_p;U=C.c_ulong
 X.XOpenDisplay.argtypes=[C.c_char_p];X.XOpenDisplay.restype=P;d=X.XOpenDisplay(None)
 if not d:return
 X.XDefaultRootWindow.argtypes=[P];X.XDefaultRootWindow.restype=U;root=X.XDefaultRootWindow(d)
 X.XQueryTree.argtypes=[P,U,C.POINTER(U),C.POINTER(U),C.POINTER(C.POINTER(U)),C.POINTER(C.c_uint)]
 X.XFetchName.argtypes=[P,U,C.POINTER(C.c_char_p)];X.XFree.argtypes=[P]
 X.XInternAtom.argtypes=[P,C.c_char_p,C.c_int];X.XInternAtom.restype=U
 X.XSendEvent.argtypes=[P,U,C.c_int,C.c_long,P];X.XFlush.argtypes=[P];X.XCloseDisplay.argtypes=[P]
 class Payload(C.Union):_fields_=[('b',C.c_char*20),('s',C.c_short*10),('l',C.c_long*5)]
 class Client(C.Structure):_fields_=[('type',C.c_int),('serial',U),('send_event',C.c_int),('display',P),('window',U),('message_type',U),('format',C.c_int),('data',Payload)]
 class Event(C.Union):_fields_=[('client',Client),('pad',C.c_long*24)]
 try:
  seen=set()
  while not stop.is_set():
   rr=U();parent=U();children=C.POINTER(U)();count=C.c_uint()
   if X.XQueryTree(d,root,C.byref(rr),C.byref(parent),C.byref(children),C.byref(count)):
    ids=list(children[:count.value]);X.XFree(children);seen.intersection_update(ids)
    for win in ids:
     if win in seen:continue
     name=C.c_char_p()
     title=b''
     if X.XFetchName(d,win,C.byref(name)) and name.value:
      title=name.value;X.XFree(C.cast(name,P))
     if not title:
      X.XGetWindowProperty.argtypes=[P,U,U,C.c_long,C.c_long,C.c_int,U,C.POINTER(U),C.POINTER(C.c_int),C.POINTER(U),C.POINTER(U),C.POINTER(P)]
      typ=U();fmt=C.c_int();n=U();left=U();data=P()
      if X.XGetWindowProperty(d,win,X.XInternAtom(d,b'_NET_WM_NAME',0),0,256,0,0,C.byref(typ),C.byref(fmt),C.byref(n),C.byref(left),C.byref(data))==0 and data:
       if fmt.value==8:title=C.string_at(data,n.value)
       X.XFree(data)
     if title != TITLE:continue
     class Hint(C.Structure):_fields_=[('res_name',P),('res_class',P)]
     X.XGetClassHint.argtypes=[P,U,C.POINTER(Hint)];hint=Hint()
     if not X.XGetClassHint(d,win,C.byref(hint)):continue
     klass=C.string_at(hint.res_class) if hint.res_class else b''
     if hint.res_name:X.XFree(hint.res_name)
     if hint.res_class:X.XFree(hint.res_class)
     if klass.lower()!=b'steam_app_99998712':continue
     event=Event();event.client.type=33;event.client.display=d;event.client.window=win;event.client.message_type=X.XInternAtom(d,b'_NET_WM_STATE',0);event.client.format=32
     event.client.data.l[0]=1;event.client.data.l[1]=X.XInternAtom(d,b'_NET_WM_STATE_FULLSCREEN',0);event.client.data.l[3]=2
     X.XSendEvent(d,root,0,(1<<19)|(1<<20),C.byref(event));X.XFlush(d);seen.add(win)
   stop.wait(1)
 finally:X.XCloseDisplay(d)

def x11_outputs():
 result=subprocess.run(['xrandr','--query'],capture_output=True,text=True,check=True)
 connected=[];primary=None
 for line in result.stdout.splitlines():
  m=re.match(r'^(\S+) connected(?: (primary))?(?: |$)',line)
  if m:
   connected.append(m.group(1))
   if m.group(2):primary=m.group(1)
 return connected,primary

def prepare_primary(screen):
 connected,previous=x11_outputs();target=screen['monitor']
 if target not in connected:raise RuntimeError('Monitor is not available in Xwayland: '+target)
 if previous!=target:
  subprocess.run(['xrandr','--output',target,'--primary'],capture_output=True,check=True)
  if x11_outputs()[1]!=target:raise RuntimeError('Xwayland did not accept primary monitor selection')
 screen['x11_previous_primary']=previous;screen['x11_primary']=target
 def restore():
  connected,current=x11_outputs()
  # Preserve any primary-monitor change made explicitly by the user during the session.
  if current!=target or previous==target:return
  if previous in connected:subprocess.run(['xrandr','--output',previous,'--primary'],capture_output=True)
  elif target in connected:subprocess.run(['xrandr','--output',target,'--noprimary'],capture_output=True)
 return restore

def select_x11_screen():
 output=subprocess.check_output(['xrandr','--query'],text=True,stderr=subprocess.DEVNULL)
 screens=[];current=None
 for line in output.splitlines():
  m=re.match(r'^(\S+) connected(?: (primary))? (\d+)x(\d+)([+-]\d+)([+-]\d+)',line)
  if m:
   current={'monitor':m[1],'physical_width':int(m[3]),'physical_height':int(m[4]),'width':int(m[3]),'height':int(m[4]),'scale':1,'refresh_hz':60,'workspace':None,'primary':bool(m[2])};screens.append(current)
  elif line and not line[0].isspace():current=None
  elif current:
   rate=re.search(r'([0-9.]+)\*',line)
   if rate:current['refresh_hz']=float(rate[1])
 if not screens:raise RuntimeError('No active X11 display')
 return next((m for m in screens if m['primary']),screens[0])
