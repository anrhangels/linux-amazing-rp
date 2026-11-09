#!/usr/bin/env python3
"""One entry point prepares Amazing Online in its own prefix; never clears game data."""
from __future__ import annotations
import argparse, contextlib, datetime, fcntl, hashlib, json, os, platform, re, shutil
import subprocess, sys, tarfile, tempfile, time, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APP = 'io.github.Faugus.faugus-launcher'
ASSEMBLIES = ['System.Management.Automation.dll', 'Microsoft.PowerShell.Commands.Diagnostics.dll',
 'Microsoft.PowerShell.Commands.Management.dll', 'Microsoft.PowerShell.Commands.Utility.dll',
 'Microsoft.PowerShell.ConsoleHost.dll', 'Microsoft.PowerShell.Security.dll',
 'Microsoft.WSMan.Management.dll', 'Microsoft.WSMan.Runtime.dll',
 'Microsoft.Management.Infrastructure.dll', 'Microsoft.Management.Infrastructure.CimCmdlets.dll',
 'Microsoft.Management.Infrastructure.Native.dll', 'Microsoft.Windows.DSC.CoreConfProviders.dll']


def validate_downloads(spec):
    for name in ['proton', 'umu', 'wmf51', 'sp1_extraction_only', 'msdelta']:
        if not re.fullmatch(r'[0-9a-f]{64}', spec[name]['sha256']): raise ValueError('Некорректная SHA-256 в конфигурации: ' + name)
    if not re.fullmatch(r'[0-9a-f]{64}', spec['dxvk_source_sha256']): raise ValueError('Некорректная SHA-256 DXVK')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream: json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
        os.replace(temp, path); path.chmod(0o600)
    finally:
        Path(temp).unlink(missing_ok=True)


