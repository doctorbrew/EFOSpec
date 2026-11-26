"""Experimental native Qt background editor; scientific calculations stay in Python."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import uuid
import re

os.environ['QT_API']='pyside6'
from PySide6 import QtCore, QtWidgets
from matplotlib.figure import Figure
from .desktop_canvas import ScientificCanvas as FigureCanvasQTAgg
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
        self.packet=Path(packet['parent_run'])/'review.json' if isinstance(packet,dict) else Path(packet).resolve()
        self.review=deepcopy(packet) if isinstance(packet,dict) else json.loads(self.packet.read_text())
        self.exposure=FailedExposure(self.review['parent_run'],self.review['raw_name'],reference_root)
        if 'candidates' not in self.review:
            self.review['candidates']=[]
            for i,c in enumerate(self.exposure.candidates,1):
                recipe=self.exposure.default_recipe();recipe['source_mode']='manual'
                recipe['objects']=[dict(id='primary',label=self.review['object'],kind='point',spec=float(self.exposure.window.origin[0]+self.exposure.window.shape[0]//2),spat=c['raw_spatial_pixel'],radius=7.,fwhm=4.)]
                self.review['candidates'].append(dict(number=i,anchor_raw_x=c['raw_spatial_pixel'],recipe=recipe))
        self.worker=None;self.last_result=None;self.loaded_object=None
        self.setWindowTitle('EFOSpec — aperture and local background review')
        self.resize(1500,1050)
        layout=QtWidgets.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        layout.addWidget(label(self.review['object'],'targetTitle'))
        layout.addWidget(label('Exposure: '+self.review['raw_name'],'muted',True))
        layout.addWidget(label('Select a trace using the acquisition image and observing records. '
            'Compare nearby bands, then extract native review counts or checked flux in a new revision.','notice',True))
        if self.exposure.context.calibration and not self.exposure.context.sky_qa.get('held_out_6363_pass',False):
            layout.addWidget(label('Wavelength validation failed in the parent run. Extracted counts remain review-only; wavelength-valid samples stay masked.','notice',True))
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
        self.bands=QtWidgets.QLineEdit();self.bands.setPlaceholderText('Example only: 520:535, 555:575')
        self.bands.setToolTip('Raw detector columns; upper endpoints excluded.')
        form.addRow('Background bands x (lo:hi, …)',self.bands)
        self.degree=QtWidgets.QSpinBox();self.degree.setRange(0,3);self.degree.setValue(2)
        if self.exposure.context.calibration:self.degree.setMinimum(1)
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
        self.readiness=label('','notice',True);self.readiness.setAccessibleName('Extraction requirements')
        controls.addWidget(self.readiness)
        self.extract_button=QtWidgets.QPushButton('Extract new revision');self.extract_button.setObjectName('primary')
        self.extract_button.clicked.connect(self.extract);controls.addWidget(self.extract_button)
        self.native_flux=QtWidgets.QCheckBox('Checked native PypeIt + flux recovery');self.native_flux.setVisible(bool(self.exposure.context.calibration));controls.addWidget(self.native_flux)
        self.counts_method=QtWidgets.QComboBox()
        self.counts_method.addItems(['Review counts: refit trace with PypeIt','Review counts: keep saved trace (polynomial boxcar)'])
        self.counts_method.setVisible(bool(self.exposure.context.calibration));controls.addWidget(self.counts_method)
        self.counts_method.setToolTip('Saved-trace boxcar is a separate experiment; it does not repair or validate a failed trace or wavelength solution.')
        self.search_button=QtWidgets.QPushButton('Compare nearby background bands');self.search_button.clicked.connect(lambda:self.extract(search=True));controls.addWidget(self.search_button)
        self.sky_policy=QtWidgets.QComboBox();self.sky_policy.addItems(['three-line','two-anchor','full-spectrum']);self.sky_policy.setToolTip('Wavelength acceptance for native flux extraction');controls.addWidget(self.sky_policy)
        self.sky_policy.setCurrentText(self.exposure.context.sky_qa.get('validation_policy','three-line'))
        self.cancel_button=QtWidgets.QPushButton('Cancel extraction');self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False);controls.addWidget(self.cancel_button);controls.addStretch()
        diagnostics,plots=card('Source and background diagnostics');split.addWidget(diagnostics);split.setStretchFactor(1,1)
        # Native screen density is separate from 300-dpi JPG/PDF export. Keep
        # house font point sizes; a 300-dpi screen canvas triples their size.
        self.figure=Figure(figsize=(18,11),dpi=100);self.canvas=FigureCanvasQTAgg(self.figure)
        actions=QtWidgets.QHBoxLayout();plots.addLayout(actions)
        self.plot_actions={}
        for mode,title in enumerate(('Inspect','Click trace','Drag background')):
            button=QtWidgets.QPushButton(title);button.setCheckable(True)
            button.clicked.connect(lambda checked,m=mode:self.mouse_mode.setCurrentIndex(m))
            actions.addWidget(button);self.plot_actions[mode]=button
        clear=QtWidgets.QPushButton('Clear bands');clear.clicked.connect(self.clear_bands);actions.addWidget(clear)
        export=QtWidgets.QPushButton('Save PDF + JPG');export.clicked.connect(self.export_plot);actions.addWidget(export)
        self.toolbar=NavigationToolbar2QT(self.canvas,self)
        plots.addWidget(self.toolbar);plots.addWidget(self.canvas,1)
        self.message=QtWidgets.QLabel('Select the trace and two background bands before fitting.');self.message.setWordWrap(True)
        self.message.setObjectName('notice');layout.addWidget(self.message)
        self.worker_details=QtWidgets.QPlainTextEdit();self.worker_details.setReadOnly(True)
        self.worker_details.setMaximumHeight(130);self.worker_details.hide();layout.addWidget(self.worker_details)
        self.runningChanged.connect(self.update_worker_controls)
        self.candidate.currentIndexChanged.connect(self.choose_candidate)
        self.canvas.mpl_connect('button_press_event',self.click_position)
        self.mouse_mode.currentIndexChanged.connect(self.configure_selector)
        self.panel.currentIndexChanged.connect(lambda _:self.preview())
        for field in (self.position,self.radius,self.clipping,self.spectral_anchor,self.degree):
            field.setLocale(QtCore.QLocale.c())
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(False)
        self.bands.textChanged.connect(self.update_readiness)
        for field in (self.position,self.radius,self.spectral_anchor,self.degree,self.clipping):
            field.valueChanged.connect(self.update_readiness)
        self.native_flux.toggled.connect(self.update_readiness)
        self.counts_method.currentIndexChanged.connect(self.update_readiness)
        self.sky_policy.currentTextChanged.connect(self.update_readiness)
        self.update_readiness()
        draw_candidates(self.figure,self.exposure);self.screen_layout();self.configure_selector();self.canvas.draw()

    def validated_recipe(self):
        value=validate_recipe(self.recipe(),self.exposure.window,self.exposure.hashes)
        if self.exposure.context.calibration and (len(value['sky']['include'])!=2 or
                any(not 15<=hi-lo<=50 for lo,hi in value['sky']['include'])):
            raise ValueError('Choose two background bands, each 15–50 pixels wide, one on each side.')
        return value

    def update_readiness(self,*_):
        missing=[]
        bands_invalid=False
        selected=self.candidate.currentIndex()>0
        entered=bool(self.bands.text().strip())
        if not selected:missing.append('Choose a trace candidate, or use Click aperture centre on the plot.')
        if not entered:missing.append('Enter two background bands or use Drag background band. Grey example text is not a selection.')
        if selected and entered:
            try:self.validated_recipe()
            except (ValueError,KeyError,TypeError) as exc:
                missing.append(str(exc));bands_invalid=True
        running=self.is_running()
        refit=self.native_flux.isChecked() or self.counts_method.currentIndex()==0
        self.degree.setMinimum(1 if self.exposure.context.calibration and refit else 0)
        self.counts_method.setEnabled(not self.native_flux.isChecked() and not running)
        geometry_missing=list(missing)
        if self.native_flux.isChecked() and self.sky_policy.currentText()=='three-line':
            from .native_sky import wavelength_accepted
            if not wavelength_accepted(self.exposure.context.sky_qa):
                missing.append('Flux recovery is blocked by the failed parent wavelength check. Uncheck checked flux recovery to extract review counts. Changing bands does not validate wavelengths.')
        mode=('Checked flux recovery; wavelength and response checks must pass.' if self.native_flux.isChecked()
              else ('Review counts only; PypeIt refits and checks the trace.' if refit and self.exposure.context.calibration
                    else 'Review counts only; saved-trace polynomial boxcar. Trace and wavelength remain unvalidated.'))
        text=('Before extraction:\n'+'\n'.join('• '+m for m in missing) if missing else
              'Ready: trace selected and background bands valid.\nThe background fit is checked when you extract.')
        if running:text='Extraction is running. Cancel it before changing the selection.'
        self.readiness.setText(text+'\n'+mode)
        self.readiness.setProperty('invalid',bool(missing))
        self.readiness.style().unpolish(self.readiness);self.readiness.style().polish(self.readiness)
        for field,invalid in ((self.candidate,not selected),(self.bands,not entered or bands_invalid)):
            field.setProperty('invalid',invalid)
            field.setStyleSheet('border: 1px solid #b84d3f;' if invalid else '')
        self.extract_button.setEnabled(not missing and not running);self.extract_button.setToolTip(text)
        self.search_button.setEnabled(not geometry_missing and not running)

    @house_style
    def screen_layout(self):
        from matplotlib.text import Text
        from .figure_style import plain_tex
        for ax in self.figure.axes:
            ax.tick_params(which='both',labelsize=style.tick_label_size(18))
        for text in self.figure.findobj(Text):
            text.set_fontfamily('serif');text.set_usetex(True)
            if text.get_text():text.set_text(plain_tex(text.get_text()))

    def export_plot(self):
        from .figure_style import save_qc
        path=QtWidgets.QFileDialog.getExistingDirectory(self,'Save PDF and 300-dpi JPG',str(self.packet.parent))
        if not path:return
        try:
            kind='gui-profile-'+datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
            stem=save_qc(self.figure,path,kind,self.review['object'])
            Path(str(stem)+'.json').write_text(json.dumps(getattr(self.figure,'profile_display',{}),indent=2)+'\n')
            self.message.setText('Saved PDF and 300-dpi JPG: '+str(stem))
        except (OSError,ValueError) as exc:self.message.setText(str(exc))

    def configure_selector(self):
        from matplotlib.widgets import SpanSelector
        mode=self.mouse_mode.currentIndex()
        if mode and self.toolbar.mode:
            self.toolbar.pan() if 'pan' in str(self.toolbar.mode) else self.toolbar.zoom()
        for key,button in self.plot_actions.items():button.setChecked(key==mode)
        if hasattr(self,'selector'):self.selector.disconnect_events()
        self.selector=SpanSelector(self.figure.axes[0],self.select_band,'horizontal',
            useblit=False,minspan=1.,props={'alpha':.2,'facecolor':'0.5'})
        self.selector.set_active(mode==2)

    def select_band(self,low,high):
        addition=f'{low:.2f}:{high:.2f}'
        self.bands.setText((self.bands.text()+', ' if self.bands.text().strip() else '')+addition)
        self.message.setText('Background band added; Preview background to validate and fit.')
        patch=self.figure.axes[0].axvspan(low,high,color='xkcd:dodger blue',alpha=.2)
        patch._efospec_background=True
        self.canvas.draw_idle()

    def clear_bands(self):
        self.bands.clear()
        for ax in self.figure.axes:
            for patch in list(ax.patches):
                if getattr(patch,'_efospec_background',False):patch.remove()
        self.message.setText('Bands cleared. Drag one band on each side, then preview the new fit.')
        self.canvas.draw_idle()

    def click_position(self,event):
        if self.mouse_mode.currentIndex()==1 and event.inaxes is self.figure.axes[0] and event.xdata is not None:
            if not self.review['candidates']:
                self.message.setText('No saved trace candidate is available for this exposure.');return
            # The click is an explicit geometry selection, not a brightness/identity inference.
            index=min(range(len(self.review['candidates'])),key=lambda i:abs(
                self.review['candidates'][i]['anchor_raw_x']-event.xdata))
            self.candidate.setCurrentIndex(index+1)
            self.position.setValue(event.xdata)
            ax=self.figure.axes[0]
            for line in list(ax.lines):
                if line.get_color()=='xkcd:red':line.remove()
            for patch in list(ax.patches):
                if patch.get_label()=='Boxcar aperture':patch.remove()
            ax.axvline(event.xdata,color='xkcd:red',ls='--')
            ax.axvspan(event.xdata-self.radius.value(),event.xdata+self.radius.value(),color='xkcd:red',alpha=.14,label='Boxcar aperture')
            self.canvas.draw_idle()
            self.message.setText('Aperture centre updated; preview before extracting.')

    def choose_candidate(self,index):
        self.loaded_object=None
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(index>0)
        if index>0:self.position.setValue(self.review['candidates'][index-1]['anchor_raw_x'])
        self.update_readiness()

    def recipe(self):
        index=self.candidate.currentIndex()-1
        if index<0:raise ValueError('Select a candidate; source identity is never inferred from brightness.')
        saved=self.review['candidates'][index]['recipe']
        value=deepcopy(saved if isinstance(saved,dict) else json.loads(Path(saved).read_text()))
        if self.loaded_object is not None:value['objects'][0]=deepcopy(self.loaded_object)
        bands=[]
        if not self.bands.text().strip():raise ValueError('Enter background bands; the grey example is not a selection.')
        for text in self.bands.text().split(','):
            try:pair=[float(v.strip()) for v in text.strip().split(':')]
            except ValueError:raise ValueError('Each band must be lo:hi, with comma-separated bands.') from None
            if len(pair)!=2:raise ValueError('Each band must be lo:hi, with comma-separated bands.')
            bands.append(pair)
        value['objects'][0].update(spat=self.position.value(),spec=float(self.spectral_anchor.value()),radius=self.radius.value())
        value['sky']=dict(mode='polynomial',include=bands,exclude=[],degree=self.degree.value(),sigma_clip=self.clipping.value())
        return value

    def preview(self):
        try:
            recipe,result=calculate(self.exposure,self.validated_recipe())
            draw_background(self.figure,self.exposure,recipe,result,panel=self.panel.currentIndex());self.screen_layout();self.canvas.draw()
            self.configure_selector()
            self.last_result=result
            self.message.setText(f"Background fit valid for {result['valid'].mean():.1%} of rows. "
                                 'Review residuals and fit bands; this does not confirm the target or validate host subtraction.')
            return recipe,result
        except Exception as exc:
            self.message.setText(str(exc));self.readiness.setText('Cannot extract: '+str(exc));return None

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
            if self.exposure.context.calibration and value['sky']['degree']==0 and (self.native_flux.isChecked() or self.counts_method.currentIndex()==0):
                raise ValueError('This saved constant polynomial is a preview recipe. Native PypeIt extraction requires degree 1–3; choose a degree explicitly before extracting.')
            index=min(range(len(self.review['candidates'])),key=lambda i:abs(self.review['candidates'][i]['anchor_raw_x']-obj['spat']))
            self.candidate.setCurrentIndex(index+1);self.position.setValue(obj['spat'])
            self.loaded_object=deepcopy(obj)
            self.spectral_anchor.setValue(int(obj['spec']));self.radius.setValue(obj['radius'])
            self.degree.setValue(value['sky']['degree']);self.clipping.setValue(value['sky']['sigma_clip'])
            self.bands.setText(', '.join(f'{lo:g}:{hi:g}' for lo,hi in value['sky']['include']))
            self.preview()
        except Exception as exc:self.message.setText(str(exc))

    def extract(self, checked=False, *, search=False):
        if self.worker is not None and self.worker.state()!=QtCore.QProcess.ProcessState.NotRunning:
            self.message.setText('A worker is already running.');return
        self.update_readiness()
        if not (self.search_button if search else self.extract_button).isEnabled():
            self.message.setText(self.readiness.text());return
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
        self.worker_details.clear();self.worker_details.hide()
        self.worker.setStandardOutputFile(str(output)+'.log');self.worker.setStandardErrorFile(str(output)+'-error.log')
        self.worker.finished.connect(lambda code,status:self.worker_finished(code,output,search=search))
        self.worker.errorOccurred.connect(self.worker_error)
        self.worker.start(sys.executable,['-m','efospec','background-search' if search else 'background-extract',str(self.exposure.run),
            '--failed-raw',self.review['raw_name'],'--recipe',str(recipe_file),'--output',str(output),
            ]+([] if search else (['--native-flux','--sky-validation',self.sky_policy.currentText()] if self.native_flux.isChecked() else
                (['--native-counts'] if self.exposure.context.calibration and self.counts_method.currentIndex()==0 else
                 ([] if self.exposure.context.calibration else ['--reference-root',str(self.exposure.context.reference_root)])))))
        self.message.setText(('Comparing background bands: ' if search else 'Extracting to a new revision: ')+str(output))
        self.runningChanged.emit(True)

    def is_running(self):
        return self.worker is not None and self.worker.state()!=QtCore.QProcess.ProcessState.NotRunning

    def update_worker_controls(self,running):
        self.update_readiness();self.sky_policy.setEnabled(not running);self.cancel_button.setEnabled(running)

    def worker_finished(self,code,output, *, search=False):
        if search and code==0:
            try:
                value=validate_recipe(json.loads((output/'selected-recipe.json').read_text()),self.exposure.window,self.exposure.hashes)
                # Reject a result if the user edited the aperture while its worker ran.
                if self.recipe()['objects']!=value['objects']:
                    raise ValueError('Aperture changed while searching; saved result was not loaded')
                self.bands.setText(', '.join(f'{lo:g}:{hi:g}' for lo,hi in value['sky']['include']))
                self.degree.setValue(value['sky']['degree'])
                self.message.setText('Search complete; selected bands loaded. Review and extract a new revision: '+str(output))
            except Exception as exc:self.message.setText(str(exc))
            self.runningChanged.emit(False)
            return
        self.runningChanged.emit(False)
        if code:
            logs=[]
            for path in (Path(str(output)+'-error.log'),Path(str(output)+'.log')):
                if path.exists():logs.append(path.read_text(errors='replace')[-16000:])
            log=re.sub(r'\x1b\[[0-9;]*m','', '\n'.join(logs))
            errors=[line for line in log.splitlines() if line.startswith(('background-extract:','background-search:'))]
            reason=errors[-1] if errors else f'Worker exited with code {code}. See the log below.'
            self.message.setText('Extraction failed: '+reason)
            self.readiness.setText('Last extraction failed: '+reason)
            self.worker_details.setPlainText(log or reason);self.worker_details.show()
        else:self.message.setText('Extraction complete. New revision: '+str(output))

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
