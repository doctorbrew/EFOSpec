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
    fig, ax = plt.subplots(figsize=(16, 5.5), layout='constrained')
    wave = spectrum.OPT_WAVE
    valid = spectrum.OPT_MASK
    counts = np.where(valid, spectrum.OPT_COUNTS/1000., np.nan)
    sigma = np.full_like(counts, np.nan)
    np.divide(.001, np.sqrt(spectrum.OPT_COUNTS_IVAR), out=sigma, where=valid)
    ax.plot(wave, counts, color=COLORS[0], lw=1.5)
    ax.fill_between(wave, counts-sigma, counts+sigma, color=COLORS[0], alpha=.18)
    ax.axhline(0, color='0.5', lw=.8)
    ax.set_xlim(float(wave[valid].min()), float(wave[valid].max()))
    ax.set_xlabel('Vacuum wavelength (Å)')
    ax.set_ylabel(r'Extracted signal [$10^3\,e^{-}$ / pixel]')
    ax.set_title(record['object']+' / Gr13 + GG495 / Arc-calibrated counts')
    save_qc(fig, output, 'counts', record['object']); plt.close(fig)


def plot_filtered_run(run):
    from pypeit.specobjs import SpecObjs
    from .recovery_qc import plot_exposure
    run = Path(run).resolve()
    manifest = json.loads((run/'run.json').read_text())
    if manifest.get('method') != 'native_filtered_standard_extraction':
        raise ValueError('filtered plotting requires a separate standard run')
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
        files = [p for p in output.iterdir() if p.suffix in {'.png', '.pdf', '.jpg', '.json'}
                 and p.name != 'plots.json']
        save_json(output/'plots.json', {'product_sha256': record['product_sha256'],
                  'source_sha256': {name: sha256(Path(__file__).parent/name) for name in
                      ('filtered_plots.py', 'recovery_qc.py', 'profile_background.py', 'figure_style.py')},
                  'plot_style_sha256': sha256(Path(__file__).resolve().parents[2]/'plot_style.py'),
                  'figures_sha256': {p.name: sha256(p) for p in files}})
