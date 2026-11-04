"""House-style figures from saved reduction checks; never rerun the science."""
import json
from pathlib import Path

import numpy as np

from .figure_style import house_style, save_qc, COLORS
from .inventory import sha256


@house_style
def plot_check(path):
    import matplotlib.pyplot as plt
    path=Path(path);record=json.loads(path.read_text())
    curves=path.parent/'curves.npz'
    if sha256(curves)!=record['curves_sha256']:
        raise ValueError('wavelength diagnostic arrays changed')
    with np.load(curves,allow_pickle=False) as saved:
        arrays={k:saved[k] for k in saved.files}
    fig,axes=plt.subplots(2,2,figsize=(22,14))
    for ax,prefix,title in zip(axes[0],('green','red'),('5577 Å anchor','6300 Å anchor / 6363 Å check')):
        if prefix+'_wave' in arrays:
            wave=arrays[prefix+'_wave'];data=arrays[prefix+'_data'];model=arrays[prefix+'_model']
            ax.plot(wave,data,color=COLORS[0],label='Measured sky')
            ax.plot(wave,model,color=COLORS[1],label='Line model')
            ax.plot(wave,data-model,color=COLORS[2],label='Residual')
        else:
            low,high=(5450.,5700.) if prefix=='green' else (6200.,6500.)
            keep=(arrays['waveair']>low)&(arrays['waveair']<high)
            if keep.any():ax.plot(arrays['waveair'][keep],arrays['sky'][keep],color=COLORS[0],label='Measured sky')
            ax.text(.5,.85,'No accepted line model',transform=ax.transAxes,ha='center')
        ax.set(title=title,xlabel='Air wavelength (Å)',ylabel=record['metadata'].get('data_unit','Counts'))
    ax=axes[1,0]
    for m in record['line_check']['lines']:
        valid=m['fit_valid'];err=m.get('centroid_error_angstrom')
        ax.errorbar(m['rest_air_angstrom'],m['offset_angstrom'],yerr=err if valid else None,
            fmt='o' if valid else 'x',color=COLORS[0] if valid else COLORS[2],capsize=4)
        ax.annotate(f'S/N {m["peak_snr"]:.1f}'+(' / invalid fit' if not valid else ''),
            (m['rest_air_angstrom'],m['offset_angstrom']),xytext=(5,8),textcoords='offset points',fontsize=13)
    shift=record['applied_shift_angstrom']
    if shift is not None:ax.axhline(shift,color=COLORS[1],label='Applied line shift')
    lines=record['line_check']['lines']
    if lines:
        ax.set_xlim(min(m['rest_air_angstrom'] for m in lines)-80,
                    max(m['rest_air_angstrom'] for m in lines)+180)
        ax.margins(y=.2)
    ax.set(title='Line check: '+record['status'],xlabel='Reference air wavelength (Å)',ylabel='Correction (Å)')
    ax=axes[1,1];comparison=record['correlation']
    if comparison['status']=='measured':
        ax.plot(arrays['correlation_lags'],arrays['correlation_values'],color=COLORS[0])
        ax.axvline(comparison['shift_pixels'],color=COLORS[1],label='PypeIt correlation peak')
        ax.set_title(f'Comparison only: {comparison["shift_angstrom"]:+.2f} Å; not applied')
    else:
        ax.text(.5,.5,'PypeIt comparison unavailable',transform=ax.transAxes,ha='center')
        ax.set_title('See check.json for the recorded reason')
    ax.set(xlabel='Shift (pixels on uniform vacuum grid)',ylabel='Correlation')
    fig.suptitle(record['metadata'].get('object','Exposure')+' / '+Path(record['metadata']['raw']).stem,fontsize=22)
    fig.subplots_adjust(hspace=.65,wspace=.35,bottom=.13,top=.9)
    stem=save_qc(fig,path.parent,'wavelength',record['metadata'].get('object','Exposure'))
    plt.close(fig)
    return str(stem)


def render_checks(run):
    return [plot_check(path) for path in sorted((Path(run)/'checks').glob('*/check.json'))]


if __name__=='__main__':
    import sys
    render_checks(sys.argv[1])
