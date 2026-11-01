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
    def __init__(self, run=None, reference_root=None):
        super().__init__()
        self.backend=None;self.exposure=None;self.reference_root=reference_root
        self.loading=False;self.last_completed=None;self.selector=None
        palette=self.palette()
        for role,color in ((QtGui.QPalette.ColorRole.Window,'#f7f5f0'),(QtGui.QPalette.ColorRole.WindowText,NAVY),
                           (QtGui.QPalette.ColorRole.Base,'white'),(QtGui.QPalette.ColorRole.Text,NAVY),
                           (QtGui.QPalette.ColorRole.Button,'white'),(QtGui.QPalette.ColorRole.ButtonText,NAVY),
                           (QtGui.QPalette.ColorRole.Highlight,NAVY),(QtGui.QPalette.ColorRole.HighlightedText,'white')):
            palette.setColor(role,QtGui.QColor(color))
        self.setPalette(palette)
        # Match native controls and Matplotlib icons to this light inspection theme.
        Q.QApplication.instance().setPalette(palette)
        Q.QApplication.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)
        self.setWindowTitle('EFOSpec · Desktop extraction');self.resize(1500,1000)
        self.setStyleSheet('''QMainWindow,QWidget {background:#f7f5f0;color:#24384b;}
            QGroupBox {font-weight:600;border:1px solid #d6d9da;border-radius:5px;margin-top:10px;padding-top:10px;}
            QGroupBox::title {subcontrol-origin:margin;left:9px;}
            QPushButton {padding:7px 12px;border:1px solid #b8c1c8;border-radius:4px;background:#fff;}
            QPushButton:disabled {color:#9ca5aa;} QLineEdit,QTableWidget,QComboBox,QPlainTextEdit {background:#fff;}
            QHeaderView::section {background:#e8ecee;padding:5px;}''')
        central=Q.QWidget();self.setCentralWidget(central);layout=Q.QVBoxLayout(central)
        bar=Q.QHBoxLayout();layout.addLayout(bar)
        self.open_button=Q.QPushButton('Open night…');self.open_button.clicked.connect(self.choose_run);bar.addWidget(self.open_button)
        self.exposures=Q.QComboBox();self.exposures.setMinimumWidth(400);bar.addWidget(self.exposures,1)
        self.exposures.currentIndexChanged.connect(self.change_exposure)
        self.path_label=Q.QLabel('Select a completed reduction');bar.addWidget(self.path_label)
        splitter=Q.QSplitter(QtCore.Qt.Orientation.Horizontal);layout.addWidget(splitter,1)
        controls=Q.QWidget();controls.setMinimumWidth(560);self.editor=controls;form=Q.QVBoxLayout(controls);splitter.addWidget(controls)
        self.context_label=Q.QLabel();self.context_label.setWordWrap(True);form.addWidget(self.context_label)
        self.engine=Q.QComboBox();self.engine.addItems(['PypeIt optimal + boxcar','Joint fixed profiles · experimental'])
        form.addWidget(Q.QLabel('Extraction engine'));form.addWidget(self.engine)
        self.manual=Q.QCheckBox('Manual source anchors');self.manual.setChecked(True);form.addWidget(self.manual)
        source=Q.QGroupBox('Sources · raw detector pixels, zero based');source_layout=Q.QVBoxLayout(source)
        self.sources=Q.QTableWidget(0,7);self.sources.setHorizontalHeaderLabels(['ID','Label','Kind','Spatial','Spectral','FWHM','Radius'])
        self.sources.horizontalHeader().setSectionResizeMode(Q.QHeaderView.ResizeMode.Stretch)
        self.sources.setMinimumHeight(130);source_layout.addWidget(self.sources)
        row=Q.QHBoxLayout();self.add=Q.QPushButton('Add companion');self.remove=Q.QPushButton('Remove companion')
        row.addWidget(self.add);row.addWidget(self.remove);source_layout.addLayout(row);form.addWidget(source)
        self.add.clicked.connect(self.add_source);self.remove.clicked.connect(self.remove_source)
        self.sources.itemChanged.connect(self.edited)
        self.manual.toggled.connect(self.edited);self.engine.currentIndexChanged.connect(self.engine_changed)
        hint=Q.QLabel('Click the 2D image to place the selected source.\nRadius is the boxcar half-width; FWHM sets the profile width.');hint.setWordWrap(True);form.addWidget(hint)
        sky=Q.QGroupBox('Background');sky_form=Q.QFormLayout(sky)
        self.sky_auto=Q.QCheckBox('Automatic PypeIt sky regions');self.sky_auto.setChecked(True)
        sky_form.addRow(self.sky_auto)
        self.include=Q.QLineEdit();self.exclude=Q.QLineEdit()
        self.include.setPlaceholderText('e.g. 480:510, 585:620');self.exclude.setPlaceholderText('Optional excluded bands')
        sky_form.addRow('Include',self.include);sky_form.addRow('Exclude',self.exclude)
        self.degree=Q.QComboBox();self.degree.addItems(['Select from held-out sky','Constant','Linear','Quadratic'])
        sky_form.addRow('Joint background',self.degree);self.degree.setEnabled(False)
        form.addWidget(sky)
        self.sky_auto.toggled.connect(self.edited);self.include.editingFinished.connect(self.edited);self.exclude.editingFinished.connect(self.edited)
        self.degree.currentIndexChanged.connect(self.edited)
        tip=Q.QLabel('Drag across the spatial-profile plot to add a background band. Source wings are always excluded.');tip.setWordWrap(True);form.addWidget(tip)
        self.profile_mode=Q.QComboBox();self.profile_mode.addItems(['Summed profiles in wavelength bins','Excess spatial scatter in wavelength bins'])
        form.addWidget(self.profile_mode);self.profile_mode.currentIndexChanged.connect(self.redraw)
        self.notice=Q.QLabel();self.notice.setWordWrap(True);form.addWidget(self.notice)
        recipebar=Q.QHBoxLayout();self.save=Q.QPushButton('Save recipe…');self.load=Q.QPushButton('Load recipe…')
        recipebar.addWidget(self.save);recipebar.addWidget(self.load);form.addLayout(recipebar)
        self.save.clicked.connect(self.save_recipe_dialog);self.load.clicked.connect(self.load_recipe_dialog)
        jobbar=Q.QHBoxLayout();self.run_button=Q.QPushButton('Extract new revision');self.cancel_button=Q.QPushButton('Cancel')
        jobbar.addWidget(self.run_button);jobbar.addWidget(self.cancel_button);form.addLayout(jobbar)
        self.run_button.clicked.connect(self.start_job);self.cancel_button.clicked.connect(self.cancel_job)
        self.progress=Q.QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);form.addWidget(self.progress)
        self.history=Q.QComboBox();form.addWidget(self.history)
        self.open_revision=Q.QPushButton('Open selected revision');form.addWidget(self.open_revision);self.open_revision.clicked.connect(self.show_revision)
        self.log=Q.QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(150);form.addWidget(self.log)
        form.addStretch()
        panel=Q.QWidget();panel_layout=Q.QVBoxLayout(panel);splitter.addWidget(panel)
        self.figure=Figure(figsize=(12,9),dpi=100,layout='constrained',facecolor='white')
        self.canvas=FigureCanvasQTAgg(self.figure)
        self.toolbar=NavigationToolbar2QT(self.canvas,self);panel_layout.addWidget(self.toolbar);panel_layout.addWidget(self.canvas,1)
        grid=self.figure.add_gridspec(2,2,height_ratios=[1,1.2]);self.spectrum_ax=self.figure.add_subplot(grid[0,:])
        self.image_ax=self.figure.add_subplot(grid[1,0]);self.profile_ax=self.figure.add_subplot(grid[1,1])
        self.canvas.mpl_connect('button_press_event',self.pick_source)
        splitter.setSizes([590,910])
        self.timer=QtCore.QTimer(self);self.timer.setInterval(350);self.timer.timeout.connect(self.poll_job);self.timer.start()
        self.cancel_button.setEnabled(False);self.run_button.setEnabled(False)
        self.editor.setEnabled(False)
        if run:self.open_run(run)

    def error(self,exc):
        self.notice.setText(str(exc));self.notice.setStyleSheet('color:#a53932')

    def choose_run(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Open a night with run.json')
        if path:self.open_run(path)

    def open_run(self,path):
        try:
            new=Workbench(path,self.reference_root)
            if self.backend:self.backend.close()
            self.backend=new;self.path_label.setText(Path(path).name)
            self.exposures.blockSignals(True);self.exposures.clear()
            for e in new.exposures:self.exposures.addItem(f'{e["object"]} · {e["grism"]} · {e["exptime"]:g} s',e['id'])
            self.exposures.blockSignals(False);self.change_exposure();self.refresh_history()
        except (OSError,ValueError,KeyError,ImportError) as exc:self.error(exc)

    def change_exposure(self,*_):
        if not self.backend or not self.exposures.currentData():return
        try:
            self.exposure=self.backend.exposure(self.exposures.currentData())
            mode='raw-only' if self.exposure.context.calibration else 'archived references'
            association=self.exposure.result.get('target',{}).get('association','unverified')
            self.context_label.setText(f'Calibration: {mode}.\nTarget association: {association.replace("_"," ")}.')
            self.editor.setEnabled(True)
            self.loading=True
            self.engine.setCurrentIndex(0)
            self.set_sources([self.exposure.primary_object()]);self.manual.setChecked(True)
            self.sky_auto.setChecked(True);self.include.clear();self.exclude.clear()
            self.loading=False;self.edited()
        except (OSError,ValueError,KeyError) as exc:
            self.loading=False;self.exposure=None;self.error(exc);self.editor.setEnabled(False)
            for ax in (self.spectrum_ax,self.image_ax,self.profile_ax):ax.clear()
            self.canvas.draw_idle()

    def set_sources(self,objects):
        self.sources.blockSignals(True);self.sources.setRowCount(len(objects))
        for row,obj in enumerate(objects):
            for col,key in enumerate(('id','label','kind','spat','spec','fwhm','radius')):
                val=obj[key];item=Q.QTableWidgetItem(f'{val:.3f}' if isinstance(val,(float,np.floating)) else str(val))
                if key=='id':item.setFlags(item.flags()&~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.sources.setItem(row,col,item)
        self.sources.blockSignals(False);self.sources.selectRow(0)

    def source_values(self):
        return [dict(zip(('id','label','kind','spat','spec','fwhm','radius'),
            [self.sources.item(row,col).text() if col<3 else float(self.sources.item(row,col).text()) for col in range(7)]))
            for row in range(self.sources.rowCount())]

    def add_source(self):
        if not self.exposure or self.sources.rowCount()>=2:return
        try:
            objects=self.source_values();obj=dict(objects[0],id='host',label='host',kind='galaxy',spat=objects[0]['spat']+15.)
            self.set_sources(objects+[obj]);self.sources.selectRow(1);self.edited()
        except (ValueError,AttributeError) as exc:self.error(exc)

    def remove_source(self):
        if self.sources.rowCount()==2:self.sources.removeRow(1);self.edited()

    def engine_changed(self,*_):
        joint=self.engine.currentIndex()==1;self.degree.setEnabled(joint)
        if joint:
            self.manual.setChecked(True);self.sky_auto.setChecked(False)
            if self.exposure and not self.include.text().strip():
                lo=self.exposure.window.origin[1];hi=lo+self.exposure.window.shape[1]
                self.include.setText(f'{lo+1}:{lo+30}, {hi-30}:{hi-1}')
        self.manual.setEnabled(not joint);self.sky_auto.setEnabled(not joint);self.edited()

    def recipe(self):
        if not self.exposure:raise ValueError('Open a completed exposure first')
        r=self.exposure.default_recipe()
        r['source_mode']='manual' if self.manual.isChecked() else 'automatic'
        r['objects']=self.source_values() if self.manual.isChecked() else []
        r['sky']={'mode':'automatic' if self.sky_auto.isChecked() else 'regions',
                  'include':bands(self.include.text()),'exclude':bands(self.exclude.text())}
        if self.engine.currentIndex()==1:
            r.update(schema_version=2,engine_version='efospec-joint-1',background_degree=['auto',0,1,2][self.degree.currentIndex()])
        return r

    def edited(self,*_):
        if self.loading or not self.exposure:return
        try:
            recipe=self.recipe();self.backend.validate(self.exposures.currentData(),recipe)
            self.notice.setStyleSheet('color:#405a68')
            self.notice.setText('Joint fit: fixed Gaussian profiles share the measured trace. Errors are conditional; inspect background alternatives and residuals.'
                if self.engine.currentIndex()==1 else 'PypeIt retraces each anchor and fits the profile. Saved inputs and accepted products remain unchanged.')
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
               title=f'{e.result["object"]} (EFOSC2 / {e.result["grism"]} · {e.result["exptime_s"]:g} s)')
        ax.legend(fontsize=11,loc='upper right')
        ax.text(.5,.035,f'Median SNR = {e.result["median_native_snr_4000_8500"]:.1f} per pixel',ha='center',transform=ax.transAxes,fontsize=11)
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
        self.profile_ax.legend(fontsize=9)
        try:
            recipe=self.recipe();mask=sky_mask(recipe,e.window)
            if mask is None:mask=images.get('sky_input_mask')
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
            ax.tick_params(which='both',direction='in',top=True,right=True,labelsize=12)
            ax.xaxis.set_minor_locator(AutoMinorLocator());ax.yaxis.set_minor_locator(AutoMinorLocator())
        if self.selector:self.selector.disconnect_events()
        self.selector=SpanSelector(self.profile_ax,self.select_background,'horizontal',useblit=True,
                                   props={'facecolor':BLUE,'alpha':.3},button=1,minspan=.5)
        self.canvas.draw_idle()

    def pick_source(self,event):
        if event.inaxes is not self.image_ax or event.button!=1 or self.toolbar.mode or not self.manual.isChecked():return
        row=max(0,self.sources.currentRow())
        if not self.sources.rowCount():return
        self.loading=True
        self.sources.item(row,3).setText(f'{event.ydata:.3f}');self.sources.item(row,4).setText(f'{event.xdata:.3f}')
        self.loading=False;self.edited()

    def select_background(self,lo,hi):
        if self.toolbar.mode or not self.exposure:return
        try:
            self.manual.setChecked(True);self.sky_auto.setChecked(False)
            self.include.setText(band_text(bands(self.include.text())+[[round(lo,2),round(hi,2)]]));self.edited()
        except ValueError as exc:self.error(exc)

    def save_recipe(self,path):
        recipe=self.backend.validate(self.exposures.currentData(),self.recipe())['recipe']
        Path(path).write_text(json.dumps(recipe,indent=2)+'\n')

    def load_recipe(self,path):
        recipe=json.loads(Path(path).read_text());recipe=self.backend.validate(self.exposures.currentData(),recipe)['recipe']
        self.loading=True;self.engine.setCurrentIndex(1 if recipe['schema_version']==2 else 0)
        self.manual.setChecked(recipe['source_mode']=='manual');self.set_sources(recipe['objects'] or [self.exposure.primary_object()])
        self.sky_auto.setChecked(recipe['sky']['mode']=='automatic');self.include.setText(band_text(recipe['sky']['include']));self.exclude.setText(band_text(recipe['sky']['exclude']))
        self.degree.setCurrentIndex(['auto',0,1,2].index(recipe.get('background_degree','auto')))
        self.loading=False;self.edited()

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
            self.backend.start(self.exposures.currentData(),self.recipe());self.poll_job()
        except (OSError,ValueError) as exc:self.error(exc)

    def cancel_job(self):
        if self.backend:self.backend.cancel();self.poll_job()

    def poll_job(self):
        if not self.backend:return
        status=self.backend.job_status()
        if not status:return
        running=status['status']=='running'
        self.cancel_button.setEnabled(running)
        if running:self.run_button.setEnabled(False)
        self.open_button.setEnabled(not running);self.exposures.setEnabled(not running)
        self.progress.setRange(0,0 if running else 1);self.progress.setValue(0 if running else 1)
        self.log.setPlainText(status.get('log',''));self.statusBar().showMessage(f'Revision {status["id"]} · {status["status"]}')
        if not running and self.last_completed!=status['id']:
            self.last_completed=status['id'];self.refresh_history();self.edited()

    def refresh_history(self):
        self.history.clear()
        for record in self.backend.history():self.history.addItem(record['id'],record['directory'])
        self.open_revision.setEnabled(self.history.count()>0)

    def show_revision(self):
        if self.history.currentData():self.open_run(self.history.currentData())

    def closeEvent(self,event):
        if self.backend:self.backend.close()
        self.timer.stop();event.accept()


def launch(run=None,reference_root=None):
    app=Q.QApplication.instance() or Q.QApplication(sys.argv[:1]);app.setApplicationName('EFOSpec')
    window=ExtractionWindow(run,reference_root);window.show()
    if run is None:QtCore.QTimer.singleShot(0,window.choose_run)
    return app.exec()
