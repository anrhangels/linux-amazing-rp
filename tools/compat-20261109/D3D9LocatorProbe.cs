using System;using System.IO;using System.Text;using System.Runtime.InteropServices;
class D3D9LocatorProbe {
 [DllImport("d3d9",CallingConvention=CallingConvention.StdCall)]static extern IntPtr Direct3DCreate9(uint sdk);
 [DllImport("kernel32",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandle(string n);
 [DllImport("kernel32",CharSet=CharSet.Unicode)]static extern bool GetModuleHandleEx(uint flags,IntPtr addr,out IntPtr module);
 [DllImport("kernel32",CharSet=CharSet.Unicode)]static extern uint GetModuleFileName(IntPtr m,StringBuilder n,int size);
 [DllImport("user32",CharSet=CharSet.Unicode)]static extern IntPtr CreateWindowEx(uint ex,string cls,string title,uint style,int x,int y,int w,int h,IntPtr parent,IntPtr menu,IntPtr instance,IntPtr param);
 [DllImport("user32")]static extern bool DestroyWindow(IntPtr w);
 [StructLayout(LayoutKind.Sequential)]struct PP {public uint Width,Height,Format,Count,MultiSample,MultiQuality,Swap;public IntPtr Window;public int Windowed,AutoDepth;public uint DepthFormat,Flags,Refresh,Interval;}
 [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate int Create(IntPtr self,uint adapter,uint type,IntPtr focus,uint flags,ref PP pp,out IntPtr device);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate uint Release(IntPtr self);
 static T Method<T>(IntPtr self,int slot){return (T)(object)Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(Marshal.ReadIntPtr(self),4*slot),typeof(T));}
 static void Main(){var log=new StringBuilder();IntPtr api=IntPtr.Zero,device=IntPtr.Zero,w=IntPtr.Zero;try {
 w=CreateWindowEx(0,"STATIC","Amazing D3D9 compatibility probe",0,-32000,-32000,64,64,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero);if(w==IntPtr.Zero)throw new Exception("Window create failed");
 api=Direct3DCreate9(32);if(api==IntPtr.Zero)throw new Exception("Direct3DCreate9 returned NULL");
 IntPtr prior=IntPtr.Zero;
 foreach(uint flags in new uint[]{0x20,0x40}){
 var pp=new PP{Width=64,Height=64,Format=0,Count=1,Swap=1,Window=w,Windowed=1,Interval=0x80000000};
 int hr=Method<Create>(api,16)(api,0,1,w,flags,ref pp,out device);log.AppendLine("CreateDevice flags="+flags.ToString("X")+" hr="+hr.ToString("X8"));if(hr<0||device==IntPtr.Zero)throw new Exception("CreateDevice failed");
 var table=Marshal.ReadIntPtr(device);IntPtr owner;if(!GetModuleHandleEx(6,table,out owner))throw new Exception("No vtable module");var path=new StringBuilder(512);GetModuleFileName(owner,path,path.Capacity);
 long rva=unchecked((uint)table.ToInt32())-(long)unchecked((uint)owner.ToInt32());log.AppendLine("module="+path+" base="+owner.ToInt64().ToString("X")+" table="+table.ToInt64().ToString("X")+" rva="+rva.ToString("X"));
 for(int i=0;i<119;i++)if(Marshal.ReadIntPtr(table,4*i)==IntPtr.Zero)throw new Exception("Null method "+i);
 var marker=new IntPtr(unchecked((int)((uint)owner.ToInt32()+0x800u)));if(Marshal.ReadByte(marker)!=0xc7||Marshal.ReadByte(marker,1)!=6||Marshal.ReadByte(marker,6)!=0x89||Marshal.ReadByte(marker,7)!=0x86||Marshal.ReadByte(marker,12)!=0x89||Marshal.ReadByte(marker,13)!=0x86)throw new Exception("Locator bytes missing");if(Marshal.ReadIntPtr(marker,2)!=table)throw new Exception("Locator points to wrong vtable");log.AppendLine("LOCATOR_MATCHES_REAL_DEVICE");if(prior!=IntPtr.Zero && table!=prior)throw new Exception("Device vtables differ");prior=table;
 Method<Release>(device,2)(device);device=IntPtr.Zero;
 }
 log.AppendLine("ALL_PASS");
 }catch(Exception e){log.AppendLine(e.ToString());}finally{if(device!=IntPtr.Zero)Method<Release>(device,2)(device);if(api!=IntPtr.Zero)Method<Release>(api,2)(api);if(w!=IntPtr.Zero)DestroyWindow(w);File.WriteAllText(@"C:\amazing-compat\d3d9-locator-probe.txt",log.ToString());}}
}
