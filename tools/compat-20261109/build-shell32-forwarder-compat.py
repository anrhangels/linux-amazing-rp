from pathlib import Path
import struct,json,hashlib
h=Path.home();ns={};exec(Path(__file__).with_name('pe_reader.py').read_text(),ns)
p=h/'.local/share/linux-arizona-rp/runners/GE-Proton11-11-x86_64/files/lib/wine/i386-windows/shell32.dll';pe=ns['PE'](p);b=bytearray(pe.b)
u16=lambda o:struct.unpack_from('<H',b,o)[0];u32=lambda o:struct.unpack_from('<I',b,o)[0]
put=lambda o,v:struct.pack_into('<I',b,o,v)
e=u32(60);opt=e+24;sh=opt+u16(e+20);n=u16(e+6);assert sh+40*(n+1)<=u32(opt+60)
imports={};r,_=pe.dirs[1];o=pe.off(r)
for j in range(2048):
 oft,_,_,name,ft=struct.unpack_from('<IIIII',b,o+j*20)
 if not name:break
 dll=pe.string(name).lower();t=pe.off(oft or ft)
 for k in range(8192):
  val=u32(t+4*k)
  if not val:break
  if not val&0x80000000:imports[(dll,pe.string(val+2))]=ft+4*k
load=imports[('kernel32.dll','LoadLibraryW')];getproc=imports[('kernel32.dll','GetProcAddress')]
align=lambda x,a:(x+a-1)//a*a
va=align(max(s['rva']+max(s['virtual_size'],s['raw_size']) for s in pe.sections),u32(opt+32));raw=align(len(b),u32(opt+36))
data=bytearray(160)
# PIC stdcall tail thunk; forward to genuine shcore implementation; no success spoofing.
code=bytearray.fromhex('53e8000000005b81eb')+struct.pack('<I',va+6)
code+=bytes.fromhex('f0ff83')+struct.pack('<I',va+144)
code+=bytes.fromhex('8d83')+struct.pack('<I',va+80)+bytes.fromhex('50ff93')+struct.pack('<I',load)
code+=bytes.fromhex('85c07415')
code+=bytes.fromhex('8d8b')+struct.pack('<I',va+112)+bytes.fromhex('5150ff93')+struct.pack('<I',getproc)
code+=bytes.fromhex('85c074035bffe05b31c0c20800')
assert len(code)==64
data[:64]=code;module='shcore.dll\0'.encode('utf-16le');name=b'CommandLineToArgvW\0';data[80:80+len(module)]=module;data[112:112+len(name)]=name
r,z=pe.dirs[0];o=pe.off(r);base,nf,nn,af,an,ao=struct.unpack_from('<IIIIII',b,o+16);idx=None
for i in range(nn):
 if pe.string(u32(pe.off(an)+4*i))=='CommandLineToArgvW':idx=u16(pe.off(ao)+2*i);break
assert idx is not None and pe.exports()['CommandLineToArgvW']=='shcore.CommandLineToArgvW'
put(pe.off(af)+4*idx,va)
b.extend(bytes(raw-len(b)));b.extend(data);size=align(len(data),u32(opt+36));b.extend(bytes(raw+size-len(b)))
q=sh+n*40;b[q:q+40]=bytes(40);b[q:q+8]=b'.arpcomp';struct.pack_into('<IIII',b,q+8,len(data),va,size,raw);put(q+36,0xe0000060)
struct.pack_into('<H',b,e+6,n+1);put(opt+56,align(va+len(data),u32(opt+32)));put(opt+4,u32(opt+4)+size);put(opt+64,0)
i=b.find(b'Wine builtin DLL',0,128);assert i>=0;b[i:i+16]=b'Compat PE copy'.ljust(16,b'\0')
out=h/'.cache/linux-amazing-rp/shell32-forwarder-compat.dll';out.write_bytes(b);out.chmod(0o600)
actual=ns['PE'](out).exports();expected=pe.exports();changed=[str(k) for k in expected if actual.get(k)!=expected[k]];assert set(changed)=={'CommandLineToArgvW',str(base+idx)}
d=h/'.local/state/linux-amazing-rp/autonomous-research/shell32-forwarder-compat';d.mkdir(mode=0o700,exist_ok=True)
report={'original_sha256':hashlib.sha256(pe.b).hexdigest(),'compat_sha256':hashlib.sha256(b).hexdigest(),'export':'CommandLineToArgvW','changed_export_keys':changed,'entry_rva':hex(va),'counter_rva':hex(va+144),'iat_LoadLibraryW':hex(load),'iat_GetProcAddress':hex(getproc),'semantics':'stdcall tail call to actual shcore.CommandLineToArgvW; NULL if loader or resolver fails; diagnostic call counter','shared_runner_modified':False}
f=d/'build.json';f.write_text(json.dumps(report,indent=2));f.chmod(0o600)
print('Built private shell32 compatibility copy. Only named/ordinal CommandLineToArgvW entry changed; RVA',hex(va))
