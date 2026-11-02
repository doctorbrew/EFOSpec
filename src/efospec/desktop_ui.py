"""Qt-only presentation components for the extraction workspace."""
from copy import deepcopy
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets as Q

STYLE = '''
QMainWindow, QWidget#workspace { background: #f2f4f8; }
QWidget { color: #25334b; font-size: 13px; }
QLabel { background: transparent; }
QFrame#topbar { background: #18263d; border: 0; }
QLabel#brand { color: #ffffff; font-size: 23px; font-weight: 700; }
QLabel#brandDetail { color: #a6b7d0; font-size: 12px; }
QLabel#eyebrow { color: #78869c; font-size: 10px; font-weight: 600; }
QLabel#sectionTitle { color: #25334b; font-size: 14px; font-weight: 600; }
QLabel#targetTitle { color: #18263d; font-size: 25px; font-weight: 600; }
QLabel#muted { color: #718097; font-size: 11px; }
QLabel#chip { background: #e9eff8; color: #4e6485; border-radius: 6px; padding: 6px 10px; font-size: 11px; }
QLabel#notice { background: #edf3fb; color: #506888; border-radius: 7px; padding: 10px; font-size: 11px; }
QLabel#notice[invalid="true"] { color: #9d4538; background: #fff0eb; }
QFrame#card { background: white; border: 1px solid #e2e7f0; border-radius: 10px; }
QFrame#footer { background: #ffffff; border-top: 1px solid #e2e7f0; }
QScrollArea { background: transparent; border: 0; }
QWidget#inspector { background: transparent; }
QPushButton, QToolButton { background: #ffffff; color: #475a76; border: 1px solid #dce3ee; border-radius: 7px; padding: 8px 12px; font-weight: 500; }
QPushButton:hover, QToolButton:hover { background: #edf3fd; border-color: #bacce9; }
QPushButton:pressed, QToolButton:checked { background: #e2ecfc; border-color: #9ab8e7; color: #295aac; }
QPushButton#primary { background: #3469cc; color: #ffffff; border: 1px solid #3469cc; font-weight: 600; padding: 12px; }
QPushButton#primary:hover { background: #285ab9; }
QPushButton:disabled, QToolButton:disabled { color: #a1acbd; background: #f3f5f8; border-color: #e7ebf1; }
QPushButton#primary:disabled { background: #dce5f4; color: #8c9db8; border-color: #dce5f4; }
QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox { background: #f8faff; border: 1px solid #dde5f0; border-radius: 6px; padding: 7px 9px; min-height: 18px; selection-background-color: #3469cc; }
QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid #7f9ed2; background: #ffffff; }
QLineEdit:read-only { color: #687c98; background: #f0f4fa; }
QComboBox:disabled, QDoubleSpinBox:disabled { color: #94a1b4; background: #f3f5f8; }
QDoubleSpinBox QLineEdit { border: 0; background: transparent; padding: 0; min-height: 0; }
QComboBox::down-arrow { image: url("CHEVRON"); width: 12px; height: 12px; }
QComboBox::drop-down { width: 24px; border: 0; }
QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #e6eefb; selection-color: #25334b; padding: 6px; }
QCheckBox { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 15px; height: 15px; }
QPlainTextEdit { background: #f8faff; border: 1px solid #e2e7f0; border-radius: 8px; padding: 8px; font-family: monospace; font-size: 11px; }
QProgressBar { border: 0; background: #e9eef6; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #3469cc; border-radius: 2px; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollBar:vertical { width: 6px; background: transparent; }
QScrollBar::handle:vertical { background: #cdd6e3; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #f2f4f8; color: #728099; font-size: 11px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #63718a; padding: 12px 22px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #295aac; border-bottom: 2px solid #3469cc; }
QTabBar::tab:disabled { color: #a1acbd; }
'''.replace('CHEVRON', (Path(__file__).parent/'assets/chevron-down.svg').as_posix())


def label(text, role='muted', wrap=False):
    item=Q.QLabel(text);item.setObjectName(role);item.setWordWrap(wrap)
    item.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    return item


def card(title):
    frame=Q.QFrame();frame.setObjectName('card')
    layout=Q.QVBoxLayout(frame);layout.setContentsMargins(16,14,16,16);layout.setSpacing(10)
    layout.addWidget(label(title,'sectionTitle'))
    return frame,layout


class SourceEditor(Q.QWidget):
    """One readable source form, with a selector for the optional companion."""
    changed=QtCore.Signal()

    def __init__(self):
        super().__init__();self._objects=[];self._loading=False
        layout=Q.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(10)
        self.selector=Q.QComboBox();self.selector.setAccessibleName('Selected source');layout.addWidget(self.selector)
        self.name=Q.QLineEdit();self.name.setAccessibleName('Source label')
        self.kind=Q.QComboBox();self.kind.addItem('Point source','point');self.kind.addItem('Galaxy candidate','galaxy')
        self.kind.setAccessibleName('Source kind')
        layout.addWidget(self.name);layout.addWidget(self.kind)
        grid=Q.QGridLayout();grid.setHorizontalSpacing(12);grid.setVerticalSpacing(5);layout.addLayout(grid)
        self.fields={}
        for i,(key,title) in enumerate((('spat','Spatial centre'),('spec','Spectral anchor'),('fwhm','FWHM'),('radius','Aperture radius'))):
            field=Q.QDoubleSpinBox();field.setRange(0,100000);field.setDecimals(6);field.setSingleStep(.25)
            field.setLocale(QtCore.QLocale.c())
            field.setSizePolicy(Q.QSizePolicy.Policy.Ignored,Q.QSizePolicy.Policy.Fixed)
            field.setKeyboardTracking(False);field.setAccessibleName(title);field.setSuffix(' px')
            grid.addWidget(label(title),2*(i//2),i%2);grid.addWidget(field,2*(i//2)+1,i%2)
            self.fields[key]=field;field.valueChanged.connect(self._commit)
        self.selector.currentIndexChanged.connect(self._select)
        self.name.editingFinished.connect(self._commit);self.kind.currentIndexChanged.connect(self._commit)

    def set_objects(self,objects,selected=0):
        self._objects=deepcopy(objects);self._loading=True
        self.selector.clear()
        for obj in objects:self.selector.addItem('Primary source' if obj['id']=='primary' else 'Companion source')
        self.selector.setCurrentIndex(min(selected,len(objects)-1));self._loading=False;self._select()

    def _select(self,*_):
        if self._loading or self.selector.currentIndex()<0:return
        self._loading=True;obj=self._objects[self.selector.currentIndex()]
        self.name.setText(obj['label']);self.kind.setCurrentIndex(self.kind.findData(obj['kind']))
        for key,field in self.fields.items():field.setValue(obj[key])
        self._loading=False

    def _commit(self,*_):
        if self._loading or not self._objects:return
        obj=self._objects[self.selector.currentIndex()]
        obj.update(label=self.name.text(),kind=self.kind.currentData(),**{k:f.value() for k,f in self.fields.items()})
        self.changed.emit()

    def objects(self):
        return deepcopy(self._objects)

    def place(self,spec,spat):
        if not self._objects:return
        self._loading=True;self.fields['spat'].setValue(spat);self.fields['spec'].setValue(spec)
        self._loading=False;self._commit()
