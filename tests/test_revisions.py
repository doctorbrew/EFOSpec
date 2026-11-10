"""Scientific export/replay tests with injected photons, without proprietary data."""
import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from efospec.extraction import extract_spectra
from efospec.inventory import inspect_file, sha256
from efospec.products import PreparedExposure, export_spectrum
from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
from test_extraction import synthetic_image
from test_pypeit_adapter import write_raw


@pytest.fixture
def saved_exposure(tmp_path):
    raw = write_raw(tmp_path, 'raw.fits')
    data, wave, truth = synthetic_image()
    with fits.open(raw, mode='update') as hdus:
        full = hdus[0].data.astype(float)
        full[:160, 299:440] = data/.91
        hdus[0].data = full
    data = fits.getdata(raw)[:160,299:440]*.91
    frame = inspect_file(raw)
    reference = tmp_path/'reference'
    extinction = reference/'standard/extinction/extinction_lasilla.dat'
    extinction.parent.mkdir(parents=True)
    np.savetxt(extinction, [[3000,0], [10000,0]])
    sensitivity = reference/'archive/efosc/sens/Gr13/Free/response.fits'
    sensitivity.parent.mkdir(parents=True)
    fits.PrimaryHDU(np.full(800, 40.), fits.Header({'CRVAL1':3000., 'CD1_1':10.,
        'CRPIX1':1., 'MJD-OBS':60000.})).writeto(sensitivity)
    with fits.open(raw) as hdus:
        detector = EFOSpecEFOSC2Spectrograph().get_detector_par(1, hdus)
    run = tmp_path/'parent'
    for sub in ('products','native','qa','QA/PNGs'):
        (run/sub).mkdir(parents=True)
    context = PreparedExposure(frame, reference, detector, data, wave, 200, 0,
        248., {'association':'historical_aperture'},
        {'arc':'reference.fits', 'reference_lines':[5010.,5780.]}, sensitivity, 0.,
        {'shift_angstrom':0.})
    engine = extract_spectra(data, wave, detector, exposure_time=frame['metadata']['EXPTIME'],
        read_noise=7.8, output=run, basename='test', target_position=48.)
    result = export_spectrum(context, engine, 'primary', run, 'test')
    from pypeit.spec2dobj import Spec2DObj
    from pypeit.core.wave import airtovac
    from astropy import units as u
    diagnostic=Spec2DObj.from_file(result['native_spec2d'],'DET01')
    np.testing.assert_allclose(diagnostic.sciimg,data,rtol=1e-7)
    np.testing.assert_array_equal(diagnostic.waveimg,airtovac(wave*u.AA).value)
    np.testing.assert_array_equal(diagnostic.bpmmask.mask,engine['arrays'][3].mask)
    assert fits.getheader(result['native_spec2d'])['RAWX0']==299
    manifest = {'results':[result], 'input_dir':str(tmp_path), 'output_dir':str(run),
        'pypeit_version':__import__('pypeit').__version__, 'limitations':['Synthetic calibration'], 'errors':[], 'skipped':[]}
    (run/'run.json').write_text(json.dumps(manifest))
    return run, reference, truth


def test_export_retains_units_bands_masks_and_raw_bytes(saved_exposure):
    run, _, truth = saved_exposure
    result = json.loads((run/'run.json').read_text())['results'][0]
    with fits.open(run/'products/test_f.fits') as hdus:
        flux = hdus[0].data[:,0,:]
        h = hdus[0].header
        assert h['BANDID1'] == 'optimal flux'
        assert h['WAVEMED'] == 'air' and h['FLUXCAL'] == 'ARCHIVE'
        assert h['SPECSYS'] == 'TOPOCENT' and hdus['VALID'].data.shape == (4,flux.shape[1])
        assert np.all(flux[3,hdus['VALID'].data[3].astype(bool)] > 0)
        # Constant 10^16 response, zero extinction: median F_lambda is counts/(gain*time*dispersion*response).
        expected = np.median(truth['primary'])/(.91*h['EXPTIME']*5.*1e16)
        assert np.median(flux[0,np.isfinite(flux[0])])/expected == pytest.approx(1., abs=.03)
    assert sha256(Path(result['raw'])) == result['raw_sha256']


def test_automatic_revision_exactly_replays_and_never_overwrites(saved_exposure, tmp_path):
    from efospec.revisions import Exposure, reextract
    run, reference, _ = saved_exposure
    exposure = Exposure(run, 'test_f.fits', reference)
    recipe = exposure.default_recipe()
    original = {p:sha256(p) for p in run.rglob('*') if p.is_file()}
    output = tmp_path/'revision'
    result = reextract(run, 'test_f.fits', recipe, output, reference, render_report=False)
    assert len(result['results']) == 1
    for extension in (0, 'VALID'):
        np.testing.assert_array_equal(fits.getdata(run/'products/test_f.fits', extension),
                                      fits.getdata(output/'products/test_f.fits', extension))
    assert json.loads((output/'recipe.json').read_text()) == recipe
    assert all(sha256(p) == digest for p,digest in original.items())
    with pytest.raises(FileExistsError):
        reextract(run, 'test_f.fits', recipe, output, reference, render_report=False)
    recipe['input_sha256']['raw'] = '0'*64
    with pytest.raises(ValueError, match='hashes'):
        reextract(run, 'test_f.fits', recipe, tmp_path/'bad', reference, render_report=False)
    assert not (tmp_path/'bad').exists()


