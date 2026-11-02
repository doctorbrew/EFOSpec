import json
from pathlib import Path
import plistlib
import subprocess
import sys

import pytest

from efospec.desktop_install import install_desktop, probe_runtime


@pytest.mark.parametrize('platform', ['darwin', 'linux'])
def test_environment_bound_launcher_opens_native_window(tmp_path, platform):
    pytest.importorskip('PySide6')
    # Spaces and shell metacharacters must remain ordinary path characters.
    destination=tmp_path/'Apps with spaces $safe'
    result=install_desktop(destination,platform=platform)
    assert result['runtime']['python']==sys.executable
    assert not result['runtime_bundled'] and not result['signed']
    if platform=='darwin':
        with (Path(result['application'])/'Contents/Info.plist').open('rb') as stream:
            assert plistlib.load(stream)['CFBundleExecutable']=='EFOSpec'
    else:
        entry=Path(result['application'])/'org.efospec.Desktop.desktop'
        assert 'Terminal=false' in entry.read_text()
        assert 'Exec="' in entry.read_text()
    completed=subprocess.run([result['executable'],'--smoke-test'],capture_output=True,text=True,timeout=45)
    assert completed.returncode==0,completed.stderr
    record=json.loads(completed.stdout.splitlines()[-1])
    assert record['ready'] and record['tabs']==2
    assert record['qt_platform'] in {'cocoa','xcb','offscreen'}
    before=Path(result['executable']).read_bytes()
    with pytest.raises(FileExistsError):install_desktop(destination,platform=platform)
    assert Path(result['executable']).read_bytes()==before


def test_invalid_runtime_and_unsupported_platform_create_no_launcher(tmp_path):
    bad=tmp_path/'bad-python'
    bad.write_text('#!/bin/sh\nprintf "missing desktop dependencies" >&2\nexit 1\n');bad.chmod(0o755)
    with pytest.raises(ValueError,match='missing desktop dependencies'):
        install_desktop(tmp_path/'apps',python=bad,platform='linux')
    assert not (tmp_path/'apps').exists()
    with pytest.raises(ValueError,match='macOS and Linux'):
        install_desktop(tmp_path/'apps',platform='win32')


def test_linux_menu_registration_uses_user_data_directory(tmp_path,monkeypatch):
    import efospec.desktop_install as installer
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'share'))
    monkeypatch.setattr(installer,'probe_runtime',lambda python:{'python':str(python)})
    result=installer.install_desktop(platform='linux')
    entry=Path(result['menu_entry'])
    assert entry.parent==tmp_path/'share/applications'
    assert Path(result['executable']).is_file()
    assert str(Path(result['application'])/'efospec.png') in entry.read_text()
