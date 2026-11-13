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


def test_native_flux_cannot_promote_failed_wavelength(tmp_path,monkeypatch):
    from efospec.native_recovery import extract_native
    import efospec.revisions as revisions
    from efospec.recipes import DetectorWindow
    e=SimpleNamespace(context=SimpleNamespace(calibration={'mode':'native'},sky_qa={'held_out_6363_pass':False}),window=DetectorWindow((100,201),(0,448)),hashes={k:'a'*64 for k in ('raw','images','manifest')})
    monkeypatch.setattr(revisions,'FailedExposure',lambda *a:e)
    recipe=dict(schema_version=1,engine_version='3.0.0',coordinates='raw_detector_pixels_zero_based',input_sha256=e.hashes,source_mode='manual',objects=[dict(id='primary',label='test',kind='point',spec=50.,spat=548.,radius=7.,fwhm=4.)],sky=dict(mode='polynomial',include=[[500,530],[575,605]],exclude=[],degree=2,sigma_clip=4.))
    with pytest.raises(ValueError,match='wavelength check failed'):extract_native(tmp_path,'raw.fits',recipe,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_manual_recovery_selection_rejects_changed_manifest(tmp_path):
    from efospec.manual_recovery_report import selected_manual_recoveries
    parent=tmp_path/'reduction';parent.mkdir();(parent/'run.json').write_text('{}')
    qc=tmp_path/'QC';qc.mkdir();trial=qc/'trial';trial.mkdir();manifest=trial/'run.json';manifest.write_text('{}')
    (qc/'manual-recovery-selection.json').write_text(json.dumps({'parent_sha256':sha256(parent/'run.json'),'runs':[{'path':str(trial),'sha256':{str(manifest):sha256(manifest)}}]}))
    manifest.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='product changed'):selected_manual_recoveries(parent)


@pytest.mark.parametrize('change',[None,'raw','product','wavelength'])
def test_manual_recovery_report_accepts_only_bound_supported_products(tmp_path,change):
    from efospec.manual_recovery_report import selected_manual_recoveries
    parent=tmp_path/'reduction';parent.mkdir();(parent/'run.json').write_text('{}')
    trial=tmp_path/'QC/trial';trial.mkdir(parents=True)
    raw=tmp_path/'raw.fits';raw.write_bytes(b'raw')
    product=trial/'flux.fits';product.write_bytes(b'flux')
    native=trial/'spec1d.fits';native.write_bytes(b'native')
    result=dict(raw=str(raw),raw_sha256=sha256(raw),product=str(product),native_spec1d=str(native),
                sky_flexure={'held_out_6363_pass':change!='wavelength'})
    manifest=trial/'run.json'
    manifest.write_text(json.dumps(dict(parent_sha256=sha256(parent/'run.json'),execution_status='complete',results=[result])))
    (tmp_path/'QC/manual-recovery-selection.json').write_text(json.dumps(dict(
        parent_sha256=sha256(parent/'run.json'),runs=[dict(path=str(trial),
        sha256={str(p):sha256(p) for p in (manifest,product,native)})])))
    if change in ('raw','product'):
        (raw if change=='raw' else product).write_bytes(b'changed')
    if change:
        with pytest.raises(ValueError,match={'raw':'raw changed','product':'product changed','wavelength':'wavelength check failed'}[change]):
            selected_manual_recoveries(parent)
    else:
        selected=selected_manual_recoveries(parent)
        assert selected[0][0]==trial and selected[0][1]['results']==[result]


@pytest.mark.parametrize('valid_fraction',[0.,.9])
def test_native_flux_export_requires_supported_response_and_records_failures(tmp_path,monkeypatch,valid_fraction):
    from efospec.native_recovery import extract_native
    from efospec.recipes import DetectorWindow
    import efospec.revisions as revisions
    run=tmp_path/'parent';run.mkdir();(run/'run.json').write_text('{}');group=run/'calibration.json';group.write_text('{}')
    frame={'path':'/raw/test.fits','sha256':'a'*64};associations={'arc':{},'flat':{},'bias':{}}
    (run/'setup-checks.json').write_text(json.dumps({'exposures':[{'path':frame['path'],'raw_calibrations':associations}]}))
    hashes={k:'a'*64 for k in ('raw','images','manifest')};hashes['calibration']=sha256(group)
    e=SimpleNamespace(run=run,frame=frame,result={'object':'test'},window=DetectorWindow((100,201),(0,448)),images={'found_traces':np.full((1,100),100.)},hashes=hashes,context=SimpleNamespace(calibration={'mode':'native'},sky_qa={'held_out_6363_pass':True}),manifest={'night':'2026-10-28','input_dir':'/raw','standards':[]})
    monkeypatch.setattr(revisions,'FailedExposure',lambda *a:e)
    response={'path':'response.fits','extinction':{}}
    monkeypatch.setattr('efospec.daily_reduction.select_response',lambda *a:dict(fit={'response':response},calibration={'raw_inputs':{}},counts={'calibration_directory':str(run)}))
    def prepare(frame,assoc,output,position,**kw):
        assert kw['reviewed_source']['identity']['method']=='operator_background'
        assert kw['spatial_half_width']==100 and position==548.
        return dict(bundle={'record':{'raw_inputs':{}}},detector={},data=np.ones((100,201)),waveair=np.ones((100,201)),xlo=448,ylo=0,engine={'source_selection':{}},arc={},shift=0.,sky={'held_out_6363_pass':True},processed={},basename='test')
    monkeypatch.setattr('efospec.native_reduction.prepare',prepare)
    def export(context,*args,**kwargs):
        assert context.hint_info['association']=='UNVERIFIED_manual_background_recovery'
        assert context.calibration['mode']=='native_raw_only'
        return {'valid_flux_fraction':valid_fraction}
    monkeypatch.setattr('efospec.products.export_spectrum',export)
    monkeypatch.setattr('efospec.run_record.snapshot_sources',lambda p:{})
    recipe=dict(schema_version=1,engine_version='3.0.0',coordinates='raw_detector_pixels_zero_based',input_sha256=hashes,source_mode='manual',objects=[dict(id='primary',label='test',kind='point',spec=50.,spat=548.,radius=7.,fwhm=4.)],sky=dict(mode='polynomial',include=[[500,530],[575,605]],exclude=[],degree=2,sigma_clip=4.))
    if valid_fraction:
        result=extract_native(run,'test.fits',recipe,tmp_path/'output');assert result['results'][0]['role']=='science'
    else:
        with pytest.raises(ValueError,match='supported calibrated flux'):extract_native(run,'test.fits',recipe,tmp_path/'output')
        saved=json.loads((tmp_path/'output/run.json').read_text());assert saved['execution_status']=='failed' and not saved['results']
    assert recipe['sky']['mode']=='polynomial'  # caller's saved recipe stays unchanged
