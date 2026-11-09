from pathlib import Path
import struct,json,hashlib
h=Path.home();ns={};exec(Path(__file__).with_name('pe_reader.py').read_text(),ns)
p=h/'.local/share/linux-arizona-rp/runners/GE-Proton11-11-x86_64/files/lib/wine/dxvk/i386-windows/d3d9.dll';pe=ns['PE'](p)
sha=hashlib.sha256(pe.b).hexdigest();assert sha=='a826bbbc540bb864d79cbaa6a56fbd4cf38737e3b2e2f47c0933f254530d8eaf'
# Measured from two real IDirect3DDevice9 instances via standard CreateDevice in this exact DXVK build.
table_rva=0x642670;marker_rva=0x800;b=bytearray(pe.b);assert b[marker_rva:marker_rva+14]==bytes(14)
u16=lambda o:struct.unpack_from('<H',b,o)[0];u32=lambda o:struct.unpack_from('<I',b,o)[0];put=lambda o,v:struct.pack_into('<I',b,o,v)
e=u32(60);opt=e+24;sh=opt+u16(e+20);n=u16(e+6);assert sh+40*(n+1)<marker_rva and marker_rva+14<=u32(opt+60)
# Read-only locator data for a legacy constructor-pattern lookup, not an executed function.
b[marker_rva:marker_rva+14]=b'\xc7\x06'+struct.pack('<I',pe.base+table_rva)+b'\x89\x86\x00\x00\x00\x00\x89\x86'
# Retain original base relocations and relocate the genuine vtable address in the locator.
r,z=pe.dirs[5];assert r and z;old=pe.b[pe.off(r):pe.off(r)+z];relocs=bytearray();cur=0
while cur+8<=len(old):
 page,size=struct.unpack_from('<II',old,cur)
 if not size:break
 assert size>=8 and cur+size<=len(old);relocs.extend(old[cur:cur+size]);cur+=size
relocs.extend(struct.pack('<IIHH',0,12,(3<<12)|(marker_rva+2),0))
align=lambda x,a:(x+a-1)//a*a
va=align(max(s['rva']+max(s['virtual_size'],s['raw_size']) for s in pe.sections),u32(opt+32));raw=align(len(b),u32(opt+36));size=align(len(relocs),u32(opt+36))
b.extend(bytes(raw-len(b)));b.extend(relocs);b.extend(bytes(raw+size-len(b)))
q=sh+n*40;b[q:q+40]=bytes(40);b[q:q+8]=b'.arploc\0';struct.pack_into('<IIII',b,q+8,len(relocs),va,size,raw);put(q+36,0x40000040)
struct.pack_into('<H',b,e+6,n+1);put(opt+56,align(va+len(relocs),u32(opt+32)));put(opt+8,u32(opt+8)+size);put(opt+96+5*8,va);put(opt+100+5*8,len(relocs));put(opt+64,0)
out=h/'.cache/linux-amazing-rp/d3d9-vtable-locator.dll';out.write_bytes(b);out.chmod(0o600);test=ns['PE'](out);assert test.exports()==pe.exports() and test.imports()==pe.imports()
d=h/'.local/state/linux-amazing-rp/autonomous-research/d3d9-vtable-locator';d.mkdir(mode=0o700,exist_ok=True)
a={'original_sha256':sha,'compat_sha256':hashlib.sha256(b).hexdigest(),'marker_rva':hex(marker_rva),'vtable_rva':hex(table_rva),'preferred_image_base':hex(pe.base),'new_reloc_rva':hex(va),'exports_unchanged':True,'imports_unchanged':True,'scope':'Private DXVK graphics library only. Locator points to real measured IDirect3DDevice9 vtable. No game-code patch or fake device.'}
f=d/'build.json';f.write_text(json.dumps(a,indent=2));f.chmod(0o600);print('Built private DXVK locator copy; original exports/imports preserved; vtable address uses base relocation')
