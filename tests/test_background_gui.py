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
        candidates=[{'raw_spatial_pixel':548.}],default_recipe=lambda:recipe.copy())
    monkeypatch.setattr(gui,'FailedExposure',lambda *args:exposure)
    monkeypatch.setattr(gui,'draw_candidates',lambda fig,e:fig.add_subplot())
    monkeypatch.setattr(gui,'draw_background',lambda *args,**kw:None)
    w=gui.BackgroundEditor(dict(parent_run=str(tmp_path),raw_name='failed.fits',object='ATtest'))
    qtbot.addWidget(w);w.show()
    yield w
    w.close()


def test_missing_selection_and_placeholder_are_explained(editor,qtbot):
    w=editor
    assert not w.extract_button.isEnabled()
    assert 'Choose a trace candidate' in w.readiness.text()
    assert 'Grey example text is not a selection' in w.readiness.text()
    w.candidate.setCurrentIndex(1)
    assert w.position.isEnabled() and not w.extract_button.isEnabled()
    w.bands.setFocus();qtbot.keyClicks(w.bands,'500:530, 575:605')
    assert w.extract_button.isEnabled(),w.readiness.text()
    assert 'Review counts only' in w.readiness.text()
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
    monkeypatch.setattr(gui.QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(tmp_path))
    original=QtCore.QProcess.start;commands=[]
    def start(process,python,args):
        commands.append(args)
        original(process,python,['-c','import time; time.sleep(120)'])
    monkeypatch.setattr(QtCore.QProcess,'start',start)
    qtbot.mouseClick(w.extract_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(w.is_running)
    assert not w.extract_button.isEnabled() and w.cancel_button.isEnabled()
    assert '--native-counts' in commands[0]
    saved=json.loads(next(tmp_path.glob('background-*.json')).read_text())
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


def test_failed_parent_flux_preflight_does_not_block_review_counts(editor):
    w=editor;w.candidate.setCurrentIndex(1);w.bands.setText('500:530, 575:605')
    w.native_flux.setChecked(True)
    assert not w.extract_button.isEnabled()
    assert 'Uncheck checked flux recovery' in w.readiness.text()
    assert w.search_button.isEnabled()
    w.native_flux.setChecked(False)
    assert w.extract_button.isEnabled()


def test_worker_failure_displays_actual_reason(editor,tmp_path):
    w=editor;output=tmp_path/'failed'
    (tmp_path/'failed-error.log').write_text('background-extract: Parent wavelength check failed; flux recovery withheld\n')
    w.worker_finished(2,output)
    assert 'Parent wavelength check failed' in w.message.text()
    assert 'Parent wavelength check failed' in w.worker_details.toPlainText()
    assert w.worker_details.isVisible()


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
    w.counts_method.setCurrentIndex(1);w.degree.setValue(0)
    assert 'saved-trace polynomial boxcar' in w.readiness.text()
    monkeypatch.setattr(gui,'calculate',lambda e,r:(r,{'valid':np.ones(100,dtype=bool)}))
    monkeypatch.setattr(gui.QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(tmp_path))
    original=QtCore.QProcess.start;commands=[]
    def start(process,python,args):
        commands.append(args);original(process,python,['-c','pass'])
    monkeypatch.setattr(QtCore.QProcess,'start',start)
    qtbot.mouseClick(w.extract_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:w.worker is not None and not w.is_running())
    assert 'background-extract' in commands[0]
    assert '--native-counts' not in commands[0] and '--native-flux' not in commands[0]
    assert json.loads(next(tmp_path.glob('background-*.json')).read_text())['sky']['degree']==0


def test_delayed_canvas_draw_keeps_house_tex_fonts(editor,monkeypatch):
    import matplotlib as mpl
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    seen=[]
    monkeypatch.setattr(FigureCanvasQTAgg,'draw',lambda self:seen.append((mpl.rcParams['text.usetex'],mpl.rcParams['font.family'])))
    with mpl.rc_context({'text.usetex':False,'font.family':'sans-serif'}):
        editor.canvas.draw()
        assert mpl.rcParams['font.family']==['sans-serif']
    assert seen==[(True,['serif'])]


def test_native_canvas_mouse_click_and_drag(editor,qtbot):
    w=editor;ax=w.figure.axes[0];ax.set_xlim(448,648);ax.set_ylim(0,1)
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
