from pathlib import Path
import struct,hashlib,json,collections,math
H=Path.home();ROOT=H/'Games/amazing-rp/prefix/drive_c/Games/Amazing Games/Amazing Online/PC';SYS=H/'Games/amazing-rp/ge11-clean-prefix/drive_c/windows/syswow64'
class PE:
 def __init__(self,p):
  self.p=p;self.b=p.read_bytes();b=self.b;self.u16=lambda o:struct.unpack_from('<H',b,o)[0];self.u32=lambda o:struct.unpack_from('<I',b,o)[0];e=self.u32(60);o=e+24;self.magic=self.u16(o);assert self.magic in (0x10b,0x20b);self.base=self.u32(o+28) if self.magic==0x10b else struct.unpack_from('<Q',b,o+24)[0];self.sections=[];sh=o+self.u16(e+20)
  for i in range(self.u16(e+6)):
   q=sh+40*i;vs,va,rs,ro=struct.unpack_from('<IIII',b,q+8);raw=b[ro:ro+rs];ct=collections.Counter(raw);en=-sum((v/len(raw))*math.log2(v/len(raw)) for v in ct.values()) if raw else 0;self.sections.append(dict(name=b[q:q+8].rstrip(b'\0').decode(errors='replace'),rva=va,virtual_size=vs,raw_size=rs,raw_offset=ro,entropy=round(en,3)))
  self.dirs=[struct.unpack_from('<II',b,o+(96 if self.magic==0x10b else 112)+8*i) for i in range(16)]
 def off(self,r):
  for s in self.sections:
   if s['rva']<=r<s['rva']+max(s['virtual_size'],s['raw_size']):
    x=r-s['rva'];assert x<s['raw_size'],('unbacked RVA',hex(r));return s['raw_offset']+x
  if r<0x400:return r
  raise ValueError(hex(r))
 def string(self,r):
  o=self.off(r);return self.b[o:self.b.index(b'\0',o)].decode(errors='replace')
 def imports(self):
  r,z=self.dirs[1];out=[]
  if not r:return out
  o=self.off(r)
  for i in range(2048):
   oft,_,_,name,ft=struct.unpack_from('<IIIII',self.b,o+20*i)
   if not name:break
   funcs=[];t=self.off(oft or ft);width=4 if self.magic==0x10b else 8;flag=1<<(width*8-1)
   for j in range(8192):
    v=struct.unpack_from('<I' if width==4 else '<Q',self.b,t+width*j)[0]
    if not v:break
    funcs.append(v&0xffff if v&flag else self.string(v+2))
   out.append(dict(dll=self.string(name),functions=funcs))
  return out
 def exports(self):
  r,z=self.dirs[0];out={}
  if not r:return out
  o=self.off(r);base,nf,nn,af,an,ao=struct.unpack_from('<IIIIII',self.b,o+16);a=self.off(af)
  for i in range(nf):
   rv=self.u32(a+4*i)
   if rv:out[base+i]=self.string(rv) if r<=rv<r+z else rv
  for i in range(nn):
   name=self.string(self.u32(self.off(an)+4*i));idx=self.u16(self.off(ao)+2*i);out[name]=out.get(base+idx,0)
  return out
