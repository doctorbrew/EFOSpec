import json
from pathlib import Path

import pytest

from efospec.review_handoff import parse_review_url, review_url, failure_log


def test_link_roundtrip_preserves_exposure_and_metacharacters(tmp_path):
    run=tmp_path/'night with spaces & $literal'
    raw='EFOSC.2026-11-11T06:29:25.891.fits'
    assert parse_review_url(review_url(run,raw))==(str(run),raw)


@pytest.mark.parametrize('url', [
    'efospec://extract?run=/night&raw=a.fits',
    'efospec://review?run=/night&raw=a.fits&raw=b.fits',
    'efospec://review?run=/night&raw=../a.fits',
    'efospec://review?run=relative&raw=a.fits',
    'efospec://review?run=/night&raw=a.fits&execute=true',
])
def test_link_cannot_request_execution_or_ambiguous_selection(url):
    with pytest.raises(ValueError):parse_review_url(url)


def test_original_error_log_is_shown_and_missing_log_is_explicit(tmp_path):
    log=tmp_path/'error.log';log.write_text('Original traceback: exact geometry failure')
    item=dict(object='SNtest',path='/raw/a.fits',code='background_support_required',
              error='Trace moved',traceback=str(log))
    assert log.read_text() in failure_log(tmp_path,item)
    log.unlink()
    assert 'Original error log unavailable' in failure_log(tmp_path,item)


def test_native_failure_without_packet_is_selectable_and_displays_log(qtbot,tmp_path):
    pytest.importorskip('PySide6')
    from efospec.desktop import ExtractionWindow
    raw='failed.fits';log=tmp_path/'error.log';log.write_text('native failure traceback')
    item=dict(object='SNtest',path='/raw/'+raw,code='background_support_required',
              error='Trace moved',traceback=str(log))
    (tmp_path/'run.json').write_text(json.dumps(dict(results=[],errors=[item],skipped=[
        dict(object='SNtest',path='/raw/red.fits',code='unsupported_setup',reason='Gr16 route')
    ])))
    w=ExtractionWindow();qtbot.addWidget(w)
    w.open_run(review_url(tmp_path,raw))
    assert w.tabs.currentIndex()==1
    assert w.reviews.currentData()=={'raw':raw}
    assert 'native failure traceback' in w.failure_details.toPlainText()
    assert not w.run_button.isEnabled() and w.review_editor is None
    w.select_raw('red.fits')
    assert 'Gr16 route' in w.failure_details.toPlainText()
    assert 'native failure traceback' not in w.failure_details.toPlainText()
    with pytest.raises(ValueError,match='No failed exposure'):w.select_raw('other.fits')
    w.close()


def test_saved_review_counts_figures_load_only_for_matching_unchanged_product(qtbot,tmp_path):
    pytest.importorskip('PySide6')
    from PIL import Image
    from efospec.desktop import ExtractionWindow
    from efospec.inventory import sha256
    product=tmp_path/'counts/products/spectrum.fits';product.parent.mkdir(parents=True)
    product.write_bytes(b'unchanged counts')
    plots=tmp_path/'counts/plots';plots.mkdir()
    Image.new('RGB',(16,16)).save(plots/'counts.png')
    item=dict(path='/raw/a.fits',object='SNtest',code='wavelength_validation_failed',error='Independent residual')
    manifest=dict(results=[],errors=[item],review_counts=[dict(raw='/raw/a.fits',product=str(product),
        product_sha256={str(product):sha256(product)})])
    (tmp_path/'run.json').write_text(json.dumps(manifest))
    w=ExtractionWindow();qtbot.addWidget(w);w.open_run(review_url(tmp_path,'a.fits'))
    assert w.failure_figures.count()==1
    product.write_bytes(b'changed counts')
    w.change_review()
    assert w.failure_figures.count()==0
    assert 'Review counts changed' in w.failure_details.toPlainText()
    w.close()


def test_old_pypeit_product_cannot_crash_exposure_handoff(qtbot,tmp_path,monkeypatch):
    from efospec import desktop
    from pypeit.pkg.exceptions import PypeItDataModelError
    class OldWorkbench:
        exposures=[dict(object='Old',grism='Gr13',exptime=60,id='old.fits')]
        def __init__(self,*args):pass
        def exposure(self,*args):raise PypeItDataModelError('Old product data model version')
        def history(self):return []
        def job_status(self):return None
        def close(self):pass
    monkeypatch.setattr(desktop,'Workbench',OldWorkbench)
    (tmp_path/'run.json').write_text(json.dumps(dict(results=[{}],errors=[
        dict(object='SNtest',path='/raw/failed.fits',code='background_support_required')
    ])))
    w=desktop.ExtractionWindow();qtbot.addWidget(w)
    w.open_run(review_url(tmp_path,'failed.fits'))
    assert w.reviews.currentData()=={'raw':'failed.fits'}
    assert not w.run_button.isEnabled()
    assert 'Old product data model version' in w.notice.text()
    w.close()


def test_native_url_event_selects_failed_exposure_after_startup(qtbot,tmp_path):
    from efospec.desktop import ExtractionWindow, ReviewOpenEvents
    from PySide6 import QtCore, QtWidgets
    (tmp_path/'run.json').write_text(json.dumps(dict(results=[],errors=[
        dict(object='SNtest',path='/raw/native-event.fits',code='background_support_required')])))
    class OpenEvent(QtCore.QEvent):
        def __init__(self):super().__init__(QtCore.QEvent.Type.FileOpen)
        def url(self):return QtCore.QUrl(review_url(tmp_path,'native-event.fits'))
    w=ExtractionWindow();qtbot.addWidget(w)
    handler=ReviewOpenEvents(w);app=QtWidgets.QApplication.instance();app.installEventFilter(handler)
    QtCore.QCoreApplication.sendEvent(app,OpenEvent())
    qtbot.waitUntil(lambda:w.reviews.currentData()=={'raw':'native-event.fits'})
    assert handler.received and w.tabs.currentIndex()==1
    app.removeEventFilter(handler);w.close()
