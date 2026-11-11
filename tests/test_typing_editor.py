"""Native Qt acceptance controls for typing annotations."""
import pytest
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pytestqt")
from efospec import typing_metadata as tm
from test_typing_metadata import typing_run

def test_native_editor_acceptance_and_revision(typing_run, qtbot):
    from efospec.typing_editor import TypingEditor
    from PySide6.QtCore import Qt, QPoint
    widget=TypingEditor(); qtbot.addWidget(widget);widget.open_run(typing_run);widget.show()
    widget.reviewer.setText('Qt observer')
    for key,value in dict(host_name='Galaxy',host_source='NED reference',host_redshift='0.03',
                          adopted_redshift='0.03',adopted_redshift_source='NED reference').items():
        widget.fields[key].setText(value)
    widget.fields['adopted_redshift_kind'].setCurrentText('host_catalogue')
    qtbot.mouseClick(widget.save_button, Qt.MouseButton.LeftButton)
    assert 'not saved' in widget.notice.text()
    assert not (typing_run/'typing-metadata.json').exists()
    qtbot.mouseClick(widget.accept_host, Qt.MouseButton.LeftButton, pos=QPoint(8, 8))
    qtbot.mouseClick(widget.accept_redshift, Qt.MouseButton.LeftButton, pos=QPoint(8, 8))
    qtbot.mouseClick(widget.save_button, Qt.MouseButton.LeftButton)
    assert 'Saved metadata revision' in widget.notice.text()
    r=tm.load(typing_run)['spectra'][0]
    assert r['host_status']=='accepted' and r['redshift_review']['reviewer']=='Qt observer'
    assert not widget.accept_host.isChecked()
