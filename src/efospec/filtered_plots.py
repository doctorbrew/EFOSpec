"""Render separate standard extractions using the existing QC figures."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .figure_style import house_style, save_qc, COLORS
from .inventory import sha256
from .native_calibration import save_json


@house_style
def plot_counts(spectrum, record, output):
    import matplotlib.pyplot as plt
    from astropy import units as u
    from pypeit.core.wave import vactoair
    from .trace_plot import PYPEIT_COLOUR, mark_sky_lines
    fig, ax = plt.subplots(figsize=(13, 6.8))
    fig.subplots_adjust(left=.115,right=.985,bottom=.16,top=.88)
    wave = vactoair(spectrum.OPT_WAVE*u.AA).value
    valid = spectrum.OPT_MASK
    counts = np.where(valid, spectrum.OPT_COUNTS/1000., np.nan)
    sigma = np.full_like(counts, np.nan)
    np.divide(.001, np.sqrt(spectrum.OPT_COUNTS_IVAR), out=sigma, where=valid)
    ax.plot(wave, counts, color=PYPEIT_COLOUR, lw=1.5,label='PypeIt review counts')
    ax.fill_between(wave, counts-sigma, counts+sigma, color=PYPEIT_COLOUR, alpha=.18,label=r'Propagated $\pm 1\sigma$')
    ax.axhline(0, color='0.5', lw=.8)
    ax.set_xlim(np.floor(wave[valid].min()/100)*100,np.ceil(wave[valid].max()/100)*100)
    ax.set_xlabel(r'Observed air wavelength [$\AA$]')
    ax.set_ylabel(r'Extracted signal [$10^3\,e^{-}$ / pixel]')
    setup=record['setup']
    ax.set_title(record['object']+' / '+setup['grism']+' + '+setup['filter']+' / Arc-calibrated counts')
    from .figure_style import style
    style.set_plotparams(ax,xticks=(1000,200),yticks=None,fs=18)
    style.styled_legend(ax,loc='upper right',ncol=2)
    mark_sky_lines(ax)
    save_qc(fig, output, 'counts', record['object'],preserve_legends=True); plt.close(fig)


@house_style
def plot_extracted_counts(spectrum, record, arrays, output):
    """Use delivered trace and aperture with the same nightly plot renderers."""
    import matplotlib.pyplot as plt
    from astropy import units as u
    from pypeit.core.wave import vactoair
    from astropy.io import fits
    from .trace_plot import draw_trace, rectify_display
    from .profile_plot import draw_spatial_profiles, save_review_profile
    if not np.array_equal(spectrum.TRACE_SPAT,arrays['trace']):
        raise ValueError('counts trace differs from saved detector trace')
    with fits.open(record['native_spec1d']) as hdus:
        header=hdus[1].header
        radius=float(header.get('BOX_R_PIX',header.get('BOX_RADIUS')))
    if not np.isfinite(radius) or radius<=0:raise ValueError('invalid saved counts aperture')
    nx=arrays['data'].shape[1]
    data=dict(arrays,spatial_origin=int(arrays['raw_x_origin'])-99,box_radius=radius,
        onslit=np.broadcast_to((np.arange(nx)>0)&(np.arange(nx)<nx-1),arrays['data'].shape),
        aperture_label='Adopted Aperture',selected_label='C1')
    data['candidate_traces']=[dict(label='C1',trace=data['trace']+data['spatial_origin'])]
    result=dict(record,grism=record['setup']['grism'],exptime_s=fits.getheader(record['raw'])['EXPTIME'])
    wave=vactoair(spectrum.OPT_WAVE[spectrum.OPT_MASK]*u.AA).value
    fig,axes=plt.subplots(2,1,figsize=(13,12.4),sharex=True)
    fig.subplots_adjust(left=.115,right=.985,bottom=.09,top=.93,hspace=.33)
    rectified=rectify_display(data,wave);stages={}
    for ax,stage in zip(axes,('before','after')):
        ax.set_xlim(np.floor(wave.min()/100)*100,np.ceil(wave.max()/100)*100)
        stages[stage]=draw_trace(ax,result,wave,data,stage=stage,rectified=rectified,legend=stage=='before')
        ax.tick_params(axis='x',which='both',bottom=True,labelbottom=True)
    axes[0].set_xlabel('')
    save_qc(fig,output,'traces',record['object'],preserve_legends=True);plt.close(fig)
    fig,profile=draw_spatial_profiles(result,wave,data)
    save_review_profile(fig,output,record['object']);plt.close(fig)
    save_json(output/'profile-display.json',profile)
    save_json(output/'trace-display.json',stages)


def plot_filtered_run(run):
    from pypeit.specobjs import SpecObjs
    from .recovery_qc import plot_exposure
    run = Path(run).resolve()
    manifest = json.loads((run/'run.json').read_text())
    if manifest.get('method') not in {'native_filtered_standard_extraction','native_red_counts_diagnostic',
                                    'native_optical_counts_diagnostic','native_nightly_counts_diagnostic'}:
        raise ValueError('counts plotting requires a separate native counts run')
    for record in manifest['results']:
        for name, digest in record['product_sha256'].items():
            path = Path(name)
            path.resolve().relative_to(run)
            if sha256(path) != digest:
                raise ValueError('filtered product changed before plotting')
        if sha256(Path(record['raw'])) != record['raw_sha256']:
            raise ValueError('raw standard changed before plotting')
        output = Path(record['product']).parent.parent/'plots'
        output.mkdir(exist_ok=True)
        spectrum = SpecObjs.from_fitsfile(record['native_spec1d'])[0]
        plot_counts(spectrum, record, output)
        with np.load(record['images']) as saved:
            arrays = {key: saved[key] for key in saved.files}
        exposure = SimpleNamespace(frame={'path': record['raw']}, images=arrays,
            window=SimpleNamespace(origin=(record['raw_spectral_origin'], record['raw_spatial_origin']),
                                   shape=arrays['data'].shape),
            candidates=[{'name': str(name)} for name in arrays['found_names']],
            result={'object': record['object'], 'processing': {
                'sky_policy': 'bounded_two_sided_pypeit', 'background_fit': record['background']}})
        plot_exposure(exposure, output)
        plot_extracted_counts(spectrum,record,arrays,output)
        files = [p for p in output.iterdir() if p.suffix in {'.png', '.pdf', '.jpg', '.json'}
                 and p.name != 'plots.json']
        save_json(output/'plots.json', {'product_sha256': record['product_sha256'],
                  'source_sha256': {name: sha256(Path(__file__).parent/name) for name in
                      ('filtered_plots.py', 'trace_plot.py', 'recovery_qc.py', 'diagnostic_plots.py', 'profile_background.py', 'profile_plot.py', 'figure_style.py')},
                  'plot_style_sha256': sha256(Path(__file__).resolve().parents[2]/'plot_style.py'),
                  'figures_sha256': {p.name: sha256(p) for p in files}})


if __name__=='__main__':
    import sys
    from .epoch_report import build_filtered_page
    plot_filtered_run(sys.argv[1])
    build_filtered_page(sys.argv[1])
