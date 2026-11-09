#!/usr/bin/env python3
"""Launch the tested Amazing RP compatibility runtime; keep diagnostics private."""
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,sys,threading
from screen import select_screen,fit_game,prepare_primary
h=Path.home();prefix=h/'Games/amazing-rp/ge11-clean-prefix';runner=h/'.local/share/linux-amazing-rp/runners/GE-Proton11-11-Amazing-Compat';state=h/'.local/state/linux-amazing-rp';logs=state/'logs';logs.mkdir(parents=True,exist_ok=True,mode=0o700);logs.chmod(0o700)
lock=(state/'compat-launch.lock').open('a');os.chmod(state/'compat-launch.lock',0o600)
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Amazing уже запущен на рабочем столе 1.')
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name)==os.getpid():continue
 try:
  env=dict(e.split(b'=',1) for e in (p/'environ').read_bytes().split(b'\0') if b'=' in e)
  wp=env.get(b'WINEPREFIX')
  if wp and Path(os.fsdecode(wp)).resolve()==prefix.resolve():raise SystemExit('Тестовый Amazing уже запущен на рабочем столе 1.')
 except (OSError,ValueError):pass
research=state/'autonomous-research'
for path,manifest in [(prefix/'drive_c/windows/syswow64/shell32.dll',research/'shell32-forwarder-compat/build.json'),(runner/'files/lib/wine/dxvk/i386-windows/d3d9.dll',research/'d3d9-vtable-locator/build.json')]:
 expected=json.loads(manifest.read_text())['compat_sha256']
 if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('Файлы совместимости изменились. Требуется проверка: '+str(path))
args=['flatpak','run','--command=env','--env=LANG=ru_RU.UTF-8','--env=LC_ALL=ru_RU.UTF-8',
 '--filesystem='+str(prefix),'--filesystem='+str(h/'Games/amazing-rp/prefix/drive_c/Games/Amazing Games'),
 '--filesystem='+str(h/'.local/share/linux-arizona-rp')+':ro','--filesystem='+str(runner)+':ro',
 '--filesystem='+str(logs),'io.github.Faugus.faugus-launcher','-u','WINEDLLOVERRIDES',
 'WINEDLLOVERRIDES=shell32=n,b','WINEPREFIX='+str(prefix),'PROTONPATH='+str(runner),
 'GAMEID=umu-99998712','UMU_USE_STEAM=1','UMU_CONTAINER_NSENTER=1','PROTON_USE_WOW64=1','MANGOHUD=0',
 'WINEDEBUG=-all,err+all,+relay',str(h/'.local/share/linux-arizona-rp/umu-run')]
screen=select_screen()
args+=sys.argv[1:] or [str(prefix/'drive_c/Games/Amazing Launcher/AmazingUpdater.exe')]
p=logs/'amazing-compat.log'
if p.exists() and p.stat().st_size>16*1024*1024:p.replace(logs/'amazing-compat.previous.log')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600);os.fchmod(fd,0o600)
with os.fdopen(fd,'a') as out:
 out.write('\n--- Amazing compatibility launch (Nov9 configuration) ---\n');out.flush()
 restore=prepare_primary(screen)
 selection=state/'last-screen.json';selection.write_text(json.dumps(screen,indent=2));selection.chmod(0o600)
 stop=threading.Event();threading.Thread(target=fit_game,args=(stop,),daemon=True).start()
 try:
  out.write('Monitor: '+screen['monitor']+' '+str(screen['width'])+'x'+str(screen['height'])+' '+str(screen['refresh_hz'])+' Hz\n');out.flush()
  rc=subprocess.call(args,stdout=out,stderr=subprocess.STDOUT)
 finally:
  stop.set();restore()
 raise SystemExit(rc)
