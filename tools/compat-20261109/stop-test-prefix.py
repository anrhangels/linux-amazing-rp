from pathlib import Path
import os,signal,sys
p=Path(sys.argv[1]).resolve()
assert p.parent==Path.home()/"Games/amazing-rp" and p.name!="prefix"
found=[]
for d in Path("/proc").glob("[0-9]*"):
 try:
  env=d.joinpath("environ").read_bytes().split(b"\0")
  if any(e.partition(b"=")[0] in (b"WINEPREFIX",b"STEAM_COMPAT_DATA_PATH") and Path(os.fsdecode(e.partition(b"=")[2])).resolve()==p for e in env):found.append(int(d.name))
 except (OSError,ValueError):pass
for pid in found:
 try:os.kill(pid,signal.SIGTERM)
 except ProcessLookupError:pass
print("Stopped test-prefix processes:",len(found))
