"""Read-only display of exported EFOSpec flux spectra, including provisional ones."""
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from PySide6 import QtCore, QtGui, QtWidgets as Q
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .desktop_canvas import ScientificCanvas
from .desktop_ui import label
from .figure_style import house_style, style, plain_tex, save_qc


def read_flux_spectrum(path):
    with fits.open(path) as hdus:
        h=hdus[0].header.copy()
        if h.get('FLUXCAL','NONE') not in ('NATIVE','ARCHIVE'):
            raise ValueError('This product contains counts, not calibrated flux.')
        data=np.asarray(hdus[0].data,dtype=float)
        if data.ndim!=3 or data.shape[:2]!=(4,1):
            raise ValueError('Unsupported exported spectrum shape.')
        flux=data[0,0].copy();sigma=data[3,0].copy()
        valid=np.asarray(hdus['VALID'].data[0],dtype=bool).reshape(-1).copy()
    wave=h['CRVAL1']+(np.arange(len(flux))+1-h.get('CRPIX1',1))*h['CDELT1']
    valid &= np.isfinite(wave)&np.isfinite(flux)&np.isfinite(sigma)&(sigma>=0)
    if not valid.any():raise ValueError('No supported flux bins in this product.')
    return dict(wave=wave,flux=flux,sigma=sigma,valid=valid,header=h)


def latest_flux_revision(exposure, raw_name):
    """Only recover completed products bound to this parent and raw input."""
    paths=list((exposure.run/'manual-revisions').glob('*/run.json'))
    paths+=list((exposure.run.parent/'QC').rglob('run.json'))
    for path in sorted(paths,key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            manifest=json.loads(path.read_text())
            if (manifest.get('execution_status')!='complete'
                    or Path(manifest.get('parent_run','')).resolve()!=exposure.run.resolve()
                    or manifest.get('parent_sha256')!=exposure.hashes['manifest']):continue
            for record in manifest.get('results',[]):
                if (Path(record.get('raw','')).name!=raw_name
                        or record.get('raw_sha256')!=exposure.hashes['raw']):continue
                product=Path(record['product']).resolve()
                if not product.is_relative_to(path.parent.resolve()):continue
                read_flux_spectrum(product)
                return path.parent,manifest,record
        except (OSError,ValueError,KeyError,TypeError):continue
    return None


class SpectrumView(Q.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.product=None;self.spectrum=None
        layout=Q.QVBoxLayout(self)
        self.status=label('No final spectrum yet. Extract with flux calibration first.','notice',True)
        layout.addWidget(self.status)
        self.file_label=label('','muted');self.file_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.file_label)
        actions=Q.QHBoxLayout();layout.addLayout(actions)
        self.folder=Q.QPushButton('Open output folder');self.folder.setEnabled(False)
        self.folder.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.product.parent))))
        actions.addWidget(self.folder)
        self.export=Q.QPushButton('Save plot PDF + JPG');self.export.setEnabled(False)
        self.export.clicked.connect(self.export_plot);actions.addWidget(self.export);actions.addStretch()
        self.figure=Figure(figsize=(14,8),dpi=100);self.canvas=ScientificCanvas(self.figure)
        self.toolbar=NavigationToolbar2QT(self.canvas,self)
        self.toolbar.setIconSize(QtCore.QSize(16,16))
        self.toolbar.setStyleSheet('QToolButton { padding: 3px; border-radius: 3px; }')
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas,1)

    @house_style
    def load_product(self,path):
        spectrum=read_flux_spectrum(path)
        self.product=Path(path);self.spectrum=spectrum;h=spectrum['header']
        validated=bool(h.get('WAVEVAL',False))
        trace_warning=bool(h.get('TRCWARN',False))
        self.status.setText(('Complete — wavelength checks passed; flux calibration applied.' if validated else
                            'Complete with warnings — flux calibration applied; wavelength unvalidated.')+
                            (f" Trace deviation: {h['TRCDEV']:.3f} px (warning only)." if trace_warning and 'TRCDEV' in h else ''))
        self.file_label.setText(self.product.name+' · '+self.product.parent.parent.name)
        self.file_label.setToolTip(str(self.product))
        self.folder.setEnabled(True);self.export.setEnabled(True)
        self.figure.clear();ax=self.figure.subplots()
        wave=spectrum['wave'];good=spectrum['valid']
        flux=np.where(good,spectrum['flux'],np.nan);sigma=np.where(good,spectrum['sigma'],np.nan)
        ax.plot(wave,flux,color='xkcd:dodger blue',lw=1,label='Extracted flux')
        ax.fill_between(wave,flux-sigma,flux+sigma,color='xkcd:dodger blue',alpha=.18)
        ax.set_xlabel(plain_tex('Wavelength (Å, '+h.get('WAVEMED','unknown')+')'))
        ax.set_ylabel(r'Flux (erg s$^{-1}$ cm$^{-2}$ $\mathrm{\AA}^{-1}$)')
        ax.set_title(plain_tex(str(h.get('OBJECT','Spectrum'))+(' — provisional' if not validated else '')))
        ax.set_xlim(float(wave[good].min()),float(wave[good].max()))
        step=max(float(np.ptp(wave[good]))/6,1.)
        style.set_plotparams(ax,xticks=(step,step/4),yticks=None,grid=False,fs=14)
        ax.xaxis.label.set_fontsize(17);ax.yaxis.label.set_fontsize(17);ax.title.set_fontsize(16)
        ax.yaxis.get_offset_text().set_fontsize(style.tick_label_size(14))
        self.figure.subplots_adjust(left=.13,right=.97,bottom=.15,top=.90)
        self.canvas.draw_idle()
        return spectrum

    def export_plot(self):
        path=Q.QFileDialog.getExistingDirectory(self,'Save spectrum plot',str(self.product.parent))
        if not path:return
        from datetime import datetime
        save_qc(self.figure,Path(path),'final-spectrum-'+datetime.now().strftime('%Y%m%dT%H%M%S%f'),
                self.spectrum['header'].get('OBJECT','Spectrum'),tick_fontsize=14,
                legend_fontsize=14,title_fontsize=16,label_fontsize=17)
