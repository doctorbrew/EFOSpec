"""Experimental native Qt background editor; scientific calculations stay in Python."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import uuid

os.environ['QT_API']='pyside6'
from PySide6 import QtCore, QtWidgets
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .revisions import FailedExposure
from .polynomial_background import calculate
from .recipes import validate_recipe
from .background_qc import draw_background,draw_candidates
from .desktop_ui import card,label
from .figure_style import house_style,style


class BackgroundEditor(QtWidgets.QWidget):
    """Reusable source-review panel; also usable as a standalone window."""
    runningChanged = QtCore.Signal(bool)

    def __init__(self, packet, reference_root=None, parent=None):
        super().__init__(parent)
        self.packet=Path(packet).resolve()
        self.review=json.loads(self.packet.read_text())
        self.exposure=FailedExposure(self.review['parent_run'],self.review['raw_name'],reference_root)
        self.worker=None;self.last_result=None;self.loaded_object=None
        self.setWindowTitle('EFOSpec — aperture and local background review')
        self.resize(1500,1050)
        layout=QtWidgets.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        layout.addWidget(label(self.review['object'],'targetTitle'))
        layout.addWidget(label('Select a trace using the acquisition image and observing records. '
            'This experimental background fit produces count-level boxcar spectra.','notice',True))
        split=QtWidgets.QSplitter();layout.addWidget(split,1)
        scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(300)
        scroll.setMaximumWidth(400);split.addWidget(scroll)
        inspector=QtWidgets.QWidget();inspector.setObjectName('inspector');scroll.setWidget(inspector)
        controls=QtWidgets.QVBoxLayout(inspector);controls.setContentsMargins(0,0,10,0);controls.setSpacing(14)
        source,source_layout=card('01 Trace and aperture');controls.addWidget(source)
        form=QtWidgets.QFormLayout();form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);source_layout.addLayout(form)
        self.candidate=QtWidgets.QComboBox();self.candidate.addItem('Choose a candidate…')
        for c in self.review['candidates']:self.candidate.addItem(f"C{c['number']}: x={c['anchor_raw_x']:.3f}")
        form.addRow('Trace candidate',self.candidate)
        self.position=QtWidgets.QDoubleSpinBox();self.position.setDecimals(3)
        self.position.setRange(self.exposure.window.origin[1]+1,self.exposure.window.origin[1]+self.exposure.window.shape[1]-2)
        form.addRow('Aperture centre x (raw, zero based)',self.position)
        self.spectral_anchor=QtWidgets.QSpinBox();self.spectral_anchor.setRange(self.exposure.window.origin[0],self.exposure.window.origin[0]+self.exposure.window.shape[0]-1)
        self.spectral_anchor.setValue(self.exposure.window.origin[0]+self.exposure.window.shape[0]//2)
        form.addRow('Trace anchor y (raw detector row)',self.spectral_anchor)
        self.radius=QtWidgets.QDoubleSpinBox();self.radius.setRange(.5,30);self.radius.setValue(7.)
        form.addRow('Boxcar half-width (pixels)',self.radius)
        background,background_layout=card('02 Background');controls.addWidget(background)
        form=QtWidgets.QFormLayout();form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);background_layout.addLayout(form)
        self.bands=QtWidgets.QLineEdit();self.bands.setPlaceholderText('520:535, 555:575')
        self.bands.setToolTip('Raw detector columns; upper endpoints excluded.')
        form.addRow('Background bands x (lo:hi, …)',self.bands)
        self.degree=QtWidgets.QSpinBox();self.degree.setRange(0,3);self.degree.setValue(2)
        form.addRow('Polynomial degree',self.degree)
        self.clipping=QtWidgets.QDoubleSpinBox();self.clipping.setRange(3.,8.);self.clipping.setValue(4.)
        form.addRow('Iterative rejection (sigma)',self.clipping)
        self.mouse_mode=QtWidgets.QComboBox();self.mouse_mode.addItems(['Inspect / toolbar','Click aperture centre','Drag background band'])
        form.addRow('Plot mouse action',self.mouse_mode)
        self.panel=QtWidgets.QComboBox();self.panel.addItems(['Data and background fit','Background-subtracted profile'])
        form.addRow('Plot view',self.panel)
        buttons=QtWidgets.QGridLayout();controls.addLayout(buttons)
        for column,(title,slot) in enumerate([('Load recipe',self.load_recipe),('Save recipe',self.save_recipe)]):
            button=QtWidgets.QPushButton(title);button.clicked.connect(slot);buttons.addWidget(button,0,column)
        button=QtWidgets.QPushButton('Preview background');button.clicked.connect(self.preview);buttons.addWidget(button,1,0,1,2)
        self.extract_button=QtWidgets.QPushButton('Extract new revision');self.extract_button.setObjectName('primary')
        self.extract_button.clicked.connect(self.extract);controls.addWidget(self.extract_button)
        self.cancel_button=QtWidgets.QPushButton('Cancel extraction');self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False);controls.addWidget(self.cancel_button);controls.addStretch()
        diagnostics,plots=card('Source and background diagnostics');split.addWidget(diagnostics);split.setStretchFactor(1,1)
        # Native screen density is separate from 300-dpi JPG/PDF export. Keep
        # house font point sizes; a 300-dpi screen canvas triples their size.
        self.figure=Figure(figsize=(18,11),dpi=100);self.canvas=FigureCanvasQTAgg(self.figure)
        plots.addWidget(NavigationToolbar2QT(self.canvas,self));plots.addWidget(self.canvas,1)
        self.message=QtWidgets.QLabel('Select the trace and two background bands before fitting.');self.message.setWordWrap(True)
        self.message.setObjectName('notice');layout.addWidget(self.message)
        self.runningChanged.connect(self.update_worker_controls)
        self.candidate.currentIndexChanged.connect(self.choose_candidate)
        self.canvas.mpl_connect('button_press_event',self.click_position)
        self.mouse_mode.currentIndexChanged.connect(self.configure_selector)
        self.panel.currentIndexChanged.connect(lambda _:self.preview())
        for field in (self.position,self.radius,self.clipping,self.spectral_anchor,self.degree):
            field.setLocale(QtCore.QLocale.c())
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(False)
        draw_candidates(self.figure,self.exposure);self.screen_layout();self.configure_selector();self.canvas.draw()

    @house_style
    def screen_layout(self):
        # Retain the house font/LaTeX/colours, with point sizes suited to a Qt
        # canvas. Publication exports use the unchanged background_qc helper.
        for ax in self.figure.axes:
            ax.tick_params(which='both',labelsize=11)
            ax.xaxis.label.set_fontsize(13);ax.yaxis.label.set_fontsize(13);ax.title.set_fontsize(14)
            legend=ax.get_legend()
            if legend:
                handles,labels=ax.get_legend_handles_labels();legend.remove()
                style.styled_legend(ax,handles=handles,labels=labels,loc='upper right',ncol=1,fontsize=10)
        if self.figure._suptitle:self.figure._suptitle.set_fontsize(14)
        self.figure.subplots_adjust(left=.12,right=.97,bottom=.17,top=.88)

    def configure_selector(self):
        from matplotlib.widgets import SpanSelector
        if hasattr(self,'selector'):self.selector.disconnect_events()
        self.selector=SpanSelector(self.figure.axes[0],self.select_band,'horizontal',
            useblit=False,minspan=1.,props={'alpha':.2,'facecolor':'0.5'})
        self.selector.set_active(self.mouse_mode.currentIndex()==2)

    def select_band(self,low,high):
        addition=f'{low:.2f}:{high:.2f}'
        self.bands.setText((self.bands.text()+', ' if self.bands.text().strip() else '')+addition)
        self.message.setText('Background band added; Preview background to validate and fit.')

    def click_position(self,event):
        if self.mouse_mode.currentIndex()==1 and event.inaxes is self.figure.axes[0] and event.xdata is not None:
            self.position.setValue(event.xdata)
            self.message.setText('Aperture centre updated; preview before extracting.')

    def choose_candidate(self,index):
        self.loaded_object=None
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(index>0)
        if index>0:self.position.setValue(self.review['candidates'][index-1]['anchor_raw_x'])

    def recipe(self):
        index=self.candidate.currentIndex()-1
        if index<0:raise ValueError('Select a candidate; source identity is never inferred from brightness.')
        value=deepcopy(json.loads(Path(self.review['candidates'][index]['recipe']).read_text()))
        if self.loaded_object is not None:value['objects'][0]=deepcopy(self.loaded_object)
        bands=[]
        for text in self.bands.text().split(','):
            pair=[float(v.strip()) for v in text.strip().split(':')]
            if len(pair)!=2:raise ValueError('Each band must be lo:hi, with comma-separated bands.')
            bands.append(pair)
        value['objects'][0].update(spat=self.position.value(),spec=float(self.spectral_anchor.value()),radius=self.radius.value())
        value['sky']=dict(mode='polynomial',include=bands,exclude=[],degree=self.degree.value(),sigma_clip=self.clipping.value())
        return value

    def preview(self):
        try:
            recipe,result=calculate(self.exposure,self.recipe())
            draw_background(self.figure,self.exposure,recipe,result,panel=self.panel.currentIndex());self.screen_layout();self.canvas.draw()
            self.configure_selector()
            self.last_result=result
            self.message.setText(f"Background fit valid for {result['valid'].mean():.1%} of rows. "
                                 'Review residuals and fit bands; this does not confirm the target or validate host subtraction.')
            return recipe,result
        except Exception as exc:
            self.message.setText(str(exc));return None

    def save_recipe(self):
        result=self.preview()
        if result is None:return
        filename,_=QtWidgets.QFileDialog.getSaveFileName(self,'Save a new recipe',str(self.packet.parent/'background-recipe.json'),'JSON (*.json)')
        if filename:
            try:
                with Path(filename).open('x') as stream:json.dump(result[0],stream,indent=2)
                self.message.setText('Recipe saved: '+filename)
            except OSError as exc:self.message.setText(str(exc))

    def load_recipe(self):
        filename,_=QtWidgets.QFileDialog.getOpenFileName(self,'Load a saved recipe',str(self.packet.parent),'JSON (*.json)')
        if not filename:return
        try:
            value=validate_recipe(json.loads(Path(filename).read_text()),self.exposure.window,self.exposure.hashes)
            if value['sky']['mode']!='polynomial' or value['sky']['exclude']:
                raise ValueError('This editor currently loads polynomial recipes with included bands and no separate exclusions.')
            obj=value['objects'][0]
            index=min(range(len(self.review['candidates'])),key=lambda i:abs(self.review['candidates'][i]['anchor_raw_x']-obj['spat']))
            self.candidate.setCurrentIndex(index+1);self.position.setValue(obj['spat'])
            self.loaded_object=deepcopy(obj)
            self.spectral_anchor.setValue(int(obj['spec']));self.radius.setValue(obj['radius'])
            self.degree.setValue(value['sky']['degree']);self.clipping.setValue(value['sky']['sigma_clip'])
            self.bands.setText(', '.join(f'{lo:g}:{hi:g}' for lo,hi in value['sky']['include']))
            self.preview()
        except Exception as exc:self.message.setText(str(exc))

    def extract(self):
        if self.worker is not None and self.worker.state()!=QtCore.QProcess.ProcessState.NotRunning:
            self.message.setText('A worker is already running.');return
        result=self.preview()
        if result is None:return
        parent=QtWidgets.QFileDialog.getExistingDirectory(self,'Choose revision parent folder',str(self.packet.parent))
        if not parent:return
        token=datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
        recipe_file=Path(parent)/('background-'+token+'.json')
        try:
            with recipe_file.open('x') as stream:stream.write(json.dumps(result[0],indent=2)+'\n')
        except OSError as exc:
            self.message.setText('Cannot save extraction recipe: '+str(exc));return
        output=Path(parent)/('background-'+token)
        self.worker=QtCore.QProcess(self)
        self.worker.setStandardOutputFile(str(output)+'.log');self.worker.setStandardErrorFile(str(output)+'-error.log')
        self.worker.finished.connect(lambda code,status:self.worker_finished(code,output))
        self.worker.errorOccurred.connect(self.worker_error)
        self.worker.start(sys.executable,['-m','efospec','background-extract',str(self.exposure.run),
            '--failed-raw',self.review['raw_name'],'--recipe',str(recipe_file),'--output',str(output),
            '--reference-root',str(self.exposure.context.reference_root)])
        self.message.setText('Extracting to a new revision: '+str(output))
        self.runningChanged.emit(True)

    def is_running(self):
        return self.worker is not None and self.worker.state()!=QtCore.QProcess.ProcessState.NotRunning

    def update_worker_controls(self,running):
        self.extract_button.setEnabled(not running);self.cancel_button.setEnabled(running)

    def worker_finished(self,code,output):
        self.message.setText(f'Worker exit {code}; new revision: {output}')
        self.runningChanged.emit(False)

    def worker_error(self,error):
        self.message.setText(self.worker.errorString())
        self.runningChanged.emit(self.is_running())

    def cancel(self):
        if self.is_running():
            worker=self.worker;worker.terminate()
            self.message.setText('Cancelling extraction; earlier products remain unchanged.')
            timer=QtCore.QTimer(worker);timer.setSingleShot(True)
            timer.timeout.connect(lambda:worker.kill() if worker.state()!=QtCore.QProcess.ProcessState.NotRunning else None)
            timer.start(1000)

    def closeEvent(self,event):
        if self.worker is not None and self.worker.state()!=QtCore.QProcess.ProcessState.NotRunning:
            self.worker.terminate()
            if not self.worker.waitForFinished(1000):self.worker.kill();self.worker.waitForFinished(1000)
        event.accept()


def launch(packet):
    from .desktop import launch as launch_desktop
    return launch_desktop(packet)
