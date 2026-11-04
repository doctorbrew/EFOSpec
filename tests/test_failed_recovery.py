"""Recover ambiguous synthetic exposures without silently selecting a neighbour."""
import json
from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits
from efospec.archive_calibration import fit_arc
from efospec.inventory import inspect_file,sha256
from efospec.rapid import select_archive,reduce_night
from efospec.revisions import FailedExposure,prepare_recovery,reextract
from test_pypeit_adapter import write_raw

REFERENCE=Path(__file__).resolve().parents[1]/'trunk/src/ntt'


def test_ambiguous_raw_can_be_recovered_with_hash_bound_manual_recipe(tmp_path,monkeypatch,qtbot):
    inputs=tmp_path/'raw';inputs.mkdir()
    raw=write_raw(inputs,'ambiguous.fits',**{'ESO OBS ID':42})
    frame=inspect_file(raw);arc,_=select_archive(frame,REFERENCE);wave,_=fit_arc(arc)
    y,x=np.indices(wave.shape);data=np.full(wave.shape,100.)
    for rest,amp in [(5577.338,500.),(6300.304,400.),(6363.776,133.)]:
        data+=amp*np.exp(-.5*((wave-rest+12.)/7.)**2)
    for center in [442.,456.]:
        data+=8000.*np.exp(-.5*((x-center)/1.7)**2)/(np.sqrt(2*np.pi)*1.7)
    data=np.random.default_rng(148).poisson(data).astype(float)
    with fits.open(raw,mode='update') as h:
        full=h[0].data.astype(float);full[:1015,99:950]=data/.91;h[0].data=full
    run=tmp_path/'failed'
    original=reduce_night(inputs,run,REFERENCE,skip_report=True)
    assert len(original['errors'])==1 and original['errors'][0]['code']=='source_selection_required'
    from pypeit.spec2dobj import Spec2DObj
    diagnostic=Path(original['errors'][0]['diagnostics']['native_spec2d'])
    assert fits.getheader(diagnostic)['QCSTAGE']=='source_selection_failed'
    assert not fits.getheader(diagnostic)['OBJMODEL']
    assert Spec2DObj.from_file(str(diagnostic),'DET01').sciimg.shape[1]==141
    exposure=FailedExposure(run,raw.name,REFERENCE)
    assert len(exposure.candidates)==2
    with pytest.raises(ValueError,match='explicit manual'):
        reextract(run,raw.name,exposure.default_recipe(),tmp_path/'auto',REFERENCE,failed=True,render_report=False)
    review=prepare_recovery(run,raw.name,tmp_path/'recipes',REFERENCE)
    assert review['status']=='TARGET_IDENTITY_REQUIRES_REVIEW'
    candidate=min(review['candidates'],key=lambda c:c['raw_spatial_pixel'])
    recipe=json.loads(Path(candidate['recipe']).read_text())
    before={p:sha256(p) for p in run.rglob('*') if p.is_file()}
    result=reextract(run,raw.name,recipe,tmp_path/'recovered',REFERENCE,failed=True,render_report=False)
    assert len(result['results'])==1
    assert result['results'][0]['target']['median_trace_trimmed_pixel']==pytest.approx(442.,abs=.3)
    assert all(sha256(p)==digest for p,digest in before.items())
    from efospec.recovery_qc import build_recovery_qc
    acquisition=write_raw(inputs,'acquisition.fits',**{
        'ESO OBS ID':fits.getheader(raw)['ESO OBS ID'],
        'ESO TPL ID':'EFOSC_img_acq_MoveToSlit','ESO DPR TECH':'IMAGE',
        'CTYPE1':'','CTYPE2':''})
    acquisition_hash=sha256(acquisition)
    packet=tmp_path/'night'/'QC'/'ambiguous'
    qc=build_recovery_qc(run,raw.name,packet,REFERENCE,test_recipes=True)
    assert qc['identity']=='UNVERIFIED' and qc['status']=='complete'
    assert len(qc['candidates'])==2
    assert len(qc['acquisitions'])==1
    assert not qc['acquisitions'][0]['has_celestial_wcs']
    assert sha256(acquisition)==acquisition_hash
    for c in qc['candidates']:
        assert c['trial']['execution']=='passed',c['trial']
        assert abs(c['trial']['anchor_drift_pixel'])<.5
        recipe_data=json.loads(Path(c['recipe']).read_text())
        assert recipe_data['objects'][0]['label'].endswith('UNVERIFIED')
        assert fits.getheader(c['trial']['product'])['OBJECT'].endswith('UNVERIFIED')
    assert all((packet/p).is_file() for p in ['science.png','traces.png','profiles.png','trial-spectra.png','index.html','target-selection.csv'])
    from PIL import Image
    jpgs=list(packet.glob('FitQC_*.jpg'))
    assert len(jpgs)==5
    for jpg in jpgs:
        assert jpg.with_suffix('.pdf').is_file()
        with Image.open(jpg) as im:assert im.info['dpi']==(300,300)
    from copy import deepcopy
    from efospec.polynomial_background import extract_background
    poly=deepcopy(recipe);sx=poly['objects'][0]['spat']
    poly['sky']=dict(mode='polynomial',include=[[sx-25,sx-15],[sx+25,sx+40]],
                     exclude=[],degree=2,sigma_clip=4.)
    with pytest.raises(ValueError,match='background-extract'):
        reextract(run,raw.name,poly,tmp_path/'wrong-engine',REFERENCE,failed=True,render_report=False)
    polynomial=extract_background(run,raw.name,poly,tmp_path/'polynomial',REFERENCE)
    assert polynomial['valid_fraction']>.9
    with fits.open(tmp_path/'polynomial'/'boxcar-background.fits') as hdus:
        assert hdus[0].header['FLUXCAL']=='NONE'
        valid=hdus['SPECTRUM'].data['VALID']
        assert valid.any() and np.all(hdus['SPECTRUM'].data['SIGMA'][valid]>0)
    assert all(sha256(p)==digest for p,digest in before.items())
    # Exercise the real editor against this saved exposure and the shared
    # scientific engine. Offscreen CI is separate from the native macOS check.
    from PySide6 import QtCore,QtWidgets
    from efospec.desktop import ExtractionWindow
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    shell=ExtractionWindow(packet/'review.json',REFERENCE)
    qtbot.addWidget(shell);shell.show()
    editor=shell.review_editor
    assert editor is not None and editor.parentWidget() is shell.review_page
    assert shell.backend is None  # All exposures failed; source review still opens.
    assert shell.tabs.currentIndex()==1 and editor.candidate.currentIndex()==0
    try:
        assert editor.preview() is None  # no automatic target selection
        editor.candidate.setCurrentIndex(1)
        editor.select_band(sx-25,sx-15);editor.select_band(sx+25,sx+40)
        first=editor.preview()
        assert first is not None and first[1]['valid'].mean()>.9
        saved=tmp_path/'desktop-recipe.json'
        monkeypatch.setattr(QtWidgets.QFileDialog,'getSaveFileName',lambda *a,**kw:(str(saved),'JSON'))
        editor.save_recipe()
        assert saved.is_file()
        editor.degree.setValue(1);editor.bands.clear()
        monkeypatch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a,**kw:(str(saved),'JSON'))
        editor.load_recipe()
        assert editor.recipe()==json.loads(saved.read_text())
        np.testing.assert_allclose(editor.last_result['counts'],first[1]['counts'],equal_nan=True)
        editor.panel.setCurrentIndex(1)
        assert editor.last_result['valid'].any()
        # The embedded review launches the same Python engine, forwards its
        # reference root and produces the previewed counts without touching inputs.
        destination=tmp_path/'desktop-output';destination.mkdir()
        monkeypatch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a,**kw:str(destination))
        editor.extract()
        assert editor.is_running()
        shell.poll_job()
        assert not shell.open_button.isEnabled()
        qtbot.waitUntil(lambda:not editor.is_running(),timeout=90000)
        assert editor.worker.exitCode()==0
        products=list(destination.glob('background-*/boxcar-background.fits'))
        assert len(products)==1
        with fits.open(products[0]) as hdus:
            np.testing.assert_allclose(hdus['SPECTRUM'].data['COUNTS'],first[1]['counts'],equal_nan=True)
        assert all(sha256(p)==digest for p,digest in before.items())
        # A live worker can be cancelled without closing the shared shell.
        import sys
        editor.worker=QtCore.QProcess(editor)
        editor.worker.start(sys.executable,['-c','import time; time.sleep(60)'])
        assert editor.worker.waitForStarted(5000)
        editor.cancel()
        qtbot.waitUntil(lambda:not editor.is_running(),timeout=5000)
        assert shell.isVisible()
        editor.worker=None
        # A malformed selection cannot start an extraction or replace the
        # previously saved recipe.
        editor.bands.setText('not a band')
        assert editor.preview() is None
        editor.save_recipe();editor.extract()
        assert editor.worker is None
        assert json.loads(saved.read_text())==first[0]
        editor.load_recipe()
        # A removed/unwritable destination must leave the desktop session
        # usable and must not launch a worker with an absent recipe.
        monkeypatch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a,**kw:str(tmp_path/'removed'))
        editor.extract()
        assert editor.worker is None
        assert 'Cannot save extraction recipe' in editor.message.text()
        shell.reviews.setCurrentIndex(0)
        assert shell.review_editor is None
    finally:
        shell.close();app.processEvents()
    with pytest.raises(FileExistsError):
        build_recovery_qc(run,raw.name,packet,REFERENCE)
    recipe['input_sha256']['images']='0'*64
    with pytest.raises(ValueError,match='hashes'):
        reextract(run,raw.name,recipe,tmp_path/'tampered',REFERENCE,failed=True,render_report=False)
    with fits.open(raw,mode='update') as h:h[0].header['OBJECT']='changed'
    with pytest.raises(ValueError,match='raw input changed'):
        FailedExposure(run,raw.name,REFERENCE)
