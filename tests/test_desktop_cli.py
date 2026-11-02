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


def test_joint_validation_cli_requires_explicit_input_and_loads_recipe(tmp_path,monkeypatch):
    from efospec.__main__ import main
    from efospec import joint_validation
    calls=[]
    monkeypatch.setattr(joint_validation,'save_validation',lambda *a,**k:calls.append((a,k)) or
                        {'conditional_tests_passed':True,'science_validated':False})
    with pytest.raises(SystemExit) as missing_product:
        main(['validate-joint','--output',str(tmp_path/'unused'),'--run','night'])
    with pytest.raises(SystemExit) as missing_run:
        main(['validate-joint','--output',str(tmp_path/'unused'),'--product','spectrum.fits'])
    assert missing_product.value.code==missing_run.value.code==2
    assert calls==[] and not (tmp_path/'unused').exists()
    recipe=tmp_path/'recipe.json';recipe.write_text(json.dumps({'objects':[{'id':'primary'},{'id':'companion'}]}))
    assert main(['validate-joint','--output',str(tmp_path/'result'),'--run','night',
                 '--product','spectrum.fits','--recipe',str(recipe)])==0
    assert calls[0][1]['recipe']==json.loads(recipe.read_text())


def test_gui_disposes_window_before_application_shutdown(monkeypatch,qtbot):
    from efospec import desktop
    from shiboken6 import isValid
    windows=[]
    original=desktop.ExtractionWindow
    class ObservedWindow(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);windows.append(self)
    monkeypatch.setattr(desktop,'ExtractionWindow',ObservedWindow)
    assert desktop.launch(smoke_test=True)==0
    assert len(windows)==1
    assert not isValid(windows[0])
