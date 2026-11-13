"""Native Qt interactions and real subprocess lifecycle (no browser)."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6 import QtCore
from test_revisions import saved_exposure


@pytest.fixture
def window(qtbot,saved_exposure):
    from efospec.desktop import ExtractionWindow
    run,reference,_=saved_exposure
    w=ExtractionWindow(run,reference);qtbot.addWidget(w);w.show()
    qtbot.waitUntil(lambda:w.canvas.isVisible())
    yield w
    w.close()


def test_desktop_source_background_and_recipe_roundtrip(window,qtbot,tmp_path):
    w=window
    assert w.exposure is not None and w.run_button.isEnabled()
    old=w.recipe()['objects'][0]['spat']
    w.pick_source(SimpleNamespace(inaxes=w.image_ax,button=1,xdata=85.,ydata=old+1.5))
    assert w.recipe()['objects'][0]['spat']==pytest.approx(old+1.5)
    w.select_background(301.,326.);w.select_background(420.,437.)
    assert w.recipe()['sky']['include']==[[301.,326.],[420.,437.]]
    assert w.run_button.isEnabled()
    path=tmp_path/'recipe.json';w.save_recipe(path);saved=json.loads(path.read_text())
    w.sources.fields['spat'].setValue(351);w.load_recipe(path)
    assert w.recipe()==saved
    w.include.setText('bad');w.edited();assert not w.run_button.isEnabled()
    assert 'lower:upper' in w.notice.text()


def test_desktop_two_source_engine_has_explicit_joint_contract(window,qtbot):
    w=window;qtbot.mouseClick(w.add,QtCore.Qt.MouseButton.LeftButton)
    assert len(w.recipe()['objects'])==2
    assert not w.run_button.isEnabled() # These anchors are too close for ordinary PypeIt mode.
    w.engine.setCurrentIndex(1)
    assert w.recipe()['schema_version']==2
    assert w.recipe()['engine_version']=='efospec-joint-1'
    assert not w.manual.isEnabled() and not w.sky_auto.isEnabled()
    assert w.degree.isEnabled()
    qtbot.mouseClick(w.remove,QtCore.Qt.MouseButton.LeftButton)
    assert len(w.recipe()['objects'])==1


def test_desktop_cancel_and_restart_preserves_parent(window,qtbot,monkeypatch):
    from efospec.inventory import sha256
    w=window;original=sha256(Path(w.exposure.result['product']))
    monkeypatch.setattr(w.backend,'worker_command',lambda *args:[sys.executable,'-c','import time;time.sleep(120)'])
    qtbot.mouseClick(w.run_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:w.cancel_button.isEnabled())
    first=w.backend.job['id']
    qtbot.mouseClick(w.cancel_button,QtCore.Qt.MouseButton.LeftButton)
    assert w.backend.job_status()['status']=='cancelled'
    assert w.backend.process.poll() is not None
    assert sha256(Path(w.exposure.result['product']))==original
    qtbot.mouseClick(w.run_button,QtCore.Qt.MouseButton.LeftButton)
    assert w.backend.job['id']!=first
    w.close();assert w.backend.process.poll() is not None


def test_desktop_real_worker_and_revision_open(window,qtbot,monkeypatch):
    w=window
    original=w.backend.worker_command
    monkeypatch.setattr(w.backend,'worker_command',lambda *args:original(*args)+['--skip-report'])
    qtbot.mouseClick(w.run_button,QtCore.Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda:w.backend.job_status()['status']!='running',timeout=30000)
    w.poll_job()
    assert w.backend.job_status()['status']=='complete',w.log.toPlainText()
    assert w.history.count()==1 and w.open_revision.isEnabled()
    assert w.details.isVisible()
    w.sky_auto.setChecked(False);w.include.setText('invalid');w.edited();w.poll_job()
    assert not w.run_button.isEnabled()  # Completion polling must not override recipe validation.
    parent=w.backend.run
    qtbot.mouseClick(w.open_revision,QtCore.Qt.MouseButton.LeftButton)
    assert w.backend.run!=parent
    assert w.exposure is not None


def test_file_picker_opens_run(window,qtbot,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(window.backend.run))
    qtbot.mouseClick(window.open_button,QtCore.Qt.MouseButton.LeftButton)
    assert window.exposures.count()==1


def test_loaded_fields_and_bounded_background_are_readable(window,qtbot):
    w=window
    from efospec.desktop import common_sky_bands
    assert w.source_values()[0]==w.exposure.primary_object()
    for key,field in w.sources.fields.items():
        assert field.value()==pytest.approx(w.exposure.primary_object()[key],abs=1e-6)
        assert field.lineEdit().width()>60 and field.lineEdit().height()>10
    w.manual.setChecked(False)
    assert not w.sources.isEnabled() and not w.add.isEnabled()
    assert w.recipe()['objects']==[]
    w.manual.setChecked(True)
    assert w.sources.isEnabled() and w.add.isEnabled()
    assert w.include.isReadOnly()
    assert w.recipe()['sky']=={'mode':'pypeit_local','include':[],'exclude':[],
                              'degree':2,'sigma_clip':4.,'width_pixels':30,'minimum_width_pixels':15}
    from efospec.local_sky import exposure_sky_inputs
    selected,_,_=exposure_sky_inputs(w.exposure,w.recipe())
    w.sky_auto.setChecked(False)
    assert not w.include.isReadOnly()
    assert w.recipe()['sky']['include']==common_sky_bands(selected,w.exposure.window.origin[1])
    w.set_view_mode('Pan');assert w.toolbar.mode and not w.selector.active
    w.set_view_mode('Inspect');assert not w.toolbar.mode and w.selector.active


def test_last_night_preference_and_missing_directory_fallback(qtbot,saved_exposure,tmp_path):
    from efospec.desktop import ExtractionWindow,initial_run
    run,reference,_=saved_exposure
    settings=QtCore.QSettings(str(tmp_path/'preferences.ini'),QtCore.QSettings.Format.IniFormat)
    assert initial_run(None,settings) is None
    w=ExtractionWindow(run,reference,settings=settings);qtbot.addWidget(w)
    assert initial_run(None,settings)==str(run.resolve())
    assert initial_run('explicit-night',settings)=='explicit-night'
    assert settings.value('last_product')=='test_f.fits'
    settings.setValue('last_run',str(tmp_path/'missing'))
    assert initial_run(None,settings) is None
    w.close()


def test_failed_link_opens_extraction_panel_in_spectra(window,monkeypatch):
    from PySide6 import QtWidgets
    import efospec.background_gui as gui
    class Panel(QtWidgets.QWidget):
        runningChanged=QtCore.Signal(bool)
        def __init__(self,packet,*a,parent=None):super().__init__(parent);self.packet=packet
        def is_running(self):return False
    monkeypatch.setattr(gui,'BackgroundEditor',Panel)
    w=window;raw='failed.fits'
    w.session.manifest['errors'].append({'path':raw,'object':'Failed target','code':'background_support_required','error':'background'})
    w.reviews.addItem('Failed target',{'raw':raw})
    w.select_raw(raw)
    assert w.tabs.currentIndex()==0
    assert w.review_editor.isVisible()
    assert w.review_editor.packet['raw_name']==raw
    assert w.exposure is None  # never edit a stale successful spectrum
