"""Read-only calibration plots from the saved PypeIt solution and response."""
from datetime import datetime
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from PySide6 import QtCore, QtWidgets as Q
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .desktop_canvas import ScientificCanvas
from .desktop_ui import label
from .figure_style import house_style, style, plain_tex, save_qc
from .inventory import sha256

RED='xkcd:red';BLUE='xkcd:dodger blue'


def read_arc(directory):
    from pypeit.wavecalib import WaveCalib
    directory=Path(directory);record=json.loads((directory/'calibration.json').read_text())
    files=record.get('processed_files',record.get('products',{}))
    paths=[directory/name for name in files if Path(name).name.startswith('WaveCalib_')]
    if len(paths)!=1:raise ValueError('A unique saved arc solution is unavailable.')
    path=paths[0]
    if sha256(path)!=files[str(path.relative_to(directory))]:raise ValueError('Saved arc solution checksum changed.')
    wavecal=WaveCalib.from_file(path)
    if len(wavecal.wv_fits)!=1:raise ValueError('Expected one EFOSC2 slit solution.')
    fit=wavecal.wv_fits[0]
    pixels=np.asarray(fit.pixel_fit,float);reference=np.asarray(fit.wave_fit,float)
    detector=np.arange(len(fit.spec),dtype=float)
    return dict(path=path,record=record,detector=detector,spectrum=np.asarray(fit.spec,float),
        pixels=pixels,reference=reference,accepted=np.asarray(fit.pypeitfit.gpm,bool),
        model=fit.pypeitfit.eval(detector/fit.xnorm),
        residual=fit.pypeitfit.eval(pixels/fit.xnorm)-reference)


def read_response(record):
    from pypeit.core.flux_calib import Nlam_to_Flam
    path=Path(record['path'])
    if record.get('sha256') and sha256(path)!=record['sha256']:
        raise ValueError('Saved sensitivity function checksum changed.')
    with fits.open(path) as hdus:
        table=hdus['RESPONSE'].data;header=hdus[0].header.copy()
        wave=np.asarray(table['WAVE'],float).copy();fit=np.asarray(table['ZEROPOINT'],float).copy()
        valid=np.asarray(table['VALID'],bool).copy() & np.isfinite(wave)&np.isfinite(fit)
        measured=np.asarray(table['MEASURED_ZEROPOINT'],float).copy()
        accepted=np.asarray(table['FIT_ACCEPTED'],bool).copy() & np.isfinite(measured)
    if not valid.any():raise ValueError('No supported sensitivity samples.')
    return dict(path=path,header=header,wave=wave,fit=fit,valid=valid,measured=measured,
                accepted=accepted,factor=np.where(valid,Nlam_to_Flam(wave,fit)*1e-17,np.nan))


def _points(ax,x,y,color,**kwargs):
    return ax.plot(x,y,'o',ms=4,mfc='white',mec=color,mew=1,linestyle='none',**kwargs)


def _finish(fig):
    for ax in fig.axes:
        ticks=MaxNLocator(nbins=5).tick_values(*ax.get_xlim());step=abs(ticks[1]-ticks[0])
        style.set_plotparams(ax,xticks=(step,step/4),yticks=None,grid=False,fs=14)
        for axis in (ax.xaxis,ax.yaxis):
            axis.label.set_fontsize(17);axis.get_offset_text().set_fontsize(style.tick_label_size(14))
        ax.title.set_fontsize(16)
        handles,labels=ax.get_legend_handles_labels()
        if handles:style.styled_legend(ax,loc='best',fontsize=12)
    fig.subplots_adjust(left=.10,right=.97,bottom=.11,top=.92,wspace=.34,hspace=.55)


@house_style
def draw_arc(fig,data,sky):
    fig.clear();arc,solution,residual,check=fig.subplots(2,2).ravel()
    x=data['pixels'];refs=data['reference'];good=data['accepted']
    arc.plot(data['detector'],data['spectrum'],color='.35',lw=.8)
    ymax=float(np.nanmax(data['spectrum']))
    for pixel in x:arc.axvline(pixel,color=RED,lw=.6,alpha=.4)
    arc.set(title='Arc lamp and identified lines',xlabel='Arc spectral pixel',ylabel='Electrons')
    arc.set_ylim(top=ymax*1.12)
    solution.plot(data['detector'],data['model'],color=RED,label='Saved solution')
    _points(solution,x[good],refs[good],BLUE,label='Identified lines')
    solution.set(title='Wavelength solution',xlabel='Arc spectral pixel',ylabel=plain_tex('Wavelength (Å, vacuum)'))
    _points(residual,refs[good],data['residual'][good],BLUE,label='Fitted lines')
    if (~good).any():_points(residual,refs[~good],data['residual'][~good],'.5',label='Rejected lines')
    qa=data['record'].get('wavelength',{})
    held=qa.get('held_out_lines_vacuum',[]);diff=qa.get('held_out_residuals_angstrom',[])
    if held and len(held)==len(diff):_points(residual,held,diff,RED,label='Held-out check')
    residual.axhline(0,color='.5',lw=.8)
    residual.set(title='Arc residuals (model minus reference)',xlabel=plain_tex('Wavelength (Å, vacuum)'),ylabel=plain_tex('Residual (Å)'))
    evidence=sky.get('failed_validation') or sky
    ranges=evidence.get('full_sky',{}).get('ranges',[])
    if ranges:
        for r in ranges:
            bounds=r.get('range_vacuum_angstrom');shift=r.get('shift_pixels')
            if bounds is None or shift is None:continue
            center=np.mean(bounds)
            check.errorbar(center,shift,xerr=(bounds[1]-bounds[0])/2,fmt='none',ecolor=BLUE,alpha=.45,lw=1)
            _points(check,[center],[shift],BLUE)
        check.set(xlabel=plain_tex('Sky-check range (Å, vacuum)'),ylabel='Measured shift (pixels)')
    else:
        lines=evidence.get('lines',[])
        points=[(line['rest_air_angstrom'],line['residual_after_shift_angstrom']) for line in lines
                if line.get('rest_air_angstrom') is not None and line.get('residual_after_shift_angstrom') is not None]
        if points:_points(check,*np.asarray(points).T,BLUE)
        else:check.text(.5,.5,'No saved sky-line measurements',ha='center',transform=check.transAxes,fontsize=14)
        check.set(xlabel=plain_tex('Sky wavelength (Å, air)'),ylabel=plain_tex('Residual after shift (Å)'))
    check.axhline(0,color='.5',lw=.8)
    from .native_sky import wavelength_accepted
    check.set_title('Science-sky checks: '+('passed' if wavelength_accepted(sky) else 'failed / unvalidated'))
    _finish(fig)


