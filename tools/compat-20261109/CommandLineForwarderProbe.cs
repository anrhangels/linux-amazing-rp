using System;using System.IO;using System.Text;using System.Runtime.InteropServices;
class CommandLineForwarderProbe {
 [DllImport("kernel32",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibrary(string n);
 [DllImport("kernel32",CharSet=CharSet.Ansi,ExactSpelling=true)] static extern IntPtr GetProcAddress(IntPtr m,string n);
 [DllImport("kernel32")] static extern IntPtr LocalFree(IntPtr p);
 [UnmanagedFunctionPointer(CallingConvention.StdCall,CharSet=CharSet.Unicode)] delegate IntPtr Argv([MarshalAs(UnmanagedType.LPWStr)]string s,out int n);
 static string[] Run(Argv f,string s){int n;var p=f(s,out n);if(p==IntPtr.Zero)throw new Exception("NULL argv");try{var a=new string[n];for(int i=0;i<n;i++)a[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(p,i*4));return a;}finally{LocalFree(p);}}
 static void Main(){var b=new StringBuilder();try{
 var shell=LoadLibrary("shell32.dll");var core=LoadLibrary("shcore.dll");var a=GetProcAddress(shell,"CommandLineToArgvW");var z=GetProcAddress(core,"CommandLineToArgvW");b.AppendLine("shell base="+shell.ToInt64().ToString("X")+" entry="+a.ToInt64().ToString("X")+" direct="+z.ToInt64().ToString("X"));
 var f=(Argv)Marshal.GetDelegateForFunctionPointer(a,typeof(Argv));var g=(Argv)Marshal.GetDelegateForFunctionPointer(z,typeof(Argv));
 foreach(var s in new[]{"\"C:\\Program Files\\Amazing\\amazing.exe\" --name \"Алексей Скольников\"","amazing.exe one two","amazing.exe \"\" tail"}){var x=Run(f,s);var y=Run(g,s);if(x.Length!=y.Length||String.Join("|",x)!=String.Join("|",y))throw new Exception("Mismatch");b.AppendLine("PASS argc="+x.Length+" "+String.Join(" | ",x));}
 b.AppendLine("Counter="+Marshal.ReadInt32(new IntPtr(unchecked((int)((uint)shell.ToInt32()+9814160u)))));b.AppendLine("ALL_PASS");
 }catch(Exception e){b.AppendLine(e.ToString());}File.WriteAllText(@"C:\amazing-compat\commandline-forwarder-probe.txt",b.ToString());}}
