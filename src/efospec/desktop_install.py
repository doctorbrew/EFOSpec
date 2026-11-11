"""Install desktop launchers bound to one verified EFOSpec environment.

The scientific runtime is deliberately not copied into an application bundle.
The selected editable checkout and Python environment must remain installed.
"""
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys


def probe_runtime(python):
    code = '''import json, sys
from pathlib import Path
from importlib.metadata import version
import efospec, PySide6
root = Path(efospec.__file__).resolve().parents[2]
assert (root / 'plot_style.py').is_file(), 'Install EFOSpec from its checkout with pip install -e .'
assert (root / 'trunk/src/ntt').is_dir(), 'The EFOSpec reference directory is missing'
assert version('pypeit') == '3.0.0', 'This release requires PypeIt 3.0.0'
from efospec import desktop, background_gui
print(json.dumps(dict(python=sys.executable, version=sys.version.split()[0],
    source=str(root), pypeit=version('pypeit'), qt=version('PySide6-Essentials'))))
'''
    result = subprocess.run([str(python), '-c', code], text=True, capture_output=True,
                            timeout=60, env={k:v for k,v in os.environ.items() if k not in {'PYTHONHOME','PYTHONPATH'}})
    if result.returncode:
        raise ValueError('The selected EFOSpec environment is not ready:\n'+result.stderr[-3000:])
    return json.loads(result.stdout.splitlines()[-1])


def _desktop_string(value):
    # Desktop-entry string escaping is distinct from shell quoting.
    return str(value).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')


def _exec_argument(value):
    value = str(value).replace('%','%%')
    quoted = '"'+''.join('\\'+c if c in '\\"`$' else c for c in value)+'"'
    return _desktop_string(quoted)


def install_desktop(destination=None, *, platform=None, python=None):
    platform = platform or sys.platform
    if platform not in {'darwin', 'linux'}:
        raise ValueError('Desktop launchers support macOS and Linux.')
    # Do not resolve the interpreter symlink: that would discard its venv.
    python = Path(python or sys.executable).expanduser().absolute()
    runtime = probe_runtime(python)
    default = destination is None
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    base = Path(destination).expanduser().absolute() if destination else (
        Path.home()/'Applications' if platform == 'darwin' else data_home/'efospec')
    target = base/('EFOSpec.app' if platform == 'darwin' else 'EFOSpec')
    menu = data_home/'applications/org.efospec.Desktop.desktop' if platform == 'linux' and default else None
    if target.exists() or target.is_symlink() or (menu and (menu.exists() or menu.is_symlink())):
        raise FileExistsError('An EFOSpec launcher already exists; choose another destination or remove the old launcher first.')
    target.mkdir(parents=True, exist_ok=False)
    try:
        resources = target/'Contents/Resources' if platform == 'darwin' else target
        resources.mkdir(parents=True, exist_ok=True)
        icon = resources/'efospec.png'
        shutil.copyfile(Path(__file__).parent/'assets/efospec-mark.png', icon)
        (resources/'runtime.json').write_text(json.dumps(runtime, indent=2)+'\n')
        executable = target/'Contents/MacOS/EFOSpec' if platform == 'darwin' else target/'efospec-desktop'
        executable.parent.mkdir(parents=True, exist_ok=True)
        search = [str(python.parent)]
        for tool in ('latex','dvipng'):
            located = shutil.which(tool)
            if located and str(Path(located).parent) not in search:search.append(str(Path(located).parent))
        executable.write_text('#!/bin/sh\n'
            '# Use the selected environment, including when launched from Finder.\n'
            'unset PYTHONHOME PYTHONPATH\n'
            'export QT_API=pyside6 MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1\n'
            'export PATH='+shlex.quote(':'.join(search))+':"${PATH:-/usr/bin:/bin}"\n'
            'exec '+shlex.quote(str(python))+' -m efospec gui "$@"\n')
        executable.chmod(0o755)
        if platform == 'darwin':
            info = dict(CFBundleName='EFOSpec', CFBundleDisplayName='EFOSpec',
                        CFBundleIdentifier='org.efospec.Desktop', CFBundlePackageType='APPL',
                        CFBundleExecutable='EFOSpec', CFBundleShortVersionString='0.1.0',
                        CFBundleVersion='1', NSHighResolutionCapable=True,
                        CFBundleURLTypes=[dict(CFBundleURLName='EFOSpec review', CFBundleURLSchemes=['efospec'])])
            if sys.platform == 'darwin':
                # Native format conversion for the bundle icon; preserve the source PNG.
                resized = resources/'icon-512.png'
                subprocess.run(['sips','-z','512','512',str(icon),'--out',str(resized)],check=True,capture_output=True)
                subprocess.run(['sips','-s','format','icns',str(resized),'--out',str(resources/'efospec.icns')],check=True,capture_output=True)
                resized.unlink();info['CFBundleIconFile']='efospec.icns'
            with (target/'Contents/Info.plist').open('wb') as stream:plistlib.dump(info,stream)
        else:
            entry = ('[Desktop Entry]\nType=Application\nName=EFOSpec\n'
                'Comment=EFOSC2 spectra and source review\nTerminal=false\n'
                'Categories=Science;Astronomy;\nMimeType=x-scheme-handler/efospec;\n'
                'Exec='+_exec_argument(executable)+' %u\n'
                'Icon='+_desktop_string(icon)+'\n')
            (target/'org.efospec.Desktop.desktop').write_text(entry)
            if menu:
                menu.parent.mkdir(parents=True, exist_ok=True)
                with menu.open('x') as stream:stream.write(entry)
        return {'platform':platform,'application':str(target),'executable':str(executable),
                'menu_entry':str(menu) if menu else None,'runtime':runtime,
                'runtime_bundled':False,'signed':False}
    except Exception:
        shutil.rmtree(target)
        raise
