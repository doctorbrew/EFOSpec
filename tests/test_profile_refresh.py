"""Profile-only presentation refreshes preserve science and companion plots."""
import json
from pathlib import Path

import numpy as np
import pytest

from efospec.inventory import sha256
from scripts import preview_spectrum_style as renderer


@pytest.fixture
def saved_profile(tmp_path, monkeypatch):
    run=tmp_path/'reduction';run.mkdir()
    folder=tmp_path/'comparison/style-preview';folder.mkdir(parents=True)
    product=run/'spectrum.fits';product.write_bytes(b'original spectrum')
    images=run/'images.npz';images.write_bytes(b'original detector arrays')
    outputs=[]
    for prefix in ('FitSpectrum_', 'FitTrace_', 'FitSpatialProfile_'):
        for suffix in ('.pdf','.jpg'):
            path=folder/(prefix+'SNtest_slit1.5'+suffix)
            path.write_bytes(path.name.encode());outputs.append(path)
    record=dict(product=str(product),outputs=list(map(str,outputs)),
        input_sha256={str(p):sha256(p) for p in (product,images)},
        output_sha256={str(p):sha256(p) for p in outputs},
        telluric_pair={'provenance':'retained'})
    path=folder/'FitSpectrum_SNtest_slit1.5.json';path.write_text(json.dumps(record))
    wave=np.linspace(4000.,7000.,90);x=np.arange(21)
    sky=np.zeros((90,21));signal=50.*np.exp(-.5*((x-10)/2.)**2)
    data=dict(data=sky+signal,sky=sky,waveair=np.broadcast_to(wave[:,None],sky.shape),
        trace=np.full(90,10.),spatial_origin=0,box_radius=3.,
        sky_input_mask=np.broadcast_to(((x>=3)&(x<=6))|((x>=14)&(x<=17)),sky.shape))
    monkeypatch.setattr(renderer,'resolve_result_paths',lambda result,run:result)
    monkeypatch.setattr(renderer,'load_trace_data',lambda result:(data,[images],'saved'))
    monkeypatch.setattr(renderer,'read_flux',lambda product:(wave,None,None))
    def save(fig,stem,**kwargs):
        for suffix in ('.pdf','.jpg'):
            stem.with_name(stem.name+suffix).write_bytes(b'new spatial profile')
    monkeypatch.setattr(renderer,'savefig_light',save)
    result=dict(product=str(product),object='SNtest',grism='Gr13',exptime_s=100.)
    return run,folder,path,record,result,images


def test_refresh_comparison_profiles_updates_hashes_and_retains_previous_plots(saved_profile):
    run,folder,path,original,result,images=saved_profile
    old_record=path.read_bytes();old_hash=sha256(path)
    changed=renderer.refresh_profile(result,run,plot_directory=folder)
    for name,digest in original['input_sha256'].items():
        assert sha256(Path(name))==digest
    for name,digest in original['output_sha256'].items():
        p=Path(name)
        assert changed['output_sha256'][name]==sha256(p)
        if p.name.startswith('FitSpatialProfile_'):
            assert sha256(p)!=digest
            assert sha256(folder/'archive/spatial-profiles'/old_hash/p.name)==digest
        else:assert sha256(p)==digest
    assert (folder/'archive/spatial-profiles'/old_hash/path.name).read_bytes()==old_record
    assert changed['telluric_pair']==original['telluric_pair']
    assert all(b['data_model_ylim'][0]<0 for b in changed['spatial_profile_diagnostics']['bins'])


def test_refresh_rejects_a_plot_from_different_science_inputs(saved_profile):
    run,folder,path,original,result,images=saved_profile
    images.write_bytes(b'changed detector arrays')
    with pytest.raises(ValueError,match='different scientific inputs'):
        renderer.refresh_profile(result,run,plot_directory=folder)
    assert json.loads(path.read_text())==original
    assert not (folder/'archive').exists()
