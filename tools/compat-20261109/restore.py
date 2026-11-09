#!/usr/bin/env python3
"""Restore only the known test-prefix DLLs, debug settings and saved launcher."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time
if sys.argv[1:]!=['--restore-original']:raise SystemExit('Usage: restore.py --restore-original (stops the Amazing test session)')
h=Path.home();root=Path(__file__).parent;settings=h/'.local/share/linux-amazing-rp/settings.json';config=json.loads(settings.read_text()) if settings.is_file() else {};prefix=Path(config.get('prefix',h/'Games/amazing-rp/ge11-clean-prefix'));research=Path(config.get('metadata',h/'.local/state/linux-amazing-rp/autonomous-research'))
subprocess.run([sys.executable,str(root/'stop-test-prefix.py'),str(prefix)],check=True);time.sleep(2)
for folder,dll in [('shell32-forwarder-compat','shell32.dll'),('d3d9-vtable-locator','d3d9.dll')]:
 d=research/folder;meta=json.loads((d/'build.json').read_text());backup=json.loads((d/'prefix-backup.json').read_text());p=Path(backup['path'])
 if p.parent!=prefix/'drive_c/windows/syswow64' or p.name!=dll:raise SystemExit('Backup does not belong to this prefix')
 digest=hashlib.sha256(p.read_bytes()).hexdigest()
 if digest not in [meta['compat_sha256'],meta['original_sha256']]:raise SystemExit('Refusing to overwrite unrecognised file: '+str(p))
 target=backup.get('symlink_target')
 if target:
  if p.is_symlink() and os.readlink(p)==target:continue
  p.unlink();p.symlink_to(target)
 elif digest!=meta['original_sha256']:
  p.unlink();shutil.copyfile(d/'prefix-original.dll',p)
p=prefix/'user.reg';s=p.read_text();a=json.loads((research/'debug-before-20261109-matrix.json').read_text());i=s.index(a['key']);end=s.index('\n[',i+1);p.write_text(s[:i]+a['section']+s[end:])
old=root/'amazing.before-compat'
if old.exists():shutil.copy2(old,h/'.local/bin/amazing')
print('Original test-prefix DLLs, debug settings and previous launcher restored. Shared runners and game files were not changed.')
