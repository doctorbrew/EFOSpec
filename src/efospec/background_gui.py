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
from .background_qc import draw_background,draw_candidates,draw_extraction,update_extraction_selection
from .desktop_ui import card,label
from .figure_style import house_style,style


class StatusMessage(QtWidgets.QLabel):
    changed = QtCore.Signal(str)

    def setText(self, text):
        super().setText(text)
        self.changed.emit(text)


class BackgroundEditor(QtWidgets.QWidget):
    """Reusable source-review panel; also usable as a standalone window."""
    runningChanged = QtCore.Signal(bool)

    def __init__(self, packet, reference_root=None, parent=None):
        super().__init__(parent)
        self.setObjectName('workspace')
        self.setStyleSheet('QLabel { font-size: 12px; } QLabel#targetTitle { font-size: 22px; } '
                          'QLabel#sectionTitle { font-size: 13px; } QLabel#notice { padding: 6px; }')
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
        layout=QtWidgets.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.header_layout=QtWidgets.QHBoxLayout();layout.addLayout(self.header_layout)
        self.source_label=label(self.review['object']+'  ·  '+self.review['raw_name'],'sectionTitle')
        self.source_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.header_layout.addWidget(self.source_label,1)
        self.log_entries=[]
        if self.exposure.context.calibration and not self.exposure.context.sky_qa.get('held_out_6363_pass',False):
            self.log_entries.append('Parent sky validation failed. New recovery attempts retain the diagnostics; provisional flux exports use unshifted arc wavelengths.')
        for error in getattr(self.exposure,'manifest',{}).get('errors',[]):
            if Path(error.get('path',error.get('raw',''))).name==self.review['raw_name']:
                self.log_entries.append(json.dumps(error,indent=2))
        self.log_button=QtWidgets.QPushButton('Log ⚠' if self.log_entries else 'Log')
        self.log_button.setToolTip('Open status, warnings and error details')
        self.log_button.clicked.connect(self.show_log);self.header_layout.addWidget(self.log_button)
        split=QtWidgets.QSplitter();layout.addWidget(split,1)
        sidebar=QtWidgets.QWidget();sidebar.setMinimumWidth(280);sidebar.setMaximumWidth(350)
        split.addWidget(sidebar);sidebar_layout=QtWidgets.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0,0,0,0)
        self.step_status=label('','notice',True);sidebar_layout.addWidget(self.step_status)
        self.next_button=QtWidgets.QPushButton();self.next_button.setObjectName('primary')
        self.next_button.clicked.connect(self.next_step);sidebar_layout.addWidget(self.next_button)
        self.next_effect=QtWidgets.QGraphicsOpacityEffect(self.next_button);self.next_button.setGraphicsEffect(self.next_effect)
        self.next_animation=QtCore.QPropertyAnimation(self.next_effect,b'opacity',self)
        self.next_animation.setDuration(1400);self.next_animation.setStartValue(1.)
        self.next_animation.setKeyValueAt(.5,.55);self.next_animation.setEndValue(1.);self.next_animation.setLoopCount(3)
        self.next_key=None;self.final_product=None;self.result_inputs=None;self.next_action=None;self.preparing_revision=False
        scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);sidebar_layout.addWidget(scroll,1)
        self.sidebar_scroll=scroll;self.sidebar_blank=QtWidgets.QWidget()
        sidebar_layout.addWidget(self.sidebar_blank,1);self.sidebar_blank.hide()
        inspector=QtWidgets.QWidget();inspector.setObjectName('inspector');scroll.setWidget(inspector)
        controls=QtWidgets.QVBoxLayout(inspector);controls.setContentsMargins(0,0,10,0);controls.setSpacing(10)
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
        self.panel=QtWidgets.QComboBox();self.panel.addItems(['Data and background fit','Background-subtracted profile','2D aperture and extracted counts']);self.panel.setCurrentIndex(2)
        form.addRow('Plot view',self.panel)
        self.recipe_options=QtWidgets.QGroupBox('Optional recipe import / export');self.recipe_options.setCheckable(True);self.recipe_options.setChecked(False)
        controls.addWidget(self.recipe_options)
        buttons=QtWidgets.QGridLayout(self.recipe_options)
        for column,(title,slot) in enumerate([('Load recipe',self.load_recipe),('Save recipe',self.save_recipe)]):
            button=QtWidgets.QPushButton(title);button.clicked.connect(slot);buttons.addWidget(button,0,column);button.setVisible(False)
            self.recipe_options.toggled.connect(button.setVisible)
        button=QtWidgets.QPushButton('Preview 2D extraction and counts');button.clicked.connect(self.preview);controls.addWidget(button)
        self.readiness=label('','notice',True);self.readiness.setAccessibleName('Extraction requirements')
        controls.addWidget(self.readiness)
        self.extract_button=QtWidgets.QPushButton('Extract counts in new revision');self.extract_button.setObjectName('primary')
        self.extract_button.clicked.connect(self.extract);controls.addWidget(self.extract_button)
        self.native_flux=QtWidgets.QCheckBox('Apply flux calibration');self.native_flux.setVisible(bool(self.exposure.context.calibration));self.native_flux.setChecked(bool(self.exposure.context.calibration));controls.addWidget(self.native_flux)
        self.counts_method=QtWidgets.QComboBox()
        self.counts_method.addItems(['PypeIt refitted counts','Saved-trace boxcar counts'])
        self.counts_method.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.counts_method.setMinimumContentsLength(16)
        self.native_flux.setToolTip('Apply the recorded response and retain any wavelength or trace quality warnings.')
        self.counts_method.setVisible(bool(self.exposure.context.calibration));controls.addWidget(self.counts_method)
        self.counts_method.setToolTip('Saved-trace boxcar is a separate experiment; it does not repair or validate a failed trace or wavelength solution.')
        self.search_button=QtWidgets.QPushButton('Compare nearby background bands');self.search_button.clicked.connect(lambda:self.extract(search=True));controls.addWidget(self.search_button)
        self.sky_policy=QtWidgets.QComboBox();self.sky_policy.addItems(['three-line','two-anchor','full-spectrum']);self.sky_policy.setToolTip('Explicit wavelength acceptance policy; changing this does not repair a calibration.')
        self.sky_policy.setCurrentText(self.exposure.context.sky_qa.get('validation_policy','three-line'))
        self.cancel_button=QtWidgets.QPushButton('Cancel extraction');self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False);controls.addWidget(self.cancel_button);controls.addStretch()
        self.workflow_tabs=QtWidgets.QTabWidget();split.addWidget(self.workflow_tabs);split.setStretchFactor(1,1)
        diagnostics=QtWidgets.QWidget();plots=QtWidgets.QVBoxLayout(diagnostics)
        plots.setContentsMargins(0,0,0,0);plots.setSpacing(0)
        split.setSizes([310,1150])
        self.workflow_tabs.addTab(self.calibration_page(flux=False),'1 Wavelength calibration')
        self.workflow_tabs.addTab(diagnostics,'2 Extraction')
        self.workflow_tabs.addTab(self.calibration_page(flux=True),'3 Flux calibration')
        self.workflow_tabs.setCurrentIndex(1)
        self.workflow_tabs.tabBar().hide()
        self.stage=QtWidgets.QComboBox();self.stage.setAccessibleName('Reduction stage')
        self.stage.addItems(['1 Wavelength calibration','2 Extraction','3 Flux calibration'])
        self.stage.setCurrentIndex(1);sidebar_layout.insertWidget(0,self.stage)
        self.stage.currentIndexChanged.connect(self.workflow_tabs.setCurrentIndex)
        self.workflow_tabs.currentChanged.connect(self.stage.setCurrentIndex)
        from .desktop_spectrum import SpectrumView
        self.final_view=SpectrumView();self.workflow_tabs.addTab(self.final_view,'4 Final spectrum')
        self.stage.addItem('4 Final spectrum')
        self.workflow_tabs.currentChanged.connect(self.update_next_step)
        self.workflow_tabs.currentChanged.connect(self.show_stage_controls)
        # Native screen density is separate from 300-dpi JPG/PDF export. Keep
        # house font point sizes; a 300-dpi screen canvas triples their size.
        self.figure=Figure(figsize=(18,11),dpi=100);self.canvas=FigureCanvasQTAgg(self.figure)
        actions=QtWidgets.QGridLayout();controls.insertLayout(0,actions)
        self.plot_actions={}
        for mode,title in enumerate(('Inspect','Click trace','Drag background')):
            button=QtWidgets.QPushButton(title);button.setCheckable(True)
            button.clicked.connect(lambda checked,m=mode:self.mouse_mode.setCurrentIndex(m))
            actions.addWidget(button,mode//2,mode%2);self.plot_actions[mode]=button
        clear=QtWidgets.QPushButton('Clear bands');clear.clicked.connect(self.clear_bands);actions.addWidget(clear,1,1)
        export=QtWidgets.QPushButton('Save PDF + JPG');export.clicked.connect(self.export_plot);actions.addWidget(export,2,0)
        self.toolbar=NavigationToolbar2QT(self.canvas,self)
        self.toolbar.setStyleSheet('QToolBar { background: #f2f4f8; }')
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toolbar.hide();plots.addWidget(self.canvas,1)
        view=QtWidgets.QPushButton('View');menu=QtWidgets.QMenu(view)
        for title,slot in [('Home',self.toolbar.home),('Back',self.toolbar.back),('Forward',self.toolbar.forward),('Pan',self.toolbar.pan),('Zoom',self.toolbar.zoom)]:
            menu.addAction(title,slot)
        view.setMenu(menu);actions.addWidget(view,2,1)
        self.message=StatusMessage(self);self.message.hide();self.message.changed.connect(self.record_log)
        self.message.setText('Select the trace and two background bands before fitting.')
        self.worker_details=QtWidgets.QPlainTextEdit(self);self.worker_details.setReadOnly(True);self.worker_details.hide()
        self.log_dialog=QtWidgets.QDialog(self);self.log_dialog.setWindowTitle('EFOSpec — '+self.review['object']+' log')
        self.log_dialog.resize(850,550);log_layout=QtWidgets.QVBoxLayout(self.log_dialog)
        self.log_view=QtWidgets.QPlainTextEdit();self.log_view.setReadOnly(True);log_layout.addWidget(self.log_view)
        close=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.log_dialog.close);log_layout.addWidget(close)
        self.runningChanged.connect(self.update_worker_controls)
        self.candidate.currentIndexChanged.connect(self.choose_candidate)
        self.canvas.mpl_connect('button_press_event',self.click_position)
        self.mouse_mode.currentIndexChanged.connect(self.configure_selector)
        self.panel.currentIndexChanged.connect(self.change_view)
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
        self.draw_initial();self.screen_layout();self.configure_selector();self.canvas.draw()
        from .desktop_spectrum import latest_flux_revision
        recovered=latest_flux_revision(self.exposure,self.review['raw_name'])
        if recovered:self.load_completed_spectrum(*recovered)
        else:self.update_calibration_plots()
        self.update_next_step()

    def record_log(self, text):
        self.log_entries.append(text)
        if hasattr(self,'log_dialog') and self.log_dialog.isVisible():self.refresh_log()

    def refresh_log(self):
        details=self.worker_details.toPlainText()
        self.log_view.setPlainText('\n\n'.join(self.log_entries)+ ('\n\nWorker output:\n'+details if details else ''))

    def show_log(self):
        self.refresh_log();self.log_dialog.show();self.log_dialog.raise_();self.log_dialog.activateWindow()

    def change_view(self,*_):
        if self.candidate.currentIndex()>0 and self.bands.text().strip() and self.preview() is not None:return
        self.last_result=None
        if self.panel.currentIndex()==2:self.draw_initial()
        else:draw_candidates(self.figure,self.exposure)
        self.screen_layout();self.configure_selector();self.refresh_selection();self.canvas.draw_idle()

    def draw_initial(self):
        draw_extraction(self.figure,self.exposure)

    def calibration_page(self, *, flux):
        from .native_sky import wavelength_accepted
        page=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(page)
        accepted=wavelength_accepted(self.exposure.context.sky_qa)
        if flux:
            self.flux_status=label('Flux calibration: not applied yet.','notice',True)
            layout.addWidget(self.flux_status)
            try:
                from .daily_reduction import select_response
                chosen=select_response(self.exposure.frame,self.exposure.manifest.get('standards',[]))
                evidence={'standard':chosen['frame']['metadata']['OBJECT'],'response':chosen['fit']['response']}
                summary='Standard star: '+str(evidence['standard'])
            except (ValueError,OSError,KeyError,AttributeError) as exc:
                evidence={'response_unavailable':str(exc)};summary='Standard-star calibration unavailable — see Log.'
            self.standard_label=label(summary,'muted',True);layout.addWidget(self.standard_label)
            self.response_record=evidence.get('response')
            self.flux_evidence=QtWidgets.QPlainTextEdit(page);self.flux_evidence.hide()
            self.flux_evidence.setPlainText(json.dumps(evidence,indent=2))
            self.log_entries.append('Flux calibration files and standard star:\n'+self.flux_evidence.toPlainText())
            actions=QtWidgets.QHBoxLayout();layout.addLayout(actions)
            button=QtWidgets.QPushButton('Extract flux-calibrated spectrum')
            button.clicked.connect(self.start_calibrated_extraction);actions.addWidget(button)
        else:
            self.wave_status=label('Wavelength solution: available — '+('checks passed.' if accepted else 'checks failed; extraction can continue with warnings.'),'notice',True)
            layout.addWidget(self.wave_status)
            layout.addWidget(label('Trace deviations are warnings only. No 0.5-pixel extraction cutoff.','muted',True))
            actions=QtWidgets.QHBoxLayout();layout.addLayout(actions)
            button=QtWidgets.QPushButton('Continue without trace cutoff')
            button.clicked.connect(self.continue_with_warnings);actions.addWidget(button)
            advanced=QtWidgets.QPushButton('Advanced checks');advanced.setCheckable(True)
            layout.addWidget(self.sky_policy);self.sky_policy.hide()
            advanced.toggled.connect(self.sky_policy.setVisible);actions.addWidget(advanced)
            evidence={'saved_wavelength_check':self.exposure.context.sky_qa,
                      'failures':[{'stage':e.get('stage'),'error':e.get('error'),'diagnostics':e.get('diagnostics',{})}
                                  for e in getattr(self.exposure,'manifest',{}).get('errors',[])
                                  if Path(e.get('path',e.get('raw',''))).name==self.review['raw_name']]}
            self.wavelength_evidence=QtWidgets.QPlainTextEdit(page);self.wavelength_evidence.hide()
            self.wavelength_evidence.setPlainText(json.dumps(evidence,indent=2))
            self.log_entries.append('Wavelength calibration measurements:\n'+self.wavelength_evidence.toPlainText())
        details=QtWidgets.QPushButton('Calibration details (Log)')
        details.clicked.connect(self.show_log);actions.addWidget(details);actions.addStretch()
        from .desktop_calibration import CalibrationView
        plot=CalibrationView('flux' if flux else 'wavelength',self.review['object'])
        layout.addWidget(plot,1)
        if flux:self.flux_plot=plot
        else:self.wave_plot=plot
        return page

    def update_calibration_plots(self,record=None):
        from .inventory import sha256
        group=None;sky=self.exposure.context.sky_qa
        response=self.response_record
        try:
            if record is not None:
                sky=record.get('sky_flexure',{})
                response=record.get('sensitivity')
                matches=[]
                for directory in record.get('calibration',{}).get('groups',[]):
                    path=Path(directory);saved=json.loads((path/'calibration.json').read_text())
                    arc=record.get('arc',{}).get('arc')
                    if saved.get('setup')==getattr(self.exposure,'frame',{}).get('setup') and (not arc or arc in saved.get('raw_inputs',{})):
                        matches.append(path)
                if len(matches)==1:group=matches[0]
            else:
                expected=self.exposure.hashes.get('calibration')
                if expected:
                    for path in self.exposure.run.rglob('calibration.json'):
                        if sha256(path)==expected:group=path.parent;break
            problem=self.wave_plot.load(group,sky)
            if problem:self.record_log(problem)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.wave_plot.load(None);self.record_log('Arc plot unavailable: '+str(exc))
        problem=self.flux_plot.load(response)
        if problem:self.record_log(problem)
        elif self.flux_plot.data is not None:
            self.standard_label.setText('Standard star: '+str(self.flux_plot.data['header'].get('STDNAME','unknown')))

    def continue_with_warnings(self):
        self.preparing_revision=True
        self.native_flux.setChecked(True)
        self.message.setText('Trace cutoff disabled: deviations remain warnings. Wavelength checks rerun during extraction.')
        self.workflow_tabs.setCurrentIndex(1)
        self.update_next_step()

    def show_stage_controls(self,index):
        self.sidebar_scroll.setVisible(index==1)
        self.sidebar_blank.setVisible(index!=1)

    def start_calibrated_extraction(self):
        self.preparing_revision=True
        self.native_flux.setChecked(True);self.workflow_tabs.setCurrentIndex(1)
        if self.extract_button.isEnabled():self.extract()
        else:self.update_next_step()

    def next_step(self):
        self.next_animation.stop();self.next_effect.setOpacity(1.)
        if self.next_action=='view':self.workflow_tabs.setCurrentIndex(3)
        elif self.next_action=='aperture':self.continue_with_warnings()
        elif self.next_action=='extract':self.extract()
        else:
            self.workflow_tabs.setCurrentIndex(1)
            if self.candidate.currentIndex()==0:self.mouse_mode.setCurrentIndex(1)
            else:self.mouse_mode.setCurrentIndex(2)

    def update_next_step(self,*_):
        if not hasattr(self,'next_button'):return
        running=self.is_running()
        try:editing=self.candidate.currentIndex()>0 and self.recipe()!=self.result_inputs
        except (ValueError,KeyError,TypeError):editing=self.candidate.currentIndex()>0
        self.next_action=None
        if running:text='Extracting…';status='Extraction and calibration running.'
        elif self.final_product and ((not editing and not self.preparing_revision) or self.workflow_tabs.currentIndex()==3):
            text='View final spectrum';status='Saved spectrum available — see final view for quality flags.'
            self.next_action='view'
        elif self.workflow_tabs.currentIndex()==0:
            text='Next: choose aperture';status='Wavelength solution available; quality flags stay in Log.'
            self.next_action='aperture'
        elif self.candidate.currentIndex()==0:
            text='Next: select trace';status='Choose the source on the detector or profile.'
        elif not self.extract_button.isEnabled():
            text='Next: choose background';status='Choose one background band on each side.'
        else:
            text='Extract flux-calibrated spectrum' if self.native_flux.isChecked() else 'Extract counts'
            status='Ready to extract. Trace deviations will be flagged.'
            self.next_action='extract'
        self.next_button.setText(text);self.next_button.setEnabled(not running)
        self.step_status.setText(status)
        key=(text,running)
        if self.next_key!=key:
            self.next_key=key;self.next_animation.stop();self.next_effect.setOpacity(1.)
            if not running:self.next_animation.start()

    def load_completed_spectrum(self,output,manifest,record):
        product=Path(record['product'])
        if not product.is_absolute():product=Path(output)/product
        try:spectrum=self.final_view.load_product(product)
        except (OSError,ValueError,KeyError) as exc:
            self.message.setText('Cannot display final spectrum: '+str(exc));return False
        self.final_product=product
        self.preparing_revision=False
        try:self.result_inputs=deepcopy(self.recipe())
        except (ValueError,KeyError,TypeError):self.result_inputs=None
        h=spectrum['header']
        self.wave_status.setText('Wavelength solution: complete — '+('checks passed.' if h.get('WAVEVAL',False) else 'quality checks failed; wavelengths are provisional.'))
        self.flux_status.setText('Flux calibration: applied — '+('with wavelength warnings.' if not h.get('WAVEVAL',False) else 'spectrum ready.'))
        self.message.setText('Saved spectrum: '+str(product)+'\n'+self.final_view.status.text())
        self.record_log('Saved spectrum calibration measurements:\n'+json.dumps(dict(
            product=str(product),wavelength=record.get('sky_flexure',{}),
            trace=record.get('processing',{}).get('trace_geometry'),warnings=manifest.get('warnings',[])),indent=2))
        self.update_calibration_plots(record)
        self.update_next_step()
        return True

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
        if self.last_result is not None:
            try:unchanged=self.recipe()==getattr(self,'preview_recipe',None)
            except (ValueError,KeyError,TypeError):unchanged=False
            if not unchanged:
                self.last_result=None
                axes=getattr(self.figure,'extraction_axes',None)
                if self.panel.currentIndex()==2 and axes:
                    ax=axes[2]
                    for artist in list(ax.lines)+list(ax.collections)+list(ax.texts):artist.remove()
                    ax.text(.5,.5,'Selection changed -- preview again',ha='center',transform=ax.transAxes)
                    self.canvas.draw_idle()
        running=self.is_running()
        refit=self.native_flux.isChecked() or self.counts_method.currentIndex()==0
        self.degree.setMinimum(1 if self.exposure.context.calibration and refit else 0)
        self.counts_method.setEnabled(not self.native_flux.isChecked() and not running)
        geometry_missing=list(missing)
        mode=('Calibrated extraction reruns wavelength checks; previous failure does not block a new attempt. Failed sky checks produce a flagged provisional arc-wavelength spectrum. Response checks still apply.' if self.native_flux.isChecked()
              else ('Review counts only; PypeIt refits and checks the trace.' if refit and self.exposure.context.calibration
                    else 'Review counts only; saved-trace polynomial boxcar. Trace and wavelength remain unvalidated.'))
        text=('Before extraction:\n'+'\n'.join('• '+m for m in missing) if missing else
              'Ready: trace selected and background bands valid.\nThe background fit is checked when you extract.')
        if running:text='Extraction is running. Cancel it before changing the selection.'
        self.readiness.setText((missing[0] if missing else 'Ready to extract.') if not running else 'Extraction running…')
        self.readiness.setToolTip(text+'\n'+mode)
        self.readiness.setProperty('invalid',bool(missing))
        self.readiness.style().unpolish(self.readiness);self.readiness.style().polish(self.readiness)
        for field,invalid in ((self.candidate,not selected),(self.bands,not entered or bands_invalid)):
            field.setProperty('invalid',invalid)
            field.setStyleSheet('border: 1px solid #b84d3f;' if invalid else '')
        self.extract_button.setText('Extract calibrated spectrum' if self.native_flux.isChecked() else 'Extract counts in new revision')
        self.extract_button.setEnabled(not missing and not running);self.extract_button.setToolTip(text)
        self.search_button.setEnabled(not geometry_missing and not running)
        self.refresh_selection()
        self.update_next_step()

    @house_style
    def screen_layout(self):
        from matplotlib.text import Text
        from .figure_style import plain_tex
        # Explicit compact GUI typography requested by the user. Values are
        # applied from fixed bases so repeated previews never compound scaling.
        for text in self.figure.findobj(Text):
            text.set_fontfamily('serif');text.set_usetex(True);text.set_fontsize(14)
            if text.get_text():text.set_text(plain_tex(text.get_text()))
        for ax in self.figure.axes:
            ax.tick_params(which='both',labelsize=style.tick_label_size(14))
            ax.xaxis.get_offset_text().set_fontsize(style.tick_label_size(14))
            ax.yaxis.get_offset_text().set_fontsize(style.tick_label_size(14))
            ax.xaxis.label.set_fontsize(17);ax.yaxis.label.set_fontsize(17)
            ax.title.set_fontsize(16)
        if self.figure._suptitle:self.figure._suptitle.set_visible(False)
        if self.panel.currentIndex()==2:
            self.figure.subplots_adjust(left=.08,right=.98,top=.94,bottom=.12,wspace=.30,hspace=.50)

    def export_plot(self):
        from .figure_style import save_qc
        path=QtWidgets.QFileDialog.getExistingDirectory(self,'Save PDF and 300-dpi JPG',str(self.packet.parent))
        if not path:return
        try:
            kind='gui-profile-'+datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
            stem=save_qc(self.figure,path,kind,self.review['object'],tick_fontsize=14,
                         legend_fontsize=14,title_fontsize=16,label_fontsize=17)
            Path(str(stem)+'.json').write_text(json.dumps(getattr(self.figure,'profile_display',{}),indent=2)+'\n')
            self.message.setText('Saved PDF and 300-dpi JPG: '+str(stem))
        except (OSError,ValueError) as exc:self.message.setText(str(exc))

    def spatial_axes(self):
        axes=getattr(self.figure,'extraction_axes',None)
        return list(axes[:2]) if self.panel.currentIndex()==2 and axes else self.figure.axes[:1]

    def refresh_selection(self):
        if not self.figure.axes:return
        if self.panel.currentIndex()!=2:return
        bands=[]
        for text in self.bands.text().split(','):
            try:
                lo,hi=map(float,text.strip().split(':'))
                import math
                if math.isfinite(lo) and math.isfinite(hi) and lo<hi:bands.append((lo,hi))
            except ValueError:continue
        obj=None
        if self.candidate.currentIndex()>0:
            obj=dict(spat=self.position.value(),spec=self.spectral_anchor.value(),radius=self.radius.value())
        update_extraction_selection(self.figure,self.exposure,obj,bands)
        self.canvas.draw_idle()

    def configure_selector(self):
        from matplotlib.widgets import SpanSelector
        mode=self.mouse_mode.currentIndex()
        if mode and self.toolbar.mode:
            self.toolbar.pan() if 'pan' in str(self.toolbar.mode) else self.toolbar.zoom()
        for key,button in self.plot_actions.items():button.setChecked(key==mode)
        for selector in getattr(self,'selectors',[]):selector.disconnect_events()
        self.selectors=[]
        for ax in self.spatial_axes():
            selector=SpanSelector(ax,self.select_band,'horizontal',useblit=False,minspan=1.,
                                  props={'alpha':.2,'facecolor':'0.5'})
            selector.set_active(mode==2);self.selectors.append(selector)
        self.selector=self.selectors[0]

    def select_band(self,low,high):
        if self.is_running():return
        addition=f'{low:.2f}:{high:.2f}'
        self.bands.setText((self.bands.text()+', ' if self.bands.text().strip() else '')+addition)
        self.message.setText('Background band added to both panels; preview to calculate new counts.')
        if self.panel.currentIndex()!=2:
            patch=self.figure.axes[0].axvspan(low,high,color='xkcd:dodger blue',alpha=.2)
            patch._efospec_background=True
        self.canvas.draw_idle()

    def clear_bands(self):
        if self.is_running():return
        self.bands.clear()
        for ax in self.figure.axes:
            for patch in list(ax.patches):
                if getattr(patch,'_efospec_background',False):patch.remove()
        self.message.setText('Bands cleared in both panels. Drag one band on each side.')
        self.canvas.draw_idle()

    def click_position(self,event):
        if self.is_running():return
        if self.mouse_mode.currentIndex()!=1 or event.inaxes not in self.spatial_axes() or event.xdata is None:return
        if not self.review['candidates']:
            self.message.setText('No saved trace candidate is available for this exposure.');return
        if self.panel.currentIndex()==2 and event.inaxes is self.figure.axes[0] and getattr(event,'ydata',None) is not None:
            self.spectral_anchor.setValue(round(event.ydata))
        row=self.spectral_anchor.value()-self.exposure.window.origin[0]
        index=min(range(len(self.review['candidates'])),key=lambda i:abs(
            self.exposure.images['found_traces'][i,row]+self.exposure.window.origin[1]-event.xdata))
        self.candidate.setCurrentIndex(index+1);self.position.setValue(event.xdata)
        self.refresh_selection()
        if self.panel.currentIndex()!=2:
            ax=self.figure.axes[0]
            for line in list(ax.lines):
                if line.get_color()=='xkcd:red':line.remove()
            for patch in list(ax.patches):
                if patch.get_label()=='Boxcar aperture':patch.remove()
            ax.axvline(event.xdata,color='xkcd:red',ls='--')
            ax.axvspan(event.xdata-self.radius.value(),event.xdata+self.radius.value(),color='xkcd:red',alpha=.14,label='Boxcar aperture')
        self.canvas.draw_idle()
        self.message.setText('Trace and aperture updated in both panels; preview to calculate new counts.')

    def choose_candidate(self,index):
        self.loaded_object=None
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(index>0)
        if index>0:
            row=self.spectral_anchor.value()-self.exposure.window.origin[0]
            self.position.setValue(float(self.exposure.images['found_traces'][index-1,row]+self.exposure.window.origin[1]))
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
            if self.panel.currentIndex()==2:draw_extraction(self.figure,self.exposure,recipe,result)
            else:draw_background(self.figure,self.exposure,recipe,result,panel=self.panel.currentIndex())
            self.screen_layout();self.canvas.draw()
            self.configure_selector()
            self.last_result=result
            self.preview_recipe=deepcopy(recipe)
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
        parent=self.exposure.run/'manual-revisions'
        try:parent.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            self.message.setText('Cannot create revision folder: '+str(exc));return
        token=datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
        recipe_file=Path(parent)/('background-'+token+'.json')
        try:
            with recipe_file.open('x') as stream:stream.write(json.dumps(result[0],indent=2)+'\n')
        except OSError as exc:
            self.message.setText('Cannot save extraction recipe: '+str(exc));return
        output=Path(parent)/('background-'+token)
        self.final_product=None
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
        for field in (self.candidate,self.bands,self.degree,self.clipping,self.native_flux,self.recipe_options):field.setEnabled(not running)
        for field in (self.position,self.radius,self.spectral_anchor):field.setEnabled(not running and self.candidate.currentIndex()>0)
        for button in self.plot_actions.values():button.setEnabled(not running)

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
            reason=errors[-1] if errors else f'Worker exited with code {code}. Open Log for details.'
            self.message.setText('Extraction failed: '+reason)
            self.readiness.setText('Last extraction failed: '+reason)
            self.worker_details.setPlainText(log or reason);self.log_button.setText('Log ⚠');self.refresh_log()
        else:
            warnings=[];status='Extraction complete';manifest={}
            try:
                manifest=json.loads((output/'run.json').read_text())
                if manifest.get('status')=='PROVISIONAL':status='Provisional spectrum complete -- wavelength unvalidated'
                warnings.extend(w['message'] for w in manifest.get('warnings',[]))
                for record in manifest.get('results',[])+manifest.get('review_counts',[]):
                    geometry=record.get('trace_geometry') or record.get('processing',{}).get('trace_geometry') or {}
                    warnings.extend(w['message'] for w in geometry.get('warnings',[]))
            except (OSError,ValueError,KeyError):pass
            self.message.setText(status+'. New revision: '+str(output)+('\n'+'\n'.join(warnings) if warnings else ''))
            if warnings:self.log_button.setText('Log ⚠')
            for record in manifest.get('results',[]):
                if Path(record.get('raw',self.review['raw_name'])).name==self.review['raw_name'] and record.get('product'):
                    if self.load_completed_spectrum(output,manifest,record):
                        self.workflow_tabs.setCurrentIndex(3)
                        break
        self.update_next_step()

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