def test_manual_revision_exports_two_sources_and_actual_background(saved_exposure, tmp_path):
    from efospec.revisions import Exposure, reextract
    run, reference, _ = saved_exposure
    exposure = Exposure(run, 'test_f.fits', reference)
    recipe = exposure.default_recipe()
    recipe['source_mode'] = 'manual'
    recipe['objects'] = [dict(id=identity,label=identity,kind='point',spec=80.,spat=299.+spat,
                              fwhm=4.,radius=7.) for identity,spat in [('primary',48.),('host',98.)]]
    recipe['sky'] = {'mode':'regions','include':[[304,329],[419,435]],'exclude':[[425,428]]}
    output = tmp_path/'manual'
    result = reextract(run,'test_f.fits',recipe,output,reference,render_report=False)
    assert [Path(r['product']).name for r in result['results']] == ['test_f.fits','test_obj_host_f.fits']
    assert result['results'][1]['object'] == 'host'
    assert all(r['processing']['sky_policy'] == 'selected_global_sky' for r in result['results'])
    with np.load(output/'native/test_images.npz') as images:
        assert not images['sky_input_mask'][:,126:129].any()
    assert result['recipe_sha256'] == sha256(output/'recipe.json')


def test_local_pypeit_revision_preserves_fit_order_masks_and_identity_status(saved_exposure,tmp_path):
    from efospec.revisions import Exposure,reextract
    run,reference,_=saved_exposure
    exposure=Exposure(run,'test_f.fits',reference)
    recipe=exposure.default_recipe()
    recipe.update(source_mode='manual',objects=[exposure.primary_object()])
    recipe['sky']=dict(mode='pypeit_local',include=[],exclude=[],width_pixels=30,degree=1,sigma_clip=4.)
    output=tmp_path/'local'
    result=reextract(run,'test_f.fits',recipe,output,reference,render_report=False)
    qa=result['results'][0]
    assert qa['target']['association']=='recipe_selected_unverified'
    assert qa['processing']['background_fit']['spatial_degree']==1
    assert qa['processing']['background_fit']['selection']['width_spatial_pixels']==30
    with np.load(output/'native/test_images.npz') as images:
        assert images['sky_spatial_degree']==1
        assert np.all(images['sky_input_mask'].sum(axis=1)==60)
        assert not images['sky_accepted_mask'][~images['sky_input_mask']].any()


def test_expanded_archive_window_is_explicit_and_reproduces_original_pixels(saved_exposure,tmp_path,monkeypatch):
    from dataclasses import replace
    from efospec.revisions import Exposure,expand_archive_window
    from efospec import archive_calibration
    run,reference,_=saved_exposure
    exposure=Exposure(run,'test_f.fits',reference)
    original=exposure.context;data=original.data.copy();wave=original.waveair.copy()
    setup=original.frame['setup']
    arc=reference/'archive/efosc/arc'/setup['grism']/setup['filter']/setup['slit']/'reference.fits'
    arc.parent.mkdir(parents=True);arc.write_bytes(b'pinned arc fixture')
    record=dict(original.arc_qa,arc_sha256=sha256(arc),identifications_sha256='a'*64)
    exposure.context=replace(original,arc_qa=record)
    y,x=np.indices((160,851));fullwave=5000.+5.*y+.02*(x-200)
    monkeypatch.setattr(archive_calibration,'fit_arc',lambda p:(fullwave,{'identifications_sha256':'a'*64}))
    expanded=expand_archive_window(exposure,50)
    np.testing.assert_array_equal(expanded.context.data[:,50:-50],data)
    np.testing.assert_array_equal(expanded.context.waveair[:,50:-50],wave)
    assert expanded.window.shape==(160,241) and expanded.window.origin==(0,249)
    assert 'expanded_window' in expanded.hashes
    assert np.isnan(expanded.images['sky'][:,:50]).all()
    assert sha256(Path(original.frame['path']))==original.frame['sha256']


def test_changed_raw_and_unknown_exposure_are_rejected(saved_exposure):
    from efospec.revisions import Exposure
    run, reference, _ = saved_exposure
    with pytest.raises(ValueError, match='exposure'):
        Exposure(run, '../test_f.fits', reference)
    result = json.loads((run/'run.json').read_text())['results'][0]
    with fits.open(result['raw'], mode='update') as hdus:
        hdus[0].header['OBJECT'] = 'changed'
    with pytest.raises(ValueError, match='raw'):
        Exposure(run,'test_f.fits',reference)