def fetch(spec, target):
    """Stable dependencies are pinned; the official launcher is HTTPS + recorded digest."""
    target = Path(target)
    if spec.get('sha256') and target.is_file() and digest(target) == spec['sha256']: return target
    parsed = urlsplit(spec['url'])
    if parsed.scheme != 'https': raise ValueError('Загрузка требует HTTPS')
    if not spec.get('sha256') and parsed.hostname not in spec.get('official_hosts', []):
        raise ValueError('Для стороннего компонента требуется SHA-256')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + '.part'); limit = spec.get('maximum_bytes', 2_000_000_000)
    try:
        with urlopen(Request(spec['url'], headers={'User-Agent': 'linux-amazing-rp/1.0'}), timeout=60) as response:
            final = urlsplit(response.url)
            if final.scheme != 'https': raise ValueError('Запрещено понижение HTTPS')
            if not spec.get('sha256') and final.hostname not in spec['official_hosts']: raise ValueError('Изменился официальный источник лаунчера')
            with temp.open('wb') as out:
                total = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block: break
                    total += len(block)
                    if total > limit: raise ValueError('Слишком большой загружаемый файл')
                    out.write(block)
        if spec.get('sha256') and digest(temp) != spec['sha256']: raise ValueError('Не совпала SHA-256: ' + target.name)
        if not spec.get('sha256'):
            with temp.open('rb') as src:
                if src.read(2) != b'MZ': raise ValueError('Вместо установщика получен другой файл')
        temp.replace(target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def safe_zip_extract(archive, target):
    target = Path(target)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path = PurePosixPath(item.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Небезопасный путь в ZIP')
        target.mkdir(parents=True, exist_ok=True); z.extractall(target)


def managed_prefix(home, prefix):
    base = Path(home) / 'Games/amazing-rp'; path = Path(prefix).expanduser().absolute()
    if path.parent.resolve() != base.resolve() or path.name == 'prefix' or not re.fullmatch(r'[A-Za-z0-9_-]+', path.name):
        raise ValueError('Используйте отдельный каталог ~/Games/amazing-rp/<имя>; исходный prefix не изменяется')
    if path.is_symlink(): raise ValueError('Префикс не должен быть символьной ссылкой')
    return path


def busy_prefix(prefix):
    expected = Path(prefix).resolve(); matches = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            env = dict(e.split(b'=', 1) for e in (p / 'environ').read_bytes().split(b'\0') if b'=' in e)
            wp = env.get(b'WINEPREFIX') or env.get(b'STEAM_COMPAT_DATA_PATH')
            if wp and Path(os.fsdecode(wp)).resolve() == expected: matches.append(int(p.name))
        except (OSError, ValueError): pass
    return matches


def missing_verbs(prefix, desired):
    path = Path(prefix) / 'winetricks.log'
    installed = {line.split()[0] for line in path.read_text().splitlines() if line.split()} if path.is_file() else set()
    return [verb for verb in desired if verb not in installed]


def delta_plan(payload, requested):
    ns = {'c': 'urn:ContainerIndex'}
    root = ET.parse(Path(payload) / '_manifest_.cix.xml').getroot()
    files = {f.get('id'): f for f in root.findall('.//c:File', ns)}
    wanted = {n.lower() for n in requested}
    selected = [f for f in files.values() if f.get('name', '').lower().split('\\')[-1] in wanted and 'none_' in f.get('name', '')]
    if len(selected) != len(wanted): raise ValueError('Изменилась структура WMF: не найдены нужные сборки')
    plan, done, visiting = [], set(), set()
    def add(f):
        key = f.get('id')
        if key in done: return
        if key in visiting: raise ValueError('Цикл зависимостей WMF')
        if not key or not re.fullmatch(r'[A-Za-z0-9_.-]+', key): raise ValueError('Некорректный идентификатор WMF')
        visiting.add(key); delta = f.find('c:Delta', ns)
        if delta is None: raise ValueError('WMF delta отсутствует')
        basis = delta.find('c:Basis', ns); base = basis.get('file') if basis is not None else None
        if base: add(files[base])
        source = delta.find('c:Source', ns); name = source.get('name')
        path = (Path(payload) / name).resolve()
        if not path.is_relative_to(Path(payload).resolve()): raise ValueError('Путь delta вне пакета')
        if digest(path).lower() != source.find('c:Hash', ns).get('value').lower(): raise ValueError('Повреждена исходная delta')
        plan.append({'id': key, 'basis': base, 'delta': str(path), 'sha256': f.find('c:Hash', ns).get('value').lower(), 'name': f.get('name').split('\\')[-1], 'selected': f in selected})
        visiting.remove(key); done.add(key)
    for f in selected: add(f)
    return plan


class Setup:
    def __init__(self, prefix, home=None):
        self.home = Path(home) if home else Path.home(); self.prefix = managed_prefix(self.home, prefix)
        self.data = self.home / '.local/share/linux-amazing-rp'; self.state = self.home / '.local/state/linux-amazing-rp'
        self.cache = self.home / '.cache/linux-amazing-rp/installer'; self.spec = json.loads((ROOT / 'configs/downloads.json').read_text()); validate_downloads(self.spec)
        self.runner = self.data / 'runners' / self.spec['proton']['directory']; self.umu = self.data / 'umu-run'
        self.compat_runner = self.data / 'runners' / ('GE-Proton11-11-Amazing-Compat-' + self.prefix.name)
        self.meta = self.state / 'profiles' / self.prefix.name
        self.existing_config = {}
        configs = [self.meta / 'runtime.json', self.data / 'settings.json']
        for config in configs:
            if config.is_file():
                candidate = json.loads(config.read_text())
                if Path(candidate.get('prefix', '/')) == self.prefix:
                    self.existing_config = candidate; self.compat_runner = Path(candidate['runner']); self.meta = Path(candidate['metadata']); self.umu = Path(candidate['umu']); self.runner = Path(candidate.get('source_runner', str(self.runner))); break
        if not self.existing_config and self.prefix == self.home / 'Games/amazing-rp/ge11-clean-prefix' and (self.state / 'autonomous-research/shell32-forwarder-compat/prefix-backup.json').is_file():
            backup = json.loads((self.state / 'autonomous-research/shell32-forwarder-compat/prefix-backup.json').read_text())
            if Path(backup['path']) == self.prefix / 'drive_c/windows/syswow64/shell32.dll':
                self.compat_runner = self.data / 'runners/GE-Proton11-11-Amazing-Compat'; self.meta = self.state / 'autonomous-research'
        shared = self.home / '.local/share/linux-arizona-rp/runners' / self.spec['proton']['directory']
        if not (self.runner / 'proton').is_file() and (shared / 'proton').is_file(): self.runner = shared; self.assets = ROOT / 'tools/compat-20261109'
        self.logs = self.state / 'install-logs' / self.prefix.name; self.marker = self.state / ('install-' + self.prefix.name + '.json')
        self.saved = []; self.backup = None

    def checked_existing_profile(self):
        launcher = Path(self.existing_config.get('launcher', self.prefix / 'drive_c/Games/Amazing Launcher/AmazingUpdater.exe'))
        if not launcher.is_file():
            alternative = self.prefix / 'drive_c/Games/AmazingLauncher/AmazingUpdater.exe'
            if alternative.is_file(): launcher = alternative
        self.detected_launcher = launcher
        manifests = [(self.prefix / 'drive_c/windows/syswow64/shell32.dll', self.meta / 'shell32-forwarder-compat/build.json'),
                     (self.compat_runner / 'files/lib/wine/dxvk/i386-windows/d3d9.dll', self.meta / 'd3d9-vtable-locator/build.json')]
        try:
            return launcher.is_file() and all(p.is_file() and digest(p) == json.loads(m.read_text())['compat_sha256'] for p, m in manifests)
        except (OSError, KeyError, ValueError): return False

    def status(self):
        return {'prefix': str(self.prefix), 'ready_profile': self.checked_existing_profile(),
                'active_prefix_processes': len(busy_prefix(self.prefix)), 'flatpak': bool(shutil.which('flatpak')),
                'proton': (self.runner / 'proton').is_file(), 'installer_version': '1.0'}

    def save(self, path):
        """Backup each changed path before mutation; preserve links without following them."""
        path = Path(path)
        if any(e['path'] == str(path) for e in self.saved): return
        self.backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        entry = {'path': str(path), 'kind': 'absent'}
        if path.is_symlink(): entry.update(kind='symlink', target=os.readlink(path))
        elif path.is_file():
            dest = self.backup / ('file-' + str(len(self.saved))); shutil.copyfile(path, dest); dest.chmod(0o600)
            entry.update(kind='file', backup=str(dest), sha256=digest(dest), mode=path.stat().st_mode & 0o777)
        elif path.exists(): raise ValueError('Ожидался файл: ' + str(path))
        self.saved.append(entry); atomic_json(self.backup / 'restore.json', {'entries': self.saved, 'prefix': str(self.prefix)})

    def command(self, exe, *arguments, runner=None, overrides=None):
        args = ['flatpak', 'run', '--command=env', '--filesystem=' + str(self.prefix),
                '--filesystem=' + str(self.data), '--filesystem=' + str(self.state), '--filesystem=' + str(self.cache),
                '--filesystem=' + str(ROOT) + ':ro', '--filesystem=' + str(self.home / '.local/share/linux-arizona-rp') + ':ro',
                APP]
        for key in ['WINEDLLOVERRIDES', 'PROTON_USE_WINED3D', 'PROTON_ENABLE_WAYLAND', 'WINEARCH']:
            args += ['-u', key]
        args += ['LANG=C.UTF-8', 'LC_ALL=C.UTF-8', 'WINEPREFIX=' + str(self.prefix), 'PROTONPATH=' + str(runner or self.runner),
                 'GAMEID=umu-99998712', 'UMU_USE_STEAM=1', 'UMU_CONTAINER_NSENTER=1', 'PROTON_USE_WOW64=1',
                 'MANGOHUD=0', 'WINEDEBUG=-all,err+all']
        if overrides: args += ['WINEDLLOVERRIDES=' + overrides]
        return args + [str(self.umu), str(exe)] + list(map(str, arguments))

    def run(self, stage, exe, *arguments, **kw):
        print('  ' + stage, flush=True)
        path = self.logs / ('install-' + stage + '.log'); self.logs.mkdir(parents=True, exist_ok=True, mode=0o700); self.logs.chmod(0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600); os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'a') as out:
            subprocess.run(self.command(exe, *arguments, **kw), stdout=out, stderr=subprocess.STDOUT, check=True, timeout=3600)

    def compile(self, name, refs=()):
        folder = self.prefix / 'drive_c/amazing-compat'; folder.mkdir(parents=True, exist_ok=True)
        source = self.assets / (name + '.cs'); shutil.copyfile(source, folder / source.name)
        exe = folder / (name + '.exe'); exe.unlink(missing_ok=True)
        csc = self.prefix / 'drive_c/windows/Microsoft.NET/Framework/v4.0.30319/csc.exe'
        self.run('compile-' + name, csc, '/nologo', '/platform:x86', *('/r:' + x for x in refs),
                 '/out:C:\\amazing-compat\\' + name + '.exe', 'C:\\amazing-compat\\' + name + '.cs')
        if not exe.is_file(): raise ValueError('Компилятор не создал ' + name + '; см. журнал')
        return exe

    def ensure_base(self):
        subprocess.run(['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub', 'https://dl.flathub.org/repo/flathub.flatpakrepo'], check=True)
        if subprocess.run(['flatpak', 'info', APP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['flatpak', 'install', '--user', '-y', 'flathub', APP], check=True)
        if not (self.runner / 'proton').is_file():
            # An already verified Arizona runtime may be read, but is never modified.
            shared = self.home / '.local/share/linux-arizona-rp/runners' / self.spec['proton']['directory']
            source_dll = shared / 'files/lib/wine/dxvk/i386-windows/d3d9.dll'
            if source_dll.is_file() and digest(source_dll) == self.spec['dxvk_source_sha256']: self.runner = shared
            else:
                if self.runner.exists(): raise ValueError('Неполный Proton; выберите другой каталог или восстановите его')
                archive = fetch(self.spec['proton'], self.cache / 'proton.tar.gz'); self.runner.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=self.runner.parent) as tmp:
                    with tarfile.open(archive) as tf:
                        if not hasattr(tarfile, 'data_filter'): raise ValueError('Нужен Python с безопасным tarfile.data_filter')
                        tf.extractall(tmp, filter='data')
                    shutil.move(str(Path(tmp) / self.spec['proton']['directory']), self.runner)
        if not self.umu.is_file() or digest(self.umu) != self.spec['umu']['sha256']:
            sources = [self.home / '.local/share/linux-arizona-rp/umu-run', self.home / '.var/app' / APP / 'data/faugus-launcher/umu-run']
            existing = next((p for p in sources if p.is_file() and digest(p) == self.spec['umu']['sha256']), None)
            if existing: self.umu.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(existing, self.umu)
            else: fetch(self.spec['umu'], self.umu)
        self.umu.chmod(0o700)

    def native_components(self):
        if not (self.prefix / 'system.reg').is_file(): self.run('initialize-prefix', 'cmd.exe', '/c', 'exit', '0')
        for verb in missing_verbs(self.prefix, ['dotnet48', 'vcrun2022', 'd3dx9_25', 'd3dx9_43', 'd3dcompiler_43', 'win10']):
            self.run('component-' + verb, 'winetricks', '-q', verb)
        reg = self.prefix / 'drive_c/amazing-compat/tls.reg'; reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text('Windows Registry Editor Version 5.00\n\n' + '\n'.join('[HKEY_LOCAL_MACHINE\\SOFTWARE\\' + view + 'Microsoft\\.NETFramework\\v4.0.30319]\n"SchUseStrongCrypto"=dword:00000001\n"SystemDefaultTlsVersions"=dword:00000001\n' for view in ['', 'Wow6432Node\\']))
        self.run('tls', 'reg.exe', 'import', 'C:\\amazing-compat\\tls.reg')
        exe = self.compile('RuntimeProbe'); (self.prefix / 'drive_c/amazing-compat/runtime-probe.txt').unlink(missing_ok=True); self.run('verify-native-dotnet', exe)
        result = self.prefix / 'drive_c/amazing-compat/runtime-probe.txt'
        if not result.is_file() or not result.read_text().startswith('NATIVE_CLR_OK'): raise ValueError('Native .NET не подтверждён')

    def cabextract(self, archive, target, member=None):
        target.mkdir(parents=True, exist_ok=True)
        binary = self.runner / 'protonfixes/files/bin/cabextract'
        if not binary.is_file(): raise ValueError('В проверенном Proton нет cabextract')
        args = [str(binary), '-q', '-d', str(target)]
        if member: args += ['-F', member]
        args.append(str(archive))
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)

    def powershell(self):
        print('PowerShell 5.1: извлечение подписанных сборок Microsoft', flush=True)
        folder = self.cache / 'wmf51'; folder.mkdir(parents=True, exist_ok=True)
        archive = fetch(self.spec['wmf51'], folder / 'Win7-KB3191566-x86.zip')
        safe_zip_extract(archive, folder / 'zip')
        msu = next((folder / 'zip').rglob('Win7-KB3191566-x86.msu'), None)
        if msu is None: raise ValueError('WMF MSU не найден')
        self.cabextract(msu, folder / 'msu')
        cab = folder / 'msu/Windows6.1-KB3191566-x86.cab'
        if not cab.is_file(): raise ValueError('WMF CAB не найден')
        self.cabextract(cab, folder / 'payload')
        plan = delta_plan(folder / 'payload', ASSEMBLIES)
        sp1 = fetch(self.spec['sp1_extraction_only'], folder / 'win7sp1-x86.exe')
        self.cabextract(sp1, folder / 'sp1', self.spec['msdelta']['member'])
        delta_dll = folder / 'sp1' / self.spec['msdelta']['member']
        if digest(delta_dll) != self.spec['msdelta']['sha256']: raise ValueError('Повреждена библиотека извлечения MSDelta')
        win = self.prefix / 'drive_c/amazing-compat'; tools = win / 'tools'; tools.mkdir(exist_ok=True)
        shutil.copyfile(delta_dll, tools / 'msdelta.dll')
        wmf = win / 'wmf'; (wmf / 'delta').mkdir(parents=True, exist_ok=True); (wmf / 'decoded').mkdir(exist_ok=True)
        jobs = []
        for item in plan:
            shutil.copyfile(item['delta'], wmf / 'delta' / (item['id'] + '.delta'))
            basis = 'C:/amazing-compat/wmf/decoded/' + item['basis'] + '.bin' if item['basis'] else '-'
            jobs.append(basis + '|C:/amazing-compat/wmf/delta/' + item['id'] + '.delta|C:/amazing-compat/wmf/decoded/' + item['id'] + '.bin')
        (win / 'decode-jobs.txt').write_text('\n'.join(jobs) + '\n')
        exe = self.compile('DeltaDecode'); self.run('decode-wmf', exe, 'C:\\amazing-compat\\decode-jobs.txt')
        install = []
        for item in plan:
            path = wmf / 'decoded' / (item['id'] + '.bin')
            if not path.is_file() or digest(path) != item['sha256']: raise ValueError('Не совпала Microsoft CIX SHA-256: ' + item['name'])
            if item['selected']:
                shutil.copyfile(path, wmf / item['name']); install.append('C:\\amazing-compat\\wmf\\' + item['name'])
        (win / 'gac-files.txt').write_text('\n'.join(install) + '\n')
        exe = self.compile('InstallPowerShellGac', refs=('System.EnterpriseServices.dll',)); (win / 'gac-result.txt').unlink(missing_ok=True); self.run('install-gac', exe)
        result = win / 'gac-result.txt'
        if not result.is_file() or result.read_text().count('INSTALLED ') != len(install): raise ValueError('Не подтверждена установка всех GAC-сборок')
        exe = self.compile('PowerShellProbe'); (win / 'powershell-result.txt').unlink(missing_ok=True); self.run('verify-powershell', exe)
        result = win / 'powershell-result.txt'
        if not result.is_file() or not result.read_text().startswith('OK\n5.1.'): raise ValueError('PowerShell 5.1 не прошёл проверку')

    def launcher(self, local=None):
        candidates = [self.prefix / 'drive_c/Games/AmazingLauncher/AmazingUpdater.exe',
                      self.prefix / 'drive_c/Games/Amazing Launcher/AmazingUpdater.exe']
        found = next((p for p in candidates if p.is_file()), None)
        if not found:
            setup = Path(local).expanduser().resolve() if local else fetch(self.spec['launcher'], self.cache / 'AmazingSetup.exe')
            with setup.open('rb') as stream:
                if stream.read(2) != b'MZ': raise ValueError('Выбранный установщик не является Windows EXE')
            atomic_json(self.state / 'launcher-source.json', {'source': 'explicit-local' if local else self.spec['launcher']['url'], 'sha256': digest(setup)})
            if local:
                dest = self.cache / 'AmazingSetup.exe'
                if setup != dest: shutil.copyfile(setup, dest)
                setup = dest
            print('Официальный установщик. Если откроется лаунчер, закройте его, чтобы завершить настройку.', flush=True)
            self.run('official-setup', setup, '/S', '/D=C:\\Games\\AmazingLauncher')
            found = next((p for p in candidates if p.is_file()), None)
        if found is None: raise ValueError('Официальный установщик не создал AmazingUpdater.exe; см. журнал')
        service = found.parent / 'AmazingService/AmazingService.exe'
        if not service.is_file():
            updater = found.parent / 'AmazingServiceUpdater.exe'
            if updater.is_file(): self.run('official-service-update', updater)
            if not service.is_file(): raise ValueError('Официальный updater не создал AmazingService; см. журнал official-service-update')
        # Use the real installed service; never replace service code or disable signature validation.
        registry = (self.prefix / 'system.reg').read_text(errors='replace')
        if not re.search(r'Services\\\\AmazingService\]', registry):
            winpath = 'C:\\' + str(service.relative_to(self.prefix / 'drive_c')).replace('/', '\\')
            self.run('register-service', 'sc.exe', 'create', 'AmazingService', 'binPath=', winpath, 'start=', 'auto')
        exe = self.compile('ServiceProbe', refs=('System.ServiceProcess.dll',)); (self.prefix / 'drive_c/amazing-compat/service-probe.txt').unlink(missing_ok=True); self.run('verify-service', exe)
        result = self.prefix / 'drive_c/amazing-compat/service-probe.txt'
        if not result.is_file() or not result.read_text().startswith('RUNNING'): raise ValueError('AmazingService не запустилась; см. журнал')
        return found

    def build_compat(self):
        self.meta.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ['build-shell32-forwarder-compat.py', 'build-d3d9-vtable-locator.py']:
            subprocess.run([sys.executable, str(self.assets / name), '--runner', str(self.runner),
                            '--output-dir', str(self.cache), '--state-dir', str(self.meta)], check=True)
        self.wait_closed()
        target = self.prefix / 'drive_c/windows/syswow64/shell32.dll'
        meta = self.meta / 'shell32-forwarder-compat'; info = json.loads((meta / 'build.json').read_text())
        if digest(target) not in [info['original_sha256'], info['compat_sha256']]: raise ValueError('Неизвестная версия prefix shell32')
        if not (meta / 'prefix-backup.json').exists():
            if digest(target) != info['original_sha256']: raise ValueError('Нет исходной копии shell32 для отката')
            self.save(target)
            if not target.is_symlink(): shutil.copyfile(target, meta / 'prefix-original.dll')
            atomic_json(meta / 'prefix-backup.json', {'path': str(target), 'symlink_target': os.readlink(target) if target.is_symlink() else None})
        if digest(target) != info['compat_sha256']:
            target.unlink(); shutil.copyfile(self.cache / 'shell32-forwarder-compat.dll', target)
        if self.compat_runner.exists():
            actual = self.compat_runner / 'files/lib/wine/dxvk/i386-windows/d3d9.dll'
            wanted = json.loads((self.meta / 'd3d9-vtable-locator/build.json').read_text())['compat_sha256']
            if not actual.is_file() or digest(actual) != wanted or not (self.compat_runner / 'proton').is_file():
                raise ValueError('Существующий runner изменён; автоматическая перезапись запрещена')
        else:
            self.compat_runner.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.compat_runner.parent, prefix='amazing-overlay-') as temp:
                overlay_root = Path(temp) / 'runner'; overlay_root.mkdir()
                def overlay(source, dest, remaining):
                    for p in source.iterdir():
                        out = dest / p.name
                        if remaining and p.name == remaining[0]:
                            if len(remaining) == 1: shutil.copyfile(self.cache / 'd3d9-vtable-locator.dll', out)
                            else: out.mkdir(); overlay(p, out, remaining[1:])
                        elif dest == overlay_root and p.name == 'proton': shutil.copy2(p, out)
                        elif p.name != '__pycache__': out.symlink_to(p, target_is_directory=p.is_dir())
                overlay(self.runner, overlay_root, ('files', 'lib', 'wine', 'dxvk', 'i386-windows', 'd3d9.dll'))
                overlay_root.rename(self.compat_runner)
        target = self.prefix / 'drive_c/windows/syswow64/d3d9.dll'; meta = self.meta / 'd3d9-vtable-locator'
        info = json.loads((meta / 'build.json').read_text())
        if not (meta / 'prefix-backup.json').exists():
            if digest(target) != info['original_sha256']: raise ValueError('Нет исходной D3D9 для отката')
            self.save(target); shutil.copyfile(target, meta / 'prefix-original.dll')
            atomic_json(meta / 'prefix-backup.json', {'path': str(target), 'was_symlink': target.is_symlink(), 'symlink_target': os.readlink(target) if target.is_symlink() else None})
        self.debug_config()
        for name, marker in [('CommandLineForwarderProbe', 'commandline-forwarder-probe.txt'), ('D3D9LocatorProbe', 'd3d9-locator-probe.txt')]:
            exe = self.compile(name)
            (self.prefix / 'drive_c/amazing-compat' / marker).unlink(missing_ok=True)
            self.run('verify-' + name, exe, runner=self.compat_runner, overrides='shell32=n,b')
            result = self.prefix / 'drive_c/amazing-compat' / marker
            if not result.is_file() or 'ALL_PASS' not in result.read_text(): raise ValueError('Проверка совместимости не прошла: ' + name)

    def wait_closed(self):
        deadline = time.monotonic() + 20
        while busy_prefix(self.prefix):
            if time.monotonic() > deadline: raise ValueError('Префикс остаётся активным: закройте лаунчер перед следующим этапом')
            time.sleep(.25)

    def debug_config(self):
        path = self.prefix / 'user.reg'; self.save(path)
        text = path.read_text(); key = r'[Software\\Wine\\Debug]'; start = text.find(key)
        section = ''; end = start
        if start >= 0:
            end = text.find('\n[', start + 1); end = end if end >= 0 else len(text); section = text[start:end]
        backup = self.meta / 'debug-before-20261109-matrix.json'
        if not backup.exists(): atomic_json(backup, {'key': key, 'section': section})
        replace = key + '\n"RelayInclude"="ntdll.RtlAllocateHeap;ntdll.ZwQueryInformationProcess"\n"RelayFromInclude"="aggmain.asi"\n'
        path.write_text(text[:start] + replace + text[end:] if start >= 0 else text.rstrip() + '\n\n' + replace)

    def shortcuts(self, launcher):
        installed = self.data / 'compat-20261109'; installed.mkdir(parents=True, exist_ok=True)
        for name in ['run.py', 'screen.py', 'restore.py', 'stop-test-prefix.py', 'README.md']:
            target = installed / name; self.save(target); shutil.copyfile(self.assets / name, target)
        cfg = {'schema': 1, 'prefix': str(self.prefix), 'runner': str(self.compat_runner), 'umu': str(self.umu),
               'launcher': str(launcher), 'metadata': str(self.meta), 'workspace': 1, 'source_runner': str(self.runner)}
        atomic_json(self.meta / 'runtime.json', cfg)
        target = self.data / 'settings.json'; self.save(target); atomic_json(target, cfg)
        binroot = self.home / '.local/bin'; binroot.mkdir(parents=True, exist_ok=True)
        for source, name in [('launch.py', 'amazing-compat'), ('amazing', 'amazing')]:
            target = binroot / name; self.save(target); shutil.copyfile(self.assets / source, target); target.chmod(0o700)
        desktop = self.home / '.local/share/applications/linux-amazing-rp.desktop'; self.save(desktop); desktop.parent.mkdir(parents=True, exist_ok=True)
        # Desktop Exec grammar is not shell grammar; quote and escape only its documented metacharacters.
        exe = str(binroot / 'amazing').replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
        desktop.write_text('[Desktop Entry]\nVersion=1.0\nType=Application\nName=Amazing RP\nComment=Установка и запуск Amazing Online на Linux\nExec="' + exe + '"\nIcon=applications-games\nTerminal=false\nCategories=Game;\nStartupNotify=false\n')
        print('Ярлык Amazing RP и команда amazing готовы.', flush=True)

    def install(self, local=None, no_shortcuts=False):
        if busy_prefix(self.prefix): raise ValueError('Закройте Amazing и его лаунчер перед установкой; другие префиксы не затрагиваются')
        ready = self.checked_existing_profile()
        if self.prefix.exists() and not ready and not self.marker.exists():
            raise ValueError('Найден существующий неподготовленный префикс. Он сохранён. Выберите новый --prefix ~/Games/amazing-rp/<имя>')
        if self.marker.exists():
            ownership = json.loads(self.marker.read_text())
            if ownership.get('schema') != 1 or ownership.get('prefix') != str(self.prefix): raise ValueError('Не совпал маркер владельца префикса')
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700); self.cache.mkdir(parents=True, exist_ok=True)
        with (self.state / 'installer.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.backup = self.state / 'backups' / ('installer-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            if ready:
                print('Найден рабочий профиль: компоненты и данные сохраняются.', flush=True)
                existing = self.data / 'settings.json'
                if existing.is_file():
                    settings = json.loads(existing.read_text()); self.umu = Path(settings['umu']); self.runner = Path(settings.get('source_runner', str(self.runner)))
                else:
                    legacy = self.home / '.local/share/linux-arizona-rp/umu-run'
                    if legacy.is_file(): self.umu = legacy
                    legacy = self.home / '.local/share/linux-arizona-rp/runners' / self.spec['proton']['directory']
                    if legacy.is_dir(): self.runner = legacy
                self.shortcuts(self.detected_launcher) if not no_shortcuts else None
                return
            self.ensure_base(); self.prefix.mkdir(parents=True, exist_ok=True)
            atomic_json(self.marker, {'schema': 1, 'prefix': str(self.prefix), 'complete': False})
            self.native_components(); self.powershell(); launcher = self.launcher(local); self.wait_closed(); self.build_compat()
            if not no_shortcuts: self.shortcuts(launcher)
            atomic_json(self.marker, {'schema': 1, 'prefix': str(self.prefix), 'complete': True})
            print('Готово. Откройте Amazing RP → дождитесь загрузки клиента в официальном лаунчере → выберите сервер.', flush=True)


def parser():
    p = argparse.ArgumentParser(description='Установка Amazing Online на Linux: окружение, лаунчер, совместимость, ярлык')
    p.add_argument('--prefix', type=Path, default=Path.home() / 'Games/amazing-rp/ge11-clean-prefix')
    p.add_argument('--no-shortcuts', action='store_true', help='подготовить отдельный тестовый профиль без изменения основной команды запуска')
    p.add_argument('--installer', type=Path, help='свой официальный AmazingSetup.exe')
    p.add_argument('--check', action='store_true', help='диагностика без изменений')
    p.add_argument('--plan', action='store_true', help='показать план без изменений')
    p.add_argument('--yes', action='store_true', help='подтвердить действия')
    p.add_argument('--no-system-packages', action='store_true', help='системные пакеты уже подготовлены')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if platform.system() != 'Linux' or platform.machine() not in ['x86_64', 'AMD64']: raise ValueError('Нужен Linux x86_64')
    setup = Setup(args.prefix)
    if args.check:
        print(json.dumps(setup.status(), ensure_ascii=False, indent=2)); return 0
    print('AMAZING ONLINE / LINUX — установка игры и подготовка запуска')
    print('Префикс: ' + str(setup.prefix))
    print('Faugus → GE-Proton 11-11 → native .NET / VC++ / DX9 → PowerShell 5.1 → официальный лаунчер → совместимость → ярлык')
    print('Файлы клиента скачивает официальный лаунчер. Пароль и сервер выбираете вы.')
    if args.plan: return 0
    if os.geteuid() == 0: raise ValueError('Запускайте без sudo; системные пакеты устанавливает bootstrap')
    if not os.environ.get('DISPLAY'): raise ValueError('Запустите установщик из графической сессии X11/Xwayland')
    if not args.yes:
        if not sys.stdin.isatty() or input('Начать установку? [y/N] ').lower() not in ['y', 'yes', 'да']: return 0
    setup.install(args.installer, args.no_shortcuts); return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, ET.ParseError) as error:
        raise SystemExit('Ошибка установки: ' + str(error) + '\nДанные не очищаются. Журналы: ~/.local/state/linux-amazing-rp/install-logs/')
