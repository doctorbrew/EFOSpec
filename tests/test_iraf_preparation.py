"""IRAF preparation shares the project run root without mixing engines."""
from pathlib import Path
import shutil
import subprocess
import sys


def test_prepare_defaults_preserve_raw_and_efosc_outputs(tmp_path):
    project=tmp_path/'EFOSpec';manual=project/'scripts';manual.mkdir(parents=True)
    source=Path(__file__).resolve().parents[1]/'scripts'
    for name in ('prepare_iraf.py','list_raw_frames.py'):
        shutil.copy2(source/name,manual/name)
    raw=project/'data/2024-11-14';raw.mkdir(parents=True)
    frame=raw/'EFOSC.test.fits';frame.write_bytes(b'raw bytes are copied without rewriting')
    efosc=project/'runs/2024-11-14/efospec';efosc.mkdir(parents=True)
    report=efosc/'index.html';report.write_text('existing EFOSpec report')
    for number in (1,2):
        subprocess.run([sys.executable,str(manual/'prepare_iraf.py'),'2024-11-14'],check=True,capture_output=True)
        work=project/'runs/2024-11-14/pyraf'/f'iraf-full-{number:02d}'
        assert (work/frame.name).read_bytes()==frame.read_bytes()
        assert (work/'list_raw_frames.py').is_file()
    assert report.read_text()=='existing EFOSpec report'
    assert frame.read_bytes()==b'raw bytes are copied without rewriting'
    assert not (project/'runs/2024-11-14/pessto').exists()
