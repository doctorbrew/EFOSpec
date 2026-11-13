import json
from types import SimpleNamespace
import numpy as np
import pytest
from astropy import units as u
from efospec.inventory import sha256


def test_native_saved_window_verification_and_raw_tampering(tmp_path,monkeypatch):
    from pypeit.core.wave import vactoair
    from efospec import native_calibrations as cal
    from efospec.native_recovery import load_failed
    def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
    raw=tmp_path/'raw.fits';raw.write_bytes(b'raw')
    frame={'path':str(raw),'sha256':sha256(raw),'setup':{'grism':'Gr13'},'metadata':{'OBJECT':'target'}}
    run=tmp_path/'run';assoc={k:{'sha256':[k]} for k in ('bias','flat','arc')}
    save(run/'inputs.json',{'frames':[frame]});save(run/'setup-checks.json',{'exposures':[{'path':str(raw),'raw_calibrations':assoc}]})
    save(run/'group/calibration.json',{'setup':frame['setup'],'associations':assoc})
    data=np.arange(1400,dtype=float).reshape(20,70);wave=np.full(data.shape,6000.)
    path=run/'exposure/native/window.npz';path.parent.mkdir(parents=True)
    np.savez(path,data=data[5:15,10:60],waveair=vactoair(wave[5:15,10:60]*u.AA).value,found_traces=np.full((1,10),25.))
    save(run/'exposure/sky-check.json',{'raw_sha256':frame['sha256'],'shift_angstrom':0.,'held_out_6363_pass':False})
    manifest={'errors':[{'path':str(raw),'diagnostics':{'diagnostic_file':str(path)}}]};save(run/'run.json',manifest)
    bundle={'wavevac':wave,'record':{'wavelength':{'reference_lines_vacuum':[4000.,8000.]}}}
    image=SimpleNamespace(image=data,ivar=np.ones_like(data),rn2img=1.,base_var=1.,img_scale=1.,detector={},fullmask=SimpleNamespace(flagged=lambda:np.zeros_like(data,dtype=bool)))
    monkeypatch.setattr(cal,'load_calibrations',lambda p:bundle);monkeypatch.setattr(cal,'process_exposure',lambda f,b:image)
    e=SimpleNamespace(run=run,manifest=manifest);load_failed(e,raw.name)
    assert e.window.origin==(5,10)
    assert e.candidates==[{'raw_spatial_pixel':35.}]
    raw.write_bytes(b'changed')
    with pytest.raises(ValueError,match='raw input changed'):load_failed(e,raw.name)
