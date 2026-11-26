"""Native failed-exposure controls explain missing geometry before a worker starts."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6 import QtCore
from efospec.recipes import DetectorWindow


@pytest.fixture
def editor(qtbot,monkeypatch,tmp_path):
    from efospec import background_gui as gui
    hashes={'raw':'a'*64,'images':'b'*64,'manifest':'c'*64}
    recipe=dict(schema_version=1,engine_version='3.0.0',coordinates='raw_detector_pixels_zero_based',
        input_sha256=hashes,source_mode='manual',objects=[],sky=dict(mode='automatic',include=[],exclude=[]))
    exposure=SimpleNamespace(run=tmp_path,window=DetectorWindow((100,201),(0,448)),hashes=hashes,
        context=SimpleNamespace(calibration={'native':True},sky_qa={'held_out_6363_pass':False}),
        images={'found_traces':np.full((1,100),100.)},
        candidates=[{'raw_spatial_pixel':548.}],default_recipe=lambda:recipe.copy())
    monkeypatch.setattr(gui,'FailedExposure',lambda *args:exposure)
    monkeypatch.setattr(gui,'draw_candidates',lambda fig,e:fig.add_subplot())
    monkeypatch.setattr(gui,'draw_background',lambda *args,**kw:None)
    def draw(fig,*args,**kwargs):
        fig.clear();fig.extraction_axes=tuple(fig.subplots(1,3))
    monkeypatch.setattr(gui,'draw_extraction',draw)
    w=gui.BackgroundEditor(dict(parent_run=str(tmp_path),raw_name='failed.fits',object='ATtest'))
    qtbot.addWidget(w);w.show()
    yield w
    w.close()


def test_missing_selection_and_placeholder_are_explained(editor,qtbot):
    w=editor
    assert not w.extract_button.isEnabled()
    assert 'Choose a trace candidate' in w.readiness.toolTip()
    assert 'Grey example text is not a selection' in w.readiness.toolTip()
    w.candidate.setCurrentIndex(1)
    assert w.position.isEnabled() and not w.extract_button.isEnabled()
    w.bands.setFocus();qtbot.keyClicks(w.bands,'500:530, 575:605')
    assert w.extract_button.isEnabled(),w.readiness.text()
    assert 'Calibrated extraction reruns wavelength checks' in w.readiness.toolTip()
    assert w.worker is None
    w.bands.setText('500:505, 575:580')
    assert not w.extract_button.isEnabled()
    w.bands.setText('500:530, 575:605')
    assert w.extract_button.isEnabled()
    w.bands.clear();assert not w.extract_button.isEnabled()


def test_plot_click_explicitly_selects_trace(editor):
    w=editor;w.mouse_mode.setCurrentIndex(1)
    w.click_position(SimpleNamespace(inaxes=w.figure.axes[0],xdata=550.))
    assert w.candidate.currentIndex()==1 and w.position.isEnabled()
    assert w.position.value()==550.
    w.bands.setText('500:530, 575:605')
    assert w.validated_recipe()['objects'][0]['spat']==550.
    assert w.extract_button.isEnabled()


def test_valid_recipe_click_starts_cancellable_worker(editor,qtbot,monkeypatch,tmp_path):
    from efospec import background_gui as gui
    w=editor;w.candidate.setCurrentIndex(1);w.bands.setText('500:530, 575:605')
    monkeypatch.setattr(gui,'calculate',lambda e,r:(r,{'valid':np.ones(100,dtype=bool)}))
    monkeypatch.setattr(gui.QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:pytest.fail('Extraction must not ask for a directory'))
    original=QtCore.QProcess.start;commands=[]
    def start(process,python,args):
        commands.append(args)
        original(process,python,['-c','import time; time.sleep(120)'])
    monkeypatch.setattr(QtCore.QProcess,'start',start)
    qtbot.mouseClick(w.extract_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(w.is_running)
    assert not w.extract_button.isEnabled() and w.cancel_button.isEnabled()
    assert '--native-flux' in commands[0]
    saved=json.loads(next((tmp_path/'manual-revisions').glob('background-*.json')).read_text())
    assert saved==w.validated_recipe()
    qtbot.mouseClick(w.cancel_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:not w.is_running(),timeout=5000)
    qtbot.waitUntil(lambda:w.extract_button.isEnabled())


def test_preview_failure_is_shown_beside_extract(editor,monkeypatch):
    from efospec import background_gui as gui
    w=editor;w.candidate.setCurrentIndex(1);w.bands.setText('500:530, 575:605')
    def failed(*args):raise ValueError('no valid background rows for preview')
    monkeypatch.setattr(gui,'calculate',failed)
    assert w.preview() is None
    assert 'Cannot extract: no valid background rows' in w.readiness.text()
    assert w.worker is None


def test_failed_parent_allows_new_calibration_attempt(editor):
    w=editor;w.candidate.setCurrentIndex(1);w.bands.setText('500:530, 575:605')
    w.native_flux.setChecked(True)
    assert w.extract_button.isEnabled()
    assert 'reruns wavelength checks' in w.readiness.toolTip()
    assert w.search_button.isEnabled()
    w.native_flux.setChecked(False)
    assert w.extract_button.isEnabled()


def test_worker_failure_displays_actual_reason(editor,tmp_path,qtbot):
    w=editor;output=tmp_path/'failed'
    (tmp_path/'failed-error.log').write_text('background-extract: Parent wavelength check failed; flux recovery withheld\n')
    w.worker_finished(2,output)
    assert 'Parent wavelength check failed' in w.message.text()
    assert 'Parent wavelength check failed' in w.worker_details.toPlainText()
    assert not w.worker_details.isVisible()
    assert not w.log_dialog.isVisible()
    qtbot.mouseClick(w.log_button,QtCore.Qt.MouseButton.LeftButton)
    assert w.log_dialog.isVisible()
    assert 'Parent wavelength check failed' in w.log_view.toPlainText()
    assert 'Parent sky validation failed' in w.log_view.toPlainText()


def test_click_tools_leave_pan_mode_and_band_drag_updates_selection(editor,qtbot):
    w=editor;w.toolbar.pan()
    qtbot.mouseClick(w.plot_actions[1],QtCore.Qt.MouseButton.LeftButton)
    assert not w.toolbar.mode and w.mouse_mode.currentIndex()==1
    w.click_position(SimpleNamespace(inaxes=w.figure.axes[0],xdata=550.))
    qtbot.mouseClick(w.plot_actions[2],QtCore.Qt.MouseButton.LeftButton)
    assert w.selector.active
    w.select_band(500,530);w.select_band(575,605)
    assert w.extract_button.isEnabled()
    w.clear_bands()
    assert not w.bands.text() and not w.extract_button.isEnabled()
    assert not any(getattr(p,'_efospec_background',False) for p in w.figure.axes[0].patches)


def test_saved_trace_counts_use_explicit_separate_worker_mode(editor,qtbot,monkeypatch,tmp_path):
    from efospec import background_gui as gui
    w=editor;w.candidate.setCurrentIndex(1);w.bands.setText('500:530, 575:605')
    w.native_flux.setChecked(False);w.counts_method.setCurrentIndex(1);w.degree.setValue(0)
    assert 'saved-trace polynomial boxcar' in w.readiness.toolTip()
    monkeypatch.setattr(gui,'calculate',lambda e,r:(r,{'valid':np.ones(100,dtype=bool)}))
    monkeypatch.setattr(gui.QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:pytest.fail('Extraction must not ask for a directory'))
    original=QtCore.QProcess.start;commands=[]
    def start(process,python,args):
        commands.append(args);original(process,python,['-c','pass'])
    monkeypatch.setattr(QtCore.QProcess,'start',start)
    qtbot.mouseClick(w.extract_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:w.worker is not None and not w.is_running())
    assert 'background-extract' in commands[0]
    assert '--native-counts' not in commands[0] and '--native-flux' not in commands[0]
    assert json.loads(next((tmp_path/'manual-revisions').glob('background-*.json')).read_text())['sky']['degree']==0


def test_delayed_canvas_draw_keeps_house_tex_fonts(editor,monkeypatch):
    import matplotlib as mpl
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    seen=[]
    monkeypatch.setattr(FigureCanvasQTAgg,'draw',lambda self:seen.append((mpl.rcParams['text.usetex'],mpl.rcParams['font.family'])))
    with mpl.rc_context({'text.usetex':False,'font.family':'sans-serif'}):
        editor.canvas.draw()
        assert mpl.rcParams['font.family']==['sans-serif']
    assert seen==[(True,['serif'])]


@pytest.mark.parametrize('panel_index',[0,1])
def test_native_canvas_mouse_click_and_drag(editor,qtbot,panel_index):
    w=editor;ax=w.figure.axes[panel_index];ax.set_xlim(448,648);ax.set_ylim(0,1)
    w.canvas.draw()
    def point(x):
        px,py=ax.transData.transform((x,.5));ratio=w.canvas.device_pixel_ratio
        return QtCore.QPoint(round(px/ratio),round(w.canvas.height()-py/ratio))
    qtbot.mouseClick(w.plot_actions[1],QtCore.Qt.MouseButton.LeftButton)
    qtbot.mouseClick(w.canvas,QtCore.Qt.MouseButton.LeftButton,pos=point(550))
    assert w.candidate.currentIndex()==1
    assert abs(w.position.value()-550)<1
    qtbot.mouseClick(w.plot_actions[2],QtCore.Qt.MouseButton.LeftButton)
    for lo,hi in ((500,530),(575,605)):
        qtbot.mousePress(w.canvas,QtCore.Qt.MouseButton.LeftButton,pos=point(lo))
        qtbot.mouseMove(w.canvas,point(hi))
        qtbot.mouseRelease(w.canvas,QtCore.Qt.MouseButton.LeftButton,pos=point(hi))
    assert len(w.validated_recipe()['sky']['include'])==2
    assert w.extract_button.isEnabled()


def test_calibration_stages_preserve_failed_evidence(editor):
    w=editor
    assert [w.workflow_tabs.tabText(i) for i in range(3)]==[
        '1 Wavelength calibration','2 Extraction','3 Flux calibration']
    assert 'held_out_6363_pass' in w.wavelength_evidence.toPlainText()
    assert not w.recipe_options.isChecked()
    assert w.panel.currentIndex()==2
    assert not w.workflow_tabs.tabBar().isVisible()
    w.stage.setCurrentIndex(0)
    assert w.workflow_tabs.currentIndex()==0
    w.workflow_tabs.setCurrentIndex(2)
    assert w.stage.currentIndex()==2


def flux_product(path, *, wavelength_valid=False):
    from astropy.io import fits
    data=np.ones((4,1,5));data[0,0]=[1,2,999,4,5];data[3,0]=.1
    valid=np.ones((4,5),dtype=np.uint8);valid[:,2]=0
    h=fits.Header(dict(FLUXCAL='NATIVE',WAVEVAL=wavelength_valid,OBJECT='ATtest',
        WAVEMED='air',CRVAL1=4000.,CRPIX1=1.,CDELT1=5.,TRCWARN=True,TRCDEV=.668))
    fits.HDUList([fits.PrimaryHDU(data,header=h),fits.ImageHDU(valid,name='VALID')]).writeto(path)
    return path


def test_completed_flux_opens_final_view_without_hiding_warning_or_invalid_mask(editor,tmp_path):
    output=tmp_path/'completed';output.mkdir();product=flux_product(output/'final.fits')
    (output/'run.json').write_text(json.dumps(dict(status='PROVISIONAL',results=[
        dict(raw='failed.fits',product=str(product))])))
    editor.worker_finished(0,output)
    assert editor.workflow_tabs.currentIndex()==3
    assert editor.final_product==product
    assert 'wavelength unvalidated' in editor.final_view.status.text()
    assert '0.668' in editor.final_view.status.text()
    assert 'quality checks failed' in editor.wave_status.text()
    assert 'applied' in editor.flux_status.text()
    line=editor.final_view.figure.axes[0].lines[0]
    np.testing.assert_array_equal(line.get_xdata(),[4000,4005,4010,4015,4020])
    assert np.isnan(line.get_ydata()[2])
    assert editor.next_button.text()=='View final spectrum'
    editor.continue_with_warnings()
    assert editor.workflow_tabs.currentIndex()==1
    assert editor.next_button.text()=='Next: select trace'
    assert editor.final_product==product  # Earlier result remains available in Final spectrum.


def test_saved_final_discovery_requires_matching_parent_raw_and_completed_revision(editor,tmp_path):
    from efospec.desktop_spectrum import latest_flux_revision
    output=tmp_path/'manual-revisions'/'saved';output.mkdir(parents=True)
    product=flux_product(output/'final.fits')
    record=dict(raw='failed.fits',raw_sha256=editor.exposure.hashes['raw'],product=str(product))
    manifest=dict(parent_run=str(tmp_path),parent_sha256=editor.exposure.hashes['manifest'],
                  execution_status='complete',results=[record])
    file=output/'run.json';file.write_text(json.dumps(manifest))
    assert latest_flux_revision(editor.exposure,'failed.fits')[0]==output
    for key,value in [('parent_sha256','different'),('execution_status','failed')]:
        file.write_text(json.dumps(dict(manifest,**{key:value})))
        assert latest_flux_revision(editor.exposure,'failed.fits') is None
    manifest['results'][0]['raw_sha256']='different';file.write_text(json.dumps(manifest))
    assert latest_flux_revision(editor.exposure,'failed.fits') is None


def test_next_action_guides_selection_then_extracts_with_flux(editor,qtbot,monkeypatch):
    w=editor;calls=[]
    monkeypatch.setattr(w,'extract',lambda:calls.append('extract'))
    assert w.next_button.text()=='Next: select trace'
    qtbot.mouseClick(w.next_button,QtCore.Qt.MouseButton.LeftButton)
    assert w.mouse_mode.currentIndex()==1
    w.candidate.setCurrentIndex(1)
    assert w.next_button.text()=='Next: choose background'
    qtbot.mouseClick(w.next_button,QtCore.Qt.MouseButton.LeftButton)
    assert w.mouse_mode.currentIndex()==2
    w.bands.setText('500:530, 575:605')
    assert w.next_button.text()=='Extract flux-calibrated spectrum'
    assert w.next_animation.state()==QtCore.QAbstractAnimation.State.Running
    qtbot.mouseClick(w.next_button,QtCore.Qt.MouseButton.LeftButton)
    assert calls==['extract'] and w.native_flux.isChecked()


def test_completed_provisional_spectrum_keeps_calibration_and_trace_warnings(editor,tmp_path):
    output=tmp_path/'provisional';output.mkdir()
    (output/'run.json').write_text(json.dumps({'status':'PROVISIONAL',
        'warnings':[{'message':'Sky SNR 5.6; wavelength unvalidated'}],
        'results':[{'processing':{'trace_geometry':{'warnings':[{'message':'Trace departure 0.668 pixel; extraction continues'}]}}}]}))
    editor.worker_finished(0,output)
    assert 'Provisional spectrum complete -- wavelength unvalidated' in editor.message.text()
    assert 'Sky SNR 5.6' in editor.message.text()
    assert 'Trace departure 0.668' in editor.message.text()



def test_selections_update_both_panels_without_fitting(editor,monkeypatch):
    from efospec import background_gui as gui
    monkeypatch.setattr(gui,'calculate',lambda *args:pytest.fail('Selection edits must not run extraction'))
    w=editor;image_ax,profile_ax,counts_ax=w.figure.extraction_axes
    w.mouse_mode.setCurrentIndex(1)
    w.click_position(SimpleNamespace(inaxes=profile_ax,xdata=551.,ydata=200.))
    assert w.position.value()==551. and w.spectral_anchor.value()==50
    assert any(np.allclose(line.get_xdata(),551.) for line in image_ax.lines)
    assert any(np.allclose(line.get_xdata(),551.) for line in profile_ax.lines)
    w.radius.setValue(9.)
    assert any(np.isclose(p.get_width(),18.) for p in profile_ax.patches if getattr(p,'_efospec_selection',False))
    w.select_band(500,530)
    for ax in (image_ax,profile_ax):
        assert sum(getattr(p,'_efospec_background',False) for p in ax.patches)==1
    w.bands.setText('500:530, 575:605')
    for ax in (image_ax,profile_ax):
        assert sum(getattr(p,'_efospec_background',False) for p in ax.patches)==2
    w.clear_bands()
    assert not any(getattr(p,'_efospec_background',False) for ax in (image_ax,profile_ax) for p in ax.patches)
    assert len(w.selectors)==2
