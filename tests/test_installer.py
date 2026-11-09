import hashlib, importlib.util, io, json, os, subprocess, sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install_amazing.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ss=importlib.util.spec_from_file_location('screen',ROOT/'tools/compat-20261109/screen.py');screen=importlib.util.module_from_spec(ss);ss.loader.exec_module(screen)
class Helpers(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_malformed_digest_rejected(self):
  cfg=json.loads((ROOT/'configs/downloads.json').read_text());cfg['msdelta']['sha256']='a'*62
  with self.assertRaises(ValueError):m.validate_downloads(cfg)
 def test_resume_skips_installed_winetricks_verbs(self):
  (self.home/'winetricks.log').write_text('remove_mono internal\ndotnet40\ndotnet48\nvcrun2022\n')
  self.assertEqual(m.missing_verbs(self.home,['dotnet48','vcrun2022','d3dx9_43']),['d3dx9_43'])
 def test_prefix_rejects_original(self):
  with self.assertRaises(ValueError):m.managed_prefix(self.home,self.home/'Games/amazing-rp/prefix')
 def test_prefix_rejects_outside(self):
  with self.assertRaises(ValueError):m.managed_prefix(self.home,self.home/'different')
 def test_prefix_rejects_symlink(self):
  p=self.home/'Games/amazing-rp/test';p.parent.mkdir(parents=True);p.symlink_to(self.home/'outside')
  with self.assertRaises(ValueError):m.managed_prefix(self.home,p)
 def test_prefix_accepts_managed_name(self):self.assertEqual(m.managed_prefix(self.home,self.home/'Games/amazing-rp/fresh'),self.home/'Games/amazing-rp/fresh')
 def test_check_is_read_only(self):
  setup=m.Setup(self.home/'Games/amazing-rp/fresh',self.home);before=list(self.home.rglob('*'));status=setup.status();self.assertFalse(status['ready_profile']);self.assertEqual(before,list(self.home.rglob('*')))
 def test_unowned_prefix_is_preserved(self):
  p=self.home/'Games/amazing-rp/fresh';p.mkdir(parents=True);f=p/'keep.txt';f.write_text('keep')
  with self.assertRaises(ValueError):m.Setup(p,self.home).install()
  self.assertEqual(f.read_text(),'keep');self.assertFalse((self.home/'.local/state/linux-amazing-rp').exists())
 def test_busy_prefix_never_mutates(self):
  setup=m.Setup(self.home/'Games/amazing-rp/fresh',self.home)
  with patch.object(m,'busy_prefix',return_value=[42]):
   with self.assertRaises(ValueError):setup.install()
  self.assertEqual(list(self.home.iterdir()),[])
 def test_atomic_json_private(self):
  p=self.home/'state/config.json';m.atomic_json(p,{'unicode':'Привет'});self.assertEqual(json.loads(p.read_text())['unicode'],'Привет');self.assertEqual(p.stat().st_mode&0o777,0o600)
 def test_zip_traversal_rejected_before_extract(self):
  p=self.home/'bad.zip'
  with zipfile.ZipFile(p,'w') as z:z.writestr('../escape','x')
  with self.assertRaises(ValueError):m.safe_zip_extract(p,self.home/'out')
  self.assertFalse((self.home/'out').exists())
 def test_zip_symlink_rejected(self):
  p=self.home/'bad.zip';entry=zipfile.ZipInfo('link');entry.external_attr=(0o120777<<16)
  with zipfile.ZipFile(p,'w') as z:z.writestr(entry,'/tmp/target')
  with self.assertRaises(ValueError):m.safe_zip_extract(p,self.home/'out')
 def test_zip_regular_extract(self):
  p=self.home/'ok.zip'
  with zipfile.ZipFile(p,'w') as z:z.writestr('folder/file','ok')
  m.safe_zip_extract(p,self.home/'out');self.assertEqual((self.home/'out/folder/file').read_text(),'ok')
 def test_unpinned_third_party_download_rejected(self):
  with self.assertRaises(ValueError):m.fetch({'url':'https://untrusted.example/a.exe'},self.home/'x')
  self.assertFalse((self.home/'x').exists())
 def test_http_download_rejected(self):
  with self.assertRaises(ValueError):m.fetch({'url':'http://example/a','sha256':'0'*64},self.home/'x')
 def test_good_cache_does_not_request_network(self):
  p=self.home/'x';p.write_bytes(b'good')
  with patch.object(m,'urlopen',side_effect=AssertionError('network')):self.assertEqual(m.fetch({'url':'https://example/a','sha256':hashlib.sha256(b'good').hexdigest()},p),p)
 def test_bad_download_never_replaces_existing(self):
  class Response(io.BytesIO):url='https://example/a'
  p=self.home/'x';p.write_bytes(b'old')
  with patch.object(m,'urlopen',return_value=Response(b'bad')):
   with self.assertRaises(ValueError):m.fetch({'url':'https://example/a','sha256':'0'*64},p)
  self.assertEqual(p.read_bytes(),b'old');self.assertFalse((self.home/'x.part').exists())
 def test_snapshot_preserves_symlink_without_following(self):
  setup=m.Setup(self.home/'Games/amazing-rp/fresh',self.home);setup.backup=self.home/'backup';source=self.home/'original';source.write_text('original');p=self.home/'link';p.symlink_to(source);setup.save(p)
  self.assertEqual(setup.saved[0]['kind'],'symlink');self.assertEqual(source.read_text(),'original');self.assertTrue(p.is_symlink())
 def test_new_profile_metadata_is_isolated(self):
  a=m.Setup(self.home/'Games/amazing-rp/first',self.home);b=m.Setup(self.home/'Games/amazing-rp/second',self.home);self.assertNotEqual(a.meta,b.meta);self.assertNotEqual(a.compat_runner,b.compat_runner)
 def test_bootstrap_unknown_argument_never_installs(self):
  r=subprocess.run(['bash',str(ROOT/'install-amazing-rp.sh'),'--definitely-invalid'],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertIn('Неизвестный',r.stderr)
 def test_bootstrap_missing_prefix_argument(self):
  r=subprocess.run(['bash',str(ROOT/'install-amazing-rp.sh'),'--prefix'],capture_output=True,text=True);self.assertEqual(r.returncode,2)
 def test_bootstrap_help(self):
  r=subprocess.run(['bash',str(ROOT/'install-amazing-rp.sh'),'--help'],capture_output=True,text=True);self.assertEqual(r.returncode,0);self.assertIn('установка игры',r.stdout)
 def test_x11_fallback_selects_primary_and_rate(self):
  data='eDP-1 connected 1600x1000+0+0\n  1600x1000 60.00*+\nHDMI-A-3 connected primary 1920x1080+1600+0\n  1920x1080 164.83*+\n'
  with patch.object(screen.subprocess,'check_output',return_value=data):s=screen.select_x11_screen()
  self.assertEqual((s['monitor'],s['width'],s['height'],s['refresh_hz']),('HDMI-A-3',1920,1080,164.83))
 def test_primary_restores_absence(self):
  with patch.object(screen,'x11_outputs',side_effect=[(['eDP','HDMI'],None),(['eDP','HDMI'],'HDMI'),(['eDP','HDMI'],'HDMI')]),patch.object(screen.subprocess,'run') as run:
   restore=screen.prepare_primary({'monitor':'HDMI'});restore();self.assertIn('--noprimary',run.call_args.args[0])
 def test_primary_does_not_override_user_change(self):
  with patch.object(screen,'x11_outputs',side_effect=[(['eDP','HDMI'],'eDP'),(['eDP','HDMI'],'HDMI'),(['eDP','HDMI'],'eDP')]),patch.object(screen.subprocess,'run') as run:
   restore=screen.prepare_primary({'monitor':'HDMI'});restore();self.assertEqual(run.call_count,1)
if __name__=='__main__':unittest.main()
