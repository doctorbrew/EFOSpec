"""An operator identification cannot silently migrate to other pixels or recipes."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from efospec.inventory import sha256
from efospec.recipes import DetectorWindow
from efospec.reviewed_sources import load_reviewed_sources, prepare_reviewed_extraction


@pytest.fixture
def reviewed(tmp_path, monkeypatch):
    hashes = {k:str(i)*64 for i,k in enumerate(['raw','images','manifest'])}
    recipe = dict(schema_version=1,engine_version='3.0.0',coordinates='raw_detector_pixels_zero_based',
        input_sha256=hashes,source_mode='manual',objects=[dict(id='primary',label='SN2026ayt_C2_trial',
        kind='point',spec=5.,spat=40.,fwhm=2.,radius=3.)],
        sky=dict(mode='pypeit_local',include=[],exclude=[],width_pixels=30,minimum_width_pixels=15,degree=2,sigma_clip=4.))
    path=tmp_path/'recipe.json';path.write_text(json.dumps(recipe))
    selection=dict(raw_name='raw.fits',raw_sha256=hashes['raw'],object='SN2026ayt',
        identity=dict(candidate=2,method='operator_visual',evidence='Operator matched C2 in acquisition image'),
        recipe_path=str(path),recipe_sha256=sha256(path),parent_run=str(tmp_path/'parent'))
    frame=dict(path=str(tmp_path/'raw.fits'),sha256=hashes['raw'],metadata={'OBJECT':'SN2026ayt'})
    data=np.ones((10,100));wave=np.ones_like(data)*5000
    exposure=SimpleNamespace(hashes=hashes,window=DetectorWindow(data.shape,(0,0)),
        context=SimpleNamespace(data=data,waveair=wave),
        images={'found_traces':np.array([np.full(10,20.),np.full(10,40.),np.full(10,60.)])})
    monkeypatch.setattr('efospec.revisions.FailedExposure',lambda *args:exposure)
    monkeypatch.setattr('efospec.local_sky.exposure_sky_inputs',lambda *args:(np.ones_like(data,bool),np.full(10,40.),{'saved_candidate_index':2}))
    return selection,frame,data,wave,tmp_path


def test_explicit_identification_replays_same_geometry_and_preserves_original_recipe(reviewed):
    selection,frame,data,wave,output=reviewed
    original=sha256(__import__('pathlib').Path(selection['recipe_path']))
    args,identity,background=prepare_reviewed_extraction(selection,frame,data,wave,(0,0),output)
    assert args['manual'][0]['spat']==40.
    assert args['manual'][0]['label']=='SN2026ayt'
    assert identity['association']=='operator_selected' and identity['identity']['candidate']==2
    assert background['saved_candidate_index']==2
    assert sha256(__import__('pathlib').Path(selection['recipe_path']))==original


@pytest.mark.parametrize('change',['raw','pixels','wavelength','origin','candidate','recipe'])
def test_changed_inputs_or_candidate_cannot_reuse_identity(reviewed,change):
    selection,frame,data,wave,output=reviewed
    origin=(0,0)
    if change=='raw':frame['sha256']='f'*64
    if change=='pixels':data=data.copy();data[0,0]+=1
    if change=='wavelength':wave=wave+.1
    if change=='origin':origin=(0,1)
    if change=='candidate':selection['identity']['candidate']=3
    if change=='recipe':selection['recipe_sha256']='f'*64
    with pytest.raises(ValueError):prepare_reviewed_extraction(selection,frame,data,wave,origin,output)
    assert not (output/'reviewed-sources').exists()


def test_selection_requires_matching_selected_exposure_and_visual_evidence(reviewed):
    selection,frame,_,_,output=reviewed
    path=output/'selection.json'
    path.write_text(json.dumps(dict(schema_version=1,sources=[selection])))
    assert load_reviewed_sources(path,[frame])['raw.fits']['identity']['candidate']==2
    with pytest.raises(ValueError,match='selected raw'):load_reviewed_sources(path,[])
    selection['identity']['evidence']=''
    path.write_text(json.dumps(dict(schema_version=1,sources=[selection])))
    with pytest.raises(ValueError,match='evidence'):load_reviewed_sources(path,[frame])


def test_background_review_does_not_claim_target_identification(reviewed):
    selection,frame,data,wave,output=reviewed
    selection['identity']['method']='operator_background'
    selection['identity']['evidence']='Operator requested local background bands around the central source.'
    path=output/'selection.json'
    path.write_text(json.dumps(dict(schema_version=1,sources=[selection])))
    selected=load_reviewed_sources(path,[frame])['raw.fits']
    _,identity,_=prepare_reviewed_extraction(selected,frame,data,wave,(0,0),output)
    assert identity['association']=='UNVERIFIED_target_association'


def test_native_reselection_retains_raw_anchor_but_refits_background(reviewed):
    from pathlib import Path
    from efospec.reviewed_sources import native_review_arguments
    selection,frame,data,wave,output=reviewed
    raw=Path(frame['path']);raw.write_bytes(b'unchanged raw exposure')
    selection['raw_sha256']=frame['sha256']=sha256(raw)
    path=Path(selection['recipe_path']);recipe=json.loads(path.read_text())
    recipe['sky']['include']=[[10.,25.],[55.,70.]]
    path.write_text(json.dumps(recipe));selection['recipe_sha256']=sha256(path)
    args,evidence=native_review_arguments(selection,frame,data.shape,(0,0),output/'native')
    assert args['manual'][0]['spat']==40.
    assert evidence['identity']['candidate']==2
    assert evidence['original_background_reused'] is False
    assert args['sky_input_mask'][:,10:25].all()
    assert not args['sky_input_mask'][:,25:55].any()
    with pytest.raises(ValueError,match='outside native'):
        native_review_arguments(selection,frame,(10,20),(0,0),output/'invalid')
    raw.write_bytes(b'a different exposure')
    with pytest.raises(ValueError,match='changed'):
        native_review_arguments(selection,frame,data.shape,(0,0),output/'changed')


def test_nearest_native_background_uses_hash_bound_curved_trace(reviewed):
    from pathlib import Path
    from efospec.reviewed_sources import native_review_arguments
    selection,frame,data,wave,output=reviewed
    raw=Path(frame['path']);raw.write_bytes(b'raw exposure')
    selection['raw_sha256']=frame['sha256']=sha256(raw)
    source=output/'images.npz';trace=40+np.linspace(-2,2,10)
    np.savez(source,data=data,trace=trace,raw_y_origin=0,spatial_origin=-99,found_names=np.array([]),found_traces=np.empty((0,10)))
    p=Path(selection['recipe_path']);recipe=json.loads(p.read_text())
    recipe['sky'].update(placement='nearest_to_aperture',core_fwhm_pixels=2.,
        trace_reference=dict(path=str(source),sha256=sha256(source),raw_sha256=frame['sha256']))
    p.write_text(json.dumps(recipe));selection['recipe_sha256']=sha256(p)
    args,evidence=native_review_arguments(selection,frame,data.shape,(0,0),output/'native-nearest')
    assert np.array_equal(args['sky_trace'],trace)
    assert np.ptp(np.argmax(args['sky_input_mask'],axis=1))>1
    assert evidence['proximity']['maximum_gap_beyond_guard_pixels']<=1.
    source.write_bytes(b'changed reference')
    with pytest.raises(ValueError,match='trace reference changed'):
        native_review_arguments(selection,frame,data.shape,(0,0),output/'invalid-reference')
