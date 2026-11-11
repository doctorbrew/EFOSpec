"""Native Qt desktop extraction frontend; science runs in shared Python workers."""
import json
import os
from pathlib import Path
import sys
os.environ['QT_API']='pyside6'
from PySide6 import QtCore, QtGui, QtWidgets as Q
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from matplotlib.ticker import AutoMinorLocator
from matplotlib.colors import ListedColormap
import numpy as np
from astropy.io import fits
from .jobs import Workbench
from .recipes import sky_mask
from .desktop_ui import STYLE, SourceEditor, card, label
from .desktop_session import resolve_session
from .review_handoff import failures, failure_log, parse_review_url

RED='#f47777';BLUE='#9fc6d1';NAVY='#24384b'


def bands(text):
    if not text.strip():return []
    try:
        result=[[float(v) for v in piece.strip().split(':')] for piece in text.split(',')]
        if any(len(pair)!=2 for pair in result):raise ValueError
        return result
    except ValueError:
        raise ValueError('Background bands use lower:upper, separated by commas') from None


def band_text(values):
    return ', '.join(f'{lo:g}:{hi:g}' for lo,hi in values)


class ExtractionWindow(Q.QMainWindow):
    def __init__(self, run=None, reference_root=None, *, settings=None):
        super().__init__()
        self.backend=None;self.exposure=None;self.reference_root=reference_root;self.settings=settings
        self.session=None;self.review_editor=None
        self.loading=False;self.last_completed=None;self.selector=None;self.saved_bands=[]
        app=Q.QApplication.instance();app.setStyle('Fusion')
        app.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)
        palette=app.style().standardPalette();palette.setColor(QtGui.QPalette.ColorRole.WindowText,QtGui.QColor(NAVY))
        app.setPalette(palette)
        families=QtGui.QFontDatabase.families()
        self.font_family=next((f for f in ('Inter','Avenir Next','Segoe UI','DejaVu Sans') if f in families),'sans-serif')
        self.setFont(QtGui.QFont(self.font_family,11));self.setStyleSheet(STYLE)
        self.setWindowTitle('EFOSpec');self.resize(1480,960)
        central=Q.QWidget();central.setObjectName('workspace');self.setCentralWidget(central)
        layout=Q.QVBoxLayout(central);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        top=Q.QFrame();top.setObjectName('topbar');bar=Q.QHBoxLayout(top);bar.setContentsMargins(24,15,24,15)
        logo_path=Path(__file__).parent/'assets/efospec-mark.png'
        self.setWindowIcon(QtGui.QIcon(str(logo_path)))
        self.logo=Q.QLabel();self.logo.setAccessibleName('EFOSpec logo');self.logo.setFixedSize(44,44)
        logo=QtGui.QPixmap(str(logo_path));ratio=self.devicePixelRatioF()
        logo=logo.scaled(round(44*ratio),round(44*ratio),QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation)
        logo.setDevicePixelRatio(ratio);self.logo.setPixmap(logo)
        self.logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter);bar.addWidget(self.logo);bar.addSpacing(6)
        bar.addWidget(label('EFOSpec','brand'));bar.addStretch()
        self.path_label=label('No night loaded','brandDetail');bar.addWidget(self.path_label);bar.addSpacing(16)
        self.open_button=Q.QPushButton('Open night…');self.open_button.clicked.connect(self.choose_run);bar.addWidget(self.open_button)
        layout.addWidget(top)
        self.tabs=Q.QTabWidget();layout.addWidget(self.tabs,1)
        body=Q.QWidget();body_layout=Q.QHBoxLayout(body);body_layout.setContentsMargins(20,20,20,10);body_layout.setSpacing(16)
        self.tabs.addTab(body,'Spectra')
        sidebar=Q.QWidget();sidebar.setFixedWidth(342);side=Q.QVBoxLayout(sidebar);side.setContentsMargins(0,0,0,0);side.setSpacing(12)
        body_layout.addWidget(sidebar)
        self.exposures=Q.QComboBox();self.exposures.setAccessibleName('Exposure');self.exposures.currentIndexChanged.connect(self.change_exposure)
        side.addWidget(label('EXPOSURE','eyebrow'));side.addWidget(self.exposures)
        scroll=Q.QScrollArea();scroll.setWidgetResizable(True);side.addWidget(scroll,1)
        controls=Q.QWidget();controls.setObjectName('inspector');self.editor=controls;scroll.setWidget(controls)
        form=Q.QVBoxLayout(controls);form.setContentsMargins(0,0,6,0);form.setSpacing(12)
        source,source_layout=card('01  Source & aperture');form.addWidget(source)
        self.sources=SourceEditor();source_layout.addWidget(self.sources);self.sources.changed.connect(self.edited)
        source_layout.addWidget(label('Click the 2D frame to move the selected anchor. Coordinates are raw, binned pixels.',wrap=True))
        row=Q.QHBoxLayout();self.add=Q.QPushButton('+ Companion');self.remove=Q.QPushButton('Remove')
        row.addWidget(self.add);row.addWidget(self.remove);source_layout.addLayout(row)
        self.add.clicked.connect(self.add_source);self.remove.clicked.connect(self.remove_source)
        sky,sky_layout=card('02  Background');form.addWidget(sky)
        self.sky_auto=Q.QCheckBox('Nearest clean bands on both sides');self.sky_auto.setChecked(True);sky_layout.addWidget(self.sky_auto)
        self.sky_width=Q.QSpinBox();self.sky_width.setRange(15,50);self.sky_width.setValue(30)
        sky_layout.addWidget(label('Preferred width per side · pixels (minimum 15)'));sky_layout.addWidget(self.sky_width)
        self.sky_degree=Q.QSpinBox();self.sky_degree.setRange(1,3);self.sky_degree.setValue(2)
        sky_layout.addWidget(label('Spatial degree · 1 slope, 2 curved, 3 cubic'));sky_layout.addWidget(self.sky_degree)
        self.sky_width.valueChanged.connect(self.edited);self.sky_degree.valueChanged.connect(self.edited)
        self.include=Q.QLineEdit();self.exclude=Q.QLineEdit()
        self.include.setAccessibleName('Included background bands');self.exclude.setAccessibleName('Excluded background bands')
        sky_layout.addWidget(label('Include · lower:upper'));sky_layout.addWidget(self.include)
        sky_layout.addWidget(label('Exclude · optional'));sky_layout.addWidget(self.exclude);self.exclude.setPlaceholderText('No excluded bands')
        self.background_hint=label('',wrap=True);sky_layout.addWidget(self.background_hint)
        self.sky_auto.toggled.connect(self.background_changed)
        self.include.editingFinished.connect(self.edited);self.exclude.editingFinished.connect(self.edited)
        engine,engine_layout=card('03  Extraction');form.addWidget(engine)
        self.engine=Q.QComboBox();self.engine.addItems(['PypeIt · bounded background','Joint profiles · experimental','Legacy PypeIt · recipe replay']);engine_layout.addWidget(self.engine)
        self.manual=Q.QCheckBox('Use selected source anchors');self.manual.setChecked(True);engine_layout.addWidget(self.manual)
        self.degree=Q.QComboBox();self.degree.addItems(['Select from held-out sky','Constant','Linear','Quadratic']);engine_layout.addWidget(self.degree);self.degree.setVisible(False)
        self.manual.toggled.connect(self.source_mode_changed);self.engine.currentIndexChanged.connect(self.engine_changed);self.degree.currentIndexChanged.connect(self.edited)
        recipebar=Q.QHBoxLayout();self.save=Q.QPushButton('Save recipe');self.load=Q.QPushButton('Load recipe')
        recipebar.addWidget(self.save);recipebar.addWidget(self.load);form.addLayout(recipebar);form.addStretch()
        self.save.clicked.connect(self.save_recipe_dialog);self.load.clicked.connect(self.load_recipe_dialog)
        self.notice=label('Open a completed night to begin.','notice',True);side.addWidget(self.notice)
        jobbar=Q.QHBoxLayout();self.run_button=Q.QPushButton('Extract new revision');self.run_button.setObjectName('primary');self.cancel_button=Q.QPushButton('Cancel');self.cancel_button.setVisible(False)
        jobbar.addWidget(self.run_button,1);jobbar.addWidget(self.cancel_button);side.addLayout(jobbar)
        self.run_button.clicked.connect(self.start_job);self.cancel_button.clicked.connect(self.cancel_job)
        self.progress=Q.QProgressBar();self.progress.setTextVisible(False);self.progress.setRange(0,1);self.progress.setValue(0);self.progress.hide();side.addWidget(self.progress)
        panel=Q.QWidget();panel_layout=Q.QVBoxLayout(panel);panel_layout.setContentsMargins(0,0,0,0);panel_layout.setSpacing(12);body_layout.addWidget(panel,1)
        heading=Q.QHBoxLayout();titles=Q.QVBoxLayout()
        self.target_title=label('Your next spectrum','targetTitle');self.context_label=label('Open a night to inspect and refine its extraction.','muted',True)
        titles.addWidget(self.target_title);titles.addWidget(self.context_label);heading.addLayout(titles,1)
        self.snr_label=label('—','chip');heading.addWidget(self.snr_label);panel_layout.addLayout(heading)
        figure_card,figure_layout=card('Spectrum & spatial diagnostics');panel_layout.addWidget(figure_card,1)
        tools=Q.QHBoxLayout();self.view_buttons={}
        for name in ('Inspect','Pan','Zoom'):
            button=Q.QToolButton();button.setText(name);button.setCheckable(True)
            button.clicked.connect(lambda checked,n=name:self.set_view_mode(n));tools.addWidget(button);self.view_buttons[name]=button
        self.view_buttons['Inspect'].setChecked(True)
        reset=Q.QPushButton('Reset view');reset.clicked.connect(lambda:self.toolbar.home());tools.addWidget(reset);tools.addStretch()
        self.profile_mode=Q.QComboBox();self.profile_mode.addItems(['Summed spatial profiles','Excess spatial scatter']);self.profile_mode.currentIndexChanged.connect(self.redraw);tools.addWidget(self.profile_mode)
        figure_layout.addLayout(tools)
        self.figure=Figure(figsize=(11,8),dpi=100,layout='constrained',facecolor='white')
        self.canvas=FigureCanvasQTAgg(self.figure);figure_layout.addWidget(self.canvas,1)
        self.toolbar=NavigationToolbar2QT(self.canvas,self);self.toolbar.hide()
        grid=self.figure.add_gridspec(2,2,height_ratios=[1,1.12]);self.spectrum_ax=self.figure.add_subplot(grid[0,:])
        self.image_ax=self.figure.add_subplot(grid[1,0]);self.profile_ax=self.figure.add_subplot(grid[1,1])
        self.canvas.mpl_connect('button_press_event',self.pick_source)
        figure_layout.addWidget(label('Coral: source aperture   ·   Blue: selected background   ·   Drag the spatial profile to add a sky band.'))
        self.details_button=Q.QToolButton();self.details_button.setText('Revisions & activity');self.details_button.setCheckable(True)
        self.details_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.details_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        panel_layout.addWidget(self.details_button)
        self.details,details_layout=card('Extraction activity');self.details.hide();panel_layout.addWidget(self.details)
        historybar=Q.QHBoxLayout();self.history=Q.QComboBox();historybar.addWidget(self.history,1)
        self.open_revision=Q.QPushButton('Open revision');historybar.addWidget(self.open_revision);self.open_revision.clicked.connect(self.show_revision);details_layout.addLayout(historybar)
        self.log=Q.QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(100);details_layout.addWidget(self.log)
        self.details_button.toggled.connect(self.toggle_details)
        self.review_page=Q.QWidget();self.review_layout=Q.QVBoxLayout(self.review_page)
        self.review_layout.setContentsMargins(20,20,20,10)
        review_bar=Q.QHBoxLayout();self.reviews=Q.QComboBox();self.reviews.setAccessibleName('Source-review exposure')
        self.reviews.addItem('Open a night or a source-review packet',None)
        self.reviews.currentIndexChanged.connect(self.change_review);review_bar.addWidget(self.reviews,1)
        self.review_open=Q.QPushButton('Open review packet…');self.review_open.clicked.connect(self.choose_review);review_bar.addWidget(self.review_open)
        self.review_layout.addLayout(review_bar)
        self.review_notice=label('Select a failed-exposure QC packet to choose its source and local background.','notice',True)
        self.review_layout.addWidget(self.review_notice)
        self.failure_details=Q.QPlainTextEdit();self.failure_details.setReadOnly(True)
        self.failure_details.setAccessibleName('Reduction error log');self.failure_details.setMaximumHeight(240)
        self.failure_details.hide();self.review_layout.addWidget(self.failure_details)
        self.failure_figures=Q.QTabWidget();self.failure_figures.hide()
        self.review_layout.addWidget(self.failure_figures,1)
        self.review_placeholder=label('Source identity is selected by the observer. Original raw files and products are preserved.',wrap=True)
        self.review_layout.addWidget(self.review_placeholder,1)
        self.tabs.addTab(self.review_page,'Source review')
        from .typing_editor import TypingEditor
        self.typing_editor=TypingEditor();self.tabs.addTab(self.typing_editor,'Host & redshift')
        self.timer=QtCore.QTimer(self);self.timer.setInterval(350);self.timer.timeout.connect(self.poll_job);self.timer.start()
        self.cancel_button.setEnabled(False);self.run_button.setEnabled(False);self.open_revision.setEnabled(False);self.editor.setEnabled(False)
        for combo in self.findChildren(Q.QComboBox):
            combo.setSizeAdjustPolicy(Q.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        self.statusBar().showMessage('Ready · original products are preserved')
        if run:self.open_run(run)

    def toggle_details(self,visible):
        self.details.setVisible(visible)
        self.details_button.setArrowType(QtCore.Qt.ArrowType.DownArrow if visible else QtCore.Qt.ArrowType.RightArrow)

    def set_view_mode(self,name):
        current=str(self.toolbar.mode)
        if current:self.toolbar.pan() if 'pan' in current else self.toolbar.zoom()
        if name=='Pan':self.toolbar.pan()
        elif name=='Zoom':self.toolbar.zoom()
        for key,button in self.view_buttons.items():button.setChecked(key==name)
        if self.selector:self.selector.set_active(name=='Inspect')

    def background_changed(self,*_):
        automatic=self.sky_auto.isChecked()
        self.include.setReadOnly(automatic);self.exclude.setReadOnly(automatic)
        if automatic:
            self.include.setText(band_text(self.saved_bands) if self.engine.currentIndex()==2 else '');self.exclude.clear()
        elif self.engine.currentIndex()==0 and self.exposure and not self.include.text().strip() and self.manual.isChecked():
            from .local_sky import exposure_sky_inputs
            try:
                proposed=self.exposure.default_recipe()
                proposed.update(source_mode='manual',objects=self.source_values())
                proposed['sky']=dict(mode='pypeit_local',include=[],exclude=[],degree=self.sky_degree.value(),
                    sigma_clip=4.,width_pixels=self.sky_width.value(),minimum_width_pixels=15)
                mask,_,_=exposure_sky_inputs(self.exposure,proposed)
                self.include.setText(band_text(common_sky_bands(mask,self.exposure.window.origin[1])))
            except (ValueError,IndexError):pass
        self.background_hint.setText('Nearest clean bands; may narrow to 15 pixels. Both sides are required. Inspect the overlay.' if automatic
                                    else 'Drag the spatial profile or edit bands. Source wings are excluded.')
        self.edited()

    def error(self,exc):
        self.notice.setText(str(exc));self.notice.setProperty('invalid',True);self.notice.style().unpolish(self.notice);self.notice.style().polish(self.notice)
        self.statusBar().showMessage(str(exc))

    def choose_run(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Open an observing night or reduction folder')
        if path:self.open_run(path)

    def open_run(self,path):
        try:
            raw = None
            if str(path).startswith('efospec:'):
                path, raw = parse_review_url(str(path))
            if self.is_running() or (self.review_editor and self.review_editor.is_running()):
                raise ValueError('Finish or cancel the extraction before changing nights.')
            session=resolve_session(path)
            new=Workbench(session.run,self.reference_root) if session.manifest['results'] else None
            if self.backend:self.backend.close()
            self.backend=new;self.session=session;self.exposure=None
            self.typing_editor.open_run(session.run)
            self.path_label.setText(session.night);self.path_label.setToolTip(str(session.run))
            previous=(self.settings.value('last_product','') if self.settings and self.settings.value('last_run')==str(session.selected) else '')
            self.exposures.blockSignals(True);self.exposures.clear()
            for e in new.exposures if new else []:self.exposures.addItem(f'{e["object"]} · {e["grism"]} · {e["exptime"]:g} s',e['id'])
            index=self.exposures.findData(previous)
            if index>=0:self.exposures.setCurrentIndex(index)
            self.exposures.blockSignals(False);self.change_exposure();self.refresh_history()
            self.clear_review()
            self.reviews.blockSignals(True);self.reviews.clear();self.reviews.addItem('Select a source-review exposure…',None)
            for packet in session.reviews:
                info=json.loads(packet.read_text())
                self.reviews.addItem(f'{info.get("object", "Unverified source")} · {info["raw_name"]}',str(packet))
            reviewed = {json.loads(p.read_text())['raw_name'] for p in session.reviews}
            for item in failures(session.manifest):
                name=Path(item.get('path', '')).name
                if name and name not in reviewed:
                    self.reviews.addItem(f'{item.get("object", "Unknown")} · {name}', {'raw':name})
                    reviewed.add(name)
            self.reviews.blockSignals(False)
            self.tabs.setTabText(1,f'Source review ({self.reviews.count()-1})')
            self.review_notice.setText('Choose the source explicitly; polynomial background extraction remains experimental.' if session.reviews
                                      else 'Choose a failed exposure to inspect its log. Manual extraction requires a compatible review packet.')
            if session.warnings:self.review_notice.setText(self.review_notice.text()+'\n'+'\n'.join(session.warnings))
            self.tabs.setCurrentIndex(0 if new else 1)
            if not new:
                self.editor.setEnabled(False);self.run_button.setEnabled(False)
                self.target_title.setText('No extracted spectra');self.context_label.setText('Review failed exposures in the Source review tab.')
                self.snr_label.setText('—')
                for ax in (self.spectrum_ax,self.image_ax,self.profile_ax):ax.clear()
                self.canvas.draw_idle()
            if session.reviews and (not new or session.selected.name=='review.json'):
                self.reviews.setCurrentIndex(1);self.tabs.setCurrentIndex(1)
            if raw:self.select_raw(raw)
            if self.settings:self.settings.setValue('last_run',str(session.selected));self.settings.sync()
        except (OSError,ValueError,KeyError,ImportError) as exc:self.error(exc)

    def select_raw(self, raw):
        if not self.session:raise ValueError('Open a reduction run before selecting an exposure.')
        for index in range(1, self.reviews.count()):
            data=self.reviews.itemData(index)
            name=data['raw'] if isinstance(data,dict) else json.loads(Path(data).read_text())['raw_name']
            if name==raw:
                self.reviews.setCurrentIndex(index);self.tabs.setCurrentIndex(1)
                return
        raise ValueError('No failed exposure with this filename in the selected run: '+raw)

    def choose_review(self):
        path,_=Q.QFileDialog.getOpenFileName(self,'Open source-review packet','','Review packet (review.json)')
        if path:self.open_run(path)

    def clear_review(self):
        if self.review_editor:
            self.review_editor.close();self.review_layout.removeWidget(self.review_editor);self.review_editor.deleteLater()
            self.review_editor=None
        self.review_placeholder.show()
        self.review_notice.show()
        self.failure_details.clear();self.failure_details.hide()
        while self.failure_figures.count():
            widget=self.failure_figures.widget(0);self.failure_figures.removeTab(0);widget.deleteLater()
        self.failure_figures.hide()

    def change_review(self,*_):
        path=self.reviews.currentData()
        self.clear_review()
        if not path:return
        raw=path['raw'] if isinstance(path,dict) else json.loads(Path(path).read_text())['raw_name']
        item=next((e for e in failures(self.session.manifest) if Path(e.get('path','')).name==raw), None)
        if item:
            self.failure_details.setPlainText(failure_log(self.session.run,item));self.failure_details.show()
        if isinstance(path,dict):
            self.review_notice.setText(f'{item.get("object",raw)} · {item.get("code","Review required")}')
            self.show_review_figures(raw)
            self.review_placeholder.setText('This exposure is loaded for failure inspection. No compatible manual-extraction '
                'packet is available for this reduction route. Native calibration recovery, wavelength repair and '
                'unsupported setups require their corresponding engine support; no extraction has been started.')
            return
        try:
            from .background_gui import BackgroundEditor
            panel=BackgroundEditor(path,self.reference_root,parent=self.review_page)
            self.review_editor=panel;self.review_placeholder.hide()
            self.review_layout.addWidget(panel,1);panel.runningChanged.connect(self.poll_job)
            self.review_notice.setVisible(bool(self.session and self.session.warnings))
        except (OSError,ValueError,KeyError,ImportError) as exc:self.review_notice.setText(str(exc))

    def show_review_figures(self, raw):
        """Reuse saved, house-styled previews; never generate a replacement spectrum."""
        from .inventory import sha256
        for record in self.session.manifest.get('review_counts', []):
            if Path(record['raw']).name!=raw:continue
            try:
                for name,digest in record['product_sha256'].items():
                    path=Path(name);path.resolve().relative_to(self.session.run)
                    if sha256(path)!=digest:raise ValueError('Review counts changed since reduction.')
                folder=Path(record['product']).parent.parent/'plots'
                folder.resolve().relative_to(self.session.run)
                for name in ('counts','traces','profiles'):
                    path=folder/(name+'.png')
                    if not path.is_file():continue
                    view=Q.QLabel();view.setPixmap(QtGui.QPixmap(str(path)).scaledToWidth(
                        1000,QtCore.Qt.TransformationMode.SmoothTransformation))
                    view.setAccessibleName('Saved review '+name)
                    scroll=Q.QScrollArea();scroll.setWidget(view)
                    self.failure_figures.addTab(scroll,name.title())
                self.failure_figures.setVisible(self.failure_figures.count()>0)
            except (OSError,ValueError) as exc:
                self.failure_details.appendPlainText('Saved figures unavailable: '+str(exc))

    def change_exposure(self,*_):
        from pypeit.pkg.exceptions import PypeItError
        if not self.backend or not self.exposures.currentData():return
        try:
            self.exposure=self.backend.exposure(self.exposures.currentData())
            mode='raw-only' if self.exposure.context.calibration else 'archived references'
            association=self.exposure.result.get('target',{}).get('association','unverified')
            r=self.exposure.result
            self.target_title.setText(r['object'])
            self.context_label.setText(f'{r["grism"]}  /  {r["slit"]}  ·  {r["exptime_s"]:g} s  ·  {mode}\nAssociation: {association.replace("_"," ")}')
            self.snr_label.setText(f'S/N  {r["median_native_snr_4000_8500"]:.1f} / pixel')
            if self.settings:
                self.settings.setValue('last_run',str(self.session.selected));self.settings.setValue('last_product',self.exposures.currentData())
                self.settings.sync()
            self.editor.setEnabled(True)
            self.loading=True
            self.engine.setCurrentIndex(0)
            self.set_sources([self.exposure.primary_object()]);self.manual.setChecked(True)
            self.saved_bands=common_sky_bands(self.exposure.images.get('sky_input_mask'),self.exposure.window.origin[1])
            self.sky_auto.setChecked(True);self.background_changed()
            self.loading=False;self.edited()
        except (OSError,ValueError,KeyError,PypeItError) as exc:
            self.loading=False;self.exposure=None;self.error(exc);self.editor.setEnabled(False);self.run_button.setEnabled(False)
            for ax in (self.spectrum_ax,self.image_ax,self.profile_ax):ax.clear()
            self.canvas.draw_idle()

    def set_sources(self,objects):
        self.sources.set_objects(objects)
        self.remove.setEnabled(self.manual.isChecked() and len(objects)>1);self.add.setEnabled(self.manual.isChecked() and len(objects)<2)

    def source_mode_changed(self,*_):
        manual=self.manual.isChecked();self.sources.setEnabled(manual)
        self.add.setEnabled(manual and len(self.source_values())<2)
        self.remove.setEnabled(manual and len(self.source_values())>1)
        self.edited()

    def source_values(self):
        return self.sources.objects()

    def add_source(self):
        if not self.exposure:return
        objects=self.source_values()
        if len(objects)>=2:return
        obj=dict(objects[0],id='host',label='host',kind='galaxy',spat=objects[0]['spat']+15.)
        self.set_sources(objects+[obj]);self.sources.selector.setCurrentIndex(1);self.edited()

    def remove_source(self):
        self.set_sources(self.source_values()[:1]);self.edited()

    def engine_changed(self,*_):
        joint=self.engine.currentIndex()==1;self.degree.setEnabled(joint);self.degree.setVisible(joint)
        self.sky_width.setVisible(self.engine.currentIndex()==0);self.sky_degree.setVisible(self.engine.currentIndex()==0)
        if joint:
            self.manual.setChecked(True);self.sky_auto.setChecked(False)
            if self.exposure and not self.include.text().strip():
                self.background_hint.setText('Select nearby background on both sides of the sources.')
        self.manual.setEnabled(not joint);self.sky_auto.setEnabled(not joint);self.edited()

    def recipe(self):
        if not self.exposure:raise ValueError('Open a completed exposure first')
        r=self.exposure.default_recipe()
        r['source_mode']='manual' if self.manual.isChecked() else 'automatic'
        r['objects']=self.source_values() if self.manual.isChecked() else []
        r['sky']={'mode':'automatic' if self.sky_auto.isChecked() else 'regions',
                  'include':[] if self.sky_auto.isChecked() else bands(self.include.text()),
                  'exclude':[] if self.sky_auto.isChecked() else bands(self.exclude.text())}
        if self.engine.currentIndex()==1:
            r.update(schema_version=2,engine_version='efospec-joint-1',background_degree=['auto',0,1,2][self.degree.currentIndex()])
        elif self.engine.currentIndex()==0:
            if r['source_mode']=='automatic':
                if not self.sky_auto.isChecked():raise ValueError('Select a source anchor to edit background bands')
                r['sky']={'mode':'bounded','include':[],'exclude':[]}
            else:
                r['sky'].update(mode='pypeit_local',degree=self.sky_degree.value(),sigma_clip=4.)
                if self.sky_auto.isChecked():r['sky'].update(width_pixels=self.sky_width.value(),minimum_width_pixels=15)
        return r

    def edited(self,*_):
        if self.loading or not self.exposure:return
        try:
            recipe=self.recipe();self.backend.validate(self.exposures.currentData(),recipe)
            self.notice.setProperty('invalid',False);self.notice.style().unpolish(self.notice);self.notice.style().polish(self.notice)
            self.notice.setText('Fixed profiles · conditional errors. Inspect residuals and background alternatives.'
                if self.engine.currentIndex()==1 else 'Ready to extract · saves a new revision.')
            self.run_button.setEnabled(not self.is_running())
        except (ValueError,TypeError,AttributeError) as exc:self.error(exc);self.run_button.setEnabled(False)
        self.redraw()

    def is_running(self):
        return bool(self.backend and self.backend.job and self.backend.job['status']=='running')

    def redraw(self,*_):
        if self.loading or not self.exposure:return
        e=self.exposure;images=e.images
        for ax in (self.spectrum_ax,self.image_ax,self.profile_ax):ax.clear()
        with fits.open(e.result['product']) as h:
            values=np.where(h['VALID'].data.astype(bool),h[0].data[:,0,:],np.nan)
            wave=h[0].header['CRVAL1']+np.arange(values.shape[1])*h[0].header['CD1_1']
        ax=self.spectrum_ax
        ax.plot(wave,values[0]/1e-16,color=RED,lw=1,label='Joint fixed profiles' if e.result.get('joint') else 'PypeIt')
        ax.fill_between(wave,(values[0]-values[3])/1e-16,(values[0]+values[3])/1e-16,color=RED,alpha=.18,
            label=r'Conditional $\pm1\sigma$' if e.result.get('joint') else r'Propagated $\pm1\sigma$')
        ax.set(xlabel='Observed air wavelength [Å]',ylabel=r'$F_\lambda$ [$10^{-16}$ cgs / Å]',
               title='Extracted spectrum')
        ax.legend(fontsize=9,loc='upper right',frameon=False,ncol=2)
        ax.text(.5,.035,f'Median SNR = {e.result["median_native_snr_4000_8500"]:.1f} per pixel',ha='center',transform=ax.transAxes,fontsize=9,color='#718097')
        onslit=images.get('onslit',np.ones(images['data'].shape,dtype=bool)).astype(bool).copy()
        onslit[:,[0,-1]]=False
        residual=np.where(onslit,images['data']-images['sky'],np.nan);finite=residual[np.isfinite(residual)]
        low,high=np.percentile(finite,[5,99.5]);ny,nx=residual.shape;y0,x0=e.window.origin
        self.image_ax.imshow(residual.T,origin='lower',aspect='auto',cmap='gray',vmin=low,vmax=high,
            extent=[y0-.5,y0+ny-.5,x0-.5,x0+nx-.5],interpolation='nearest')
        self.image_ax.set(xlabel='Spectral detector pixel',ylabel='Spatial detector pixel',title='Sky-subtracted 2D Spectra')
        spatial=np.arange(nx)+x0;edges=np.linspace(np.nanmin(images['waveair']),np.nanmax(images['waveair']),4)
        for i,(lo,hi) in enumerate(zip(edges[:-1],edges[1:])):
            selected=(images['waveair']>=lo)&(images['waveair']<hi)&np.isfinite(residual)
            if self.profile_mode.currentIndex()==0:
                profile=np.where(selected,residual,0).sum(axis=0)
            else:
                variance=(np.maximum(images['data'],0)+e.frame['metadata']['ESO DET OUT1 RON']**2 if not e.context.processed
                    else np.divide(1,e.context.processed['ivar'],out=np.full(residual.shape,np.nan),where=e.context.processed['ivar']>0))
                profile=np.sqrt(np.maximum(0,np.nanvar(np.where(selected,residual,np.nan),axis=0)-np.nanmean(np.where(selected,variance,np.nan),axis=0)))
            self.profile_ax.plot(spatial,profile,lw=1,label=f'{lo:.0f}–{hi:.0f} Å',color=['#577590','#a59471',RED][i])
        self.profile_ax.set(xlabel='Spatial detector pixel',ylabel='Summed electrons' if self.profile_mode.currentIndex()==0 else 'Excess scatter [electrons]',title='Spatial profiles')
        self.profile_ax.legend(fontsize=8,frameon=False)
        try:
            recipe=self.recipe();mask=sky_mask(recipe,e.window)
            if recipe['sky']['mode']=='pypeit_local':
                from .local_sky import exposure_sky_inputs
                mask,_,_=exposure_sky_inputs(e,recipe)
            elif mask is None and self.engine.currentIndex()!=0:mask=images.get('sky_input_mask')
            if mask is not None:
                self.image_ax.imshow(np.where(mask.T,1.,np.nan),origin='lower',aspect='auto',
                    cmap=ListedColormap([BLUE]),alpha=.2,vmin=0,vmax=1,
                    extent=[y0-.5,y0+ny-.5,x0-.5,x0+nx-.5],interpolation='nearest')
                self.profile_ax.fill_between(spatial,0,mask.mean(axis=0),
                    transform=self.profile_ax.get_xaxis_transform(),color=BLUE,alpha=.2)
            for i,obj in enumerate(recipe['objects']):
                trace=images['trace']+x0;anchor=obj['spec']-y0
                trace=trace+obj['spat']-np.interp(anchor,np.arange(ny),trace)
                color=RED if i==0 else '#7c85ba'
                self.image_ax.plot(np.arange(ny)+y0,trace,color=color,lw=1)
                self.image_ax.fill_between(np.arange(ny)+y0,trace-obj['radius'],trace+obj['radius'],color=color,alpha=.2)
                self.profile_ax.axvline(obj['spat'],color=color,lw=1)
                self.profile_ax.axvspan(obj['spat']-obj['radius'],obj['spat']+obj['radius'],color=color,alpha=.16)
        except (ValueError,TypeError,KeyError,AttributeError):pass  # Invalid edits remain visible in the controls.
        for ax in (self.spectrum_ax,self.image_ax,self.profile_ax):
            ax.tick_params(which='both',direction='in',top=True,right=True,labelsize=9,colors='#63718a')
            ax.xaxis.label.set(fontsize=10,color=NAVY,fontfamily=self.font_family,fontweight='normal')
            ax.yaxis.label.set(fontsize=10,color=NAVY,fontfamily=self.font_family,fontweight='normal')
            ax.set_title(ax.get_title(),fontsize=12,color=NAVY,fontfamily=self.font_family,fontweight='medium',pad=14)
            for tick in ax.get_xticklabels()+ax.get_yticklabels():tick.set_fontfamily(self.font_family);tick.set_fontweight('normal')
            for spine in ax.spines.values():spine.set_color('#d6deea')
            if ax is not self.image_ax:ax.grid(axis='y',color='#edf1f6',lw=.6,zorder=0)
            ax.xaxis.set_minor_locator(AutoMinorLocator());ax.yaxis.set_minor_locator(AutoMinorLocator())
        if self.selector:self.selector.disconnect_events()
        self.selector=SpanSelector(self.profile_ax,self.select_background,'horizontal',useblit=True,
                                   props={'facecolor':BLUE,'alpha':.3},button=1,minspan=.5)
        self.selector.set_active(not bool(self.toolbar.mode))
        self.canvas.draw_idle()

    def pick_source(self,event):
        if event.inaxes is not self.image_ax or event.button!=1 or self.toolbar.mode or not self.manual.isChecked():return
        self.sources.place(event.xdata,event.ydata)

    def select_background(self,lo,hi):
        if self.toolbar.mode or not self.exposure:return
        try:
            self.manual.setChecked(True)
            if self.sky_auto.isChecked():
                self.loading=True;self.sky_auto.setChecked(False);self.include.clear();self.exclude.clear();self.loading=False
            self.include.setText(band_text(bands(self.include.text())+[[round(lo,2),round(hi,2)]]));self.edited()
        except ValueError as exc:self.error(exc)

    def save_recipe(self,path):
        recipe=self.backend.validate(self.exposures.currentData(),self.recipe())['recipe']
        Path(path).write_text(json.dumps(recipe,indent=2)+'\n')

    def load_recipe(self,path):
        recipe=json.loads(Path(path).read_text());recipe=self.backend.validate(self.exposures.currentData(),recipe)['recipe']
        self.loading=True;self.engine.setCurrentIndex(1 if recipe['schema_version']==2 else (0 if recipe['sky']['mode'] in ('pypeit_local','bounded') else 2))
        self.manual.setChecked(recipe['source_mode']=='manual');self.set_sources(recipe['objects'] or [self.exposure.primary_object()])
        self.sky_auto.setChecked(recipe['sky']['mode'] in ('automatic','bounded') or (recipe['sky']['mode']=='pypeit_local' and not recipe['sky']['include']))
        self.sky_width.setValue(recipe['sky'].get('width_pixels',30));self.sky_degree.setValue(recipe['sky'].get('degree',2))
        self.include.setText(band_text(recipe['sky']['include']));self.exclude.setText(band_text(recipe['sky']['exclude']))
        self.degree.setCurrentIndex(['auto',0,1,2].index(recipe.get('background_degree','auto')))
        self.loading=False;self.background_changed()

    def save_recipe_dialog(self):
        path,_=Q.QFileDialog.getSaveFileName(self,'Save extraction recipe','','JSON (*.json)')
        if path:
            try:self.save_recipe(path)
            except (OSError,ValueError) as exc:self.error(exc)

    def load_recipe_dialog(self):
        path,_=Q.QFileDialog.getOpenFileName(self,'Load extraction recipe','','JSON (*.json)')
        if path:
            try:self.load_recipe(path)
            except (OSError,ValueError,KeyError) as exc:self.error(exc)

    def start_job(self):
        try:
            self.backend.start(self.exposures.currentData(),self.recipe());self.details_button.setChecked(True);self.poll_job()
        except (OSError,ValueError) as exc:self.error(exc)

    def cancel_job(self):
        if self.backend:self.backend.cancel();self.poll_job()

    def poll_job(self,*_):
        review_running=bool(self.review_editor and self.review_editor.is_running())
        running=self.is_running()
        self.tabs.setTabEnabled(0,not review_running);self.tabs.setTabEnabled(1,not running)
        self.open_button.setEnabled(not (running or review_running))
        self.review_open.setEnabled(not (running or review_running));self.reviews.setEnabled(not review_running)
        if not self.backend:return
        status=self.backend.job_status()
        if not status:return
        running=status['status']=='running'
        self.cancel_button.setEnabled(running);self.cancel_button.setVisible(running);self.progress.setVisible(running)
        if running:self.run_button.setEnabled(False)
        self.exposures.setEnabled(not running);self.editor.setEnabled(not running)
        self.progress.setRange(0,0 if running else 1);self.progress.setValue(0 if running else 1)
        self.log.setPlainText(status.get('log',''));self.statusBar().showMessage(f'Revision {status["id"]} · {status["status"]}')
        if not running and self.last_completed!=status['id']:
            self.last_completed=status['id'];self.refresh_history();self.edited()

    def refresh_history(self):
        self.history.clear()
        for record in self.backend.history() if self.backend else []:self.history.addItem(record['id'],record['directory'])
        self.open_revision.setEnabled(self.history.count()>0)

    def show_revision(self):
        if self.history.currentData():self.open_run(self.history.currentData())

    def closeEvent(self,event):
        if self.backend:self.backend.close()
        if self.review_editor:self.review_editor.close()
        self.timer.stop();event.accept()


class ReviewOpenEvents(QtCore.QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.received=False

    def eventFilter(self,watched,event):
        if event.type()==QtCore.QEvent.Type.FileOpen and event.url().scheme()=='efospec':
            self.received=True
            url=event.url().toString()
            def open_requested():
                self.window.open_run(url)
                self.window.show();self.window.raise_();self.window.activateWindow()
            QtCore.QTimer.singleShot(0,open_requested)
            return True
        return False


def launch(run=None,reference_root=None,*,smoke_test=False,raw=None):
    app=Q.QApplication.instance() or Q.QApplication(sys.argv[:1]);app.setApplicationName('EFOSpec')
    settings=None if smoke_test else QtCore.QSettings('EFOSpec','Desktop')
    if not smoke_test:run=initial_run(run,settings)
    # Install the URL receiver before loading remembered products. Loading can
    # process native events, and an incompatible old product must not lose the URL.
    window=ExtractionWindow(None,reference_root,settings=settings)
    handler=ReviewOpenEvents(window);app.installEventFilter(handler)
    window.show()
    def open_initial():
        if not handler.received and run:window.open_run(run)
        if raw:window.select_raw(raw)
    QtCore.QTimer.singleShot(0,open_initial)
    # Dispose Qt children while its event dispatcher is still alive. Python
    # callback cycles can otherwise keep them past QApplication destruction.
    app.aboutToQuit.connect(window.close)
    app.aboutToQuit.connect(window.deleteLater)
    if smoke_test:
        def finish():
            ready=run is None or (window.session is not None and (
                window.exposure is not None or window.review_editor is not None or window.reviews.currentData() is not None))
            print(json.dumps({'application':'EFOSpec','qt_platform':app.platformName(),
                'tabs':window.tabs.count(),'ready':ready,
                'review_selection':window.reviews.currentData(),
                'run':str(window.session.run) if window.session else None}),flush=True)
            window.close();app.exit(0 if ready else 1)
        QtCore.QTimer.singleShot(600,finish)
    elif run is None:QtCore.QTimer.singleShot(300,lambda:window.choose_run() if window.session is None else None)
    return app.exec()


def initial_run(explicit, settings):
    """Remember a local night without shipping anyone's data paths in the package."""
    if explicit is not None:return explicit
    saved=settings.value('last_run','')
    if saved:
        try:resolve_session(saved);return saved
        except (OSError,ValueError,KeyError):pass
    return None


def common_sky_bands(mask, origin):
    """Display the intersection of saved sky selections, without changing the mask."""
    if mask is None:return []
    keep=np.asarray(mask,dtype=bool).all(axis=0)
    edges=np.flatnonzero(np.diff(np.r_[False,keep,False]))+origin
    return edges.reshape(-1,2).tolist()