@house_style
def draw_response(fig,data):
    fig.clear();grid=fig.add_gridspec(2,2)
    zp=fig.add_subplot(grid[:,0]);factor=fig.add_subplot(grid[0,1]);residual=fig.add_subplot(grid[1,1])
    wave=data['wave'];valid=data['valid'];accepted=data['accepted'];measured=data['measured'];fit=data['fit']
    rejected=valid & ~accepted & np.isfinite(measured)
    _points(zp,wave[rejected],measured[rejected],'.65',label='Excluded')
    _points(zp,wave[accepted],measured[accepted],BLUE,label='Used in fit')
    zp.plot(wave,np.where(valid,fit,np.nan),color=RED,lw=1.5,label='Saved fit')
    zp.set(title=plain_tex(str(data['header'].get('STDNAME','Standard'))+' sensitivity fit'),
           xlabel=plain_tex('Wavelength (Å, vacuum)'),ylabel='Sensitivity zeropoint (mag)')
    factor.plot(wave,data['factor'],color=RED,lw=1.5)
    factor.set(title='Sensitivity function',xlabel=plain_tex('Wavelength (Å, vacuum)'),
               ylabel=r'$F_\lambda/N_\lambda$ (erg cm$^{-2}$ electron$^{-1}$)')
    use=accepted&valid
    _points(residual,wave[use],measured[use]-fit[use],BLUE)
    residual.axhline(0,color='.5',lw=.8)
    residual.set(title='Standard-star fit residuals',xlabel=plain_tex('Wavelength (Å, vacuum)'),ylabel='Measured minus fit (mag)')
    for ax in (zp,factor,residual):ax.set_xlim(wave[valid].min(),wave[valid].max())
    _finish(fig)


class CalibrationView(Q.QWidget):
    def __init__(self,kind,object_name,parent=None):
        super().__init__(parent);self.kind=kind;self.object_name=object_name;self.data=None
        layout=Q.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        row=Q.QHBoxLayout();layout.addLayout(row)
        self.caption=label('Saved calibration diagnostics','muted',True);row.addWidget(self.caption,1)
        self.export=Q.QPushButton('Save PDF + JPG');self.export.setEnabled(False)
        self.export.clicked.connect(self.export_plot);row.addWidget(self.export)
        self.figure=Figure(figsize=(16,10),dpi=100);self.canvas=ScientificCanvas(self.figure)
        self.toolbar=NavigationToolbar2QT(self.canvas,self);self.toolbar.setIconSize(QtCore.QSize(16,16))
        self.toolbar.setStyleSheet('QToolButton { padding: 3px; border-radius: 3px; }')
        row.insertWidget(0,self.toolbar);layout.addWidget(self.canvas,1)

    def load(self,source,sky=None):
        try:
            if source is None:raise ValueError('No saved diagnostic for this calibration.')
            if self.kind=='wavelength':
                self.data=read_arc(source);draw_arc(self.figure,self.data,sky or {})
                caption='Saved arc solution; science-sky checks shown separately.'
            else:
                self.data=read_response(source);draw_response(self.figure,self.data)
                caption='Saved standard-star fit; gaps are unsupported. Telluric and slit-loss corrections are not applied.'
            self.caption.setText(caption);self.caption.setToolTip(str(self.data['path']))
            self.export.setEnabled(True);self.canvas.draw_idle();return None
        except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError) as exc:
            self.data=None;self.figure.clear();self.canvas.draw_idle();self.export.setEnabled(False)
            message='Calibration plot unavailable: '+str(exc);self.caption.setText(message)
            return message

    def export_plot(self):
        directory=Q.QFileDialog.getExistingDirectory(self,'Save calibration plots',str(self.data['path'].parent))
        if directory:
            save_qc(self.figure,Path(directory),self.kind+'-calibration-'+datetime.now().strftime('%Y%m%dT%H%M%S%f'),
                    self.object_name,tick_fontsize=14,legend_fontsize=12,title_fontsize=16,label_fontsize=17,preserve_legends=True)
