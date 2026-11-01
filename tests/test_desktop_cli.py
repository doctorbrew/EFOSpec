from pathlib import Path
import json
import pytest


def test_gui_command_is_native_and_allows_file_picker(monkeypatch):
    pytest.importorskip('PySide6')
    from efospec.__main__ import main
    from efospec import desktop
    calls=[]
    monkeypatch.setattr(desktop,'launch',lambda *args:calls.append(args) or 0)
    assert main(['gui'])==0
    assert calls==[(None,None)]
    assert main(['gui','runs/2024-11-14','--reference-root','ref'])==0
    assert calls[-1]==('runs/2024-11-14','ref')


def test_raw_cli_passes_explicit_positions_and_cache(monkeypatch,capsys):
    from efospec.__main__ import main
    from efospec import native_reduction
    calls=[]
    monkeypatch.setattr(native_reduction,'reduce_pair',lambda *a,**k:calls.append((a,k)) or {'output_dir':'new','results':[{}]})
    assert main(['reduce-native','night','--science','science.fits','--standard','standard.fits',
        '--output','new','--science-position','530','--standard-position','550','--reuse-calibrations','prior','--skip-report'])==0
    assert calls[0][1]==dict(science_position=530.,standard_position=550.,render_report=False,reuse_calibrations='prior')
    assert json.loads(capsys.readouterr().out)['reduced']==1
