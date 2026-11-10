#!/usr/bin/env python3
"""Overlay preserved and PypeIt 3 science exports for one observing date."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import plot_style as style


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_run(path, night, version):
    path = Path(path).resolve()
    manifest = path/'run.json'
    run = json.loads(manifest.read_text())
    if run.get('night') != night or run.get('pypeit_version') != version:
        raise ValueError(f'{manifest}: expected {night}, PypeIt {version}')
    if run.get('execution_status') == 'running':
        raise ValueError('wait for reduction completion before comparing exports')
    science = {}
    for row in run['results']:
        if row.get('role') != 'science':
            continue
        key = row['raw_sha256']
        if key in science:
            raise ValueError('multiple primary science exports for one raw exposure')
        science[key] = row
    return run, science, digest(manifest)


def spectrum(row):
    path = Path(row['product'])
    before = digest(path)
    band = 1 if row.get('primary_extraction') == 'boxcar' else 0
    with fits.open(path) as hdus:
        head = hdus[0].header
        if head.get('WAVEMED') != 'air':
            raise ValueError('comparison requires delivered air wavelengths')
        flux = np.asarray(hdus[0].data[band, 0, :], float)*1e16
        valid = np.asarray(hdus['VALID'].data[band], bool) & np.isfinite(flux)
        wave = head['CRVAL1']+(np.arange(flux.size)+1-head.get('CRPIX1', 1))*head['CD1_1']
    valid &= (wave >= 4000.) & (wave <= 8500.)
    if valid.sum() < 20:
        raise ValueError(f'{path}: insufficient supported spectrum')
    return wave, np.where(valid, flux, np.nan), before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('night', type=date.fromisoformat)
    parser.add_argument('--old-run', required=True, type=Path)
    parser.add_argument('--new-run', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    night = args.night.isoformat()
    old, old_rows, old_sha = load_run(args.old_run, night, '1.14.0')
    new, new_rows, new_sha = load_run(args.new_run, night, '3.0.0')
    keys = sorted(set(old_rows) | set(new_rows),
                  key=lambda k: (new_rows.get(k) or old_rows[k])['object'])
    if not keys:
        raise ValueError('no science flux exports in either revision')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output/'plot-script.py').write_bytes(Path(__file__).read_bytes())
    nrows = max(3, int(np.ceil(len(keys)/2)))
    fig, axes = plt.subplots(nrows, 2, figsize=(17, 16*nrows/3), squeeze=False)
    # Previous overview used 0.32. Reduce it by exactly ten percent.
    fig.subplots_adjust(hspace=.4, wspace=.32*.9, bottom=.055, top=.92)
    fig.suptitle('EFOSpec / '+night, fontsize=25)
    colors = {'1.14.0': style.HIROSHIGE_R(.95), '3.0.0': style.HIROSHIGE_R(.05)}
    records = []
    for ax, key in zip(axes.flat, keys):
        preferred = new_rows.get(key) or old_rows[key]
        plotted = []
        for version, rows in [('1.14.0', old_rows), ('3.0.0', new_rows)]:
            if key not in rows:
                continue
            row = rows[key]
            if (row['object'], row['grism']) != (preferred['object'], preferred['grism']):
                raise ValueError('raw exposure metadata disagree across reductions')
            w, f, before = spectrum(row)
            ax.plot(w, f, color=colors[version], lw=1., alpha=.9,
                    label='PypeIt '+version, rasterized=True)
            plotted.append(dict(version=version, product=row['product'], sha256=before,
                                median_snr=row['median_native_snr_4000_8500'],
                                extraction=row.get('primary_extraction', 'optimal')))
        title = (f"{preferred['object']} / {preferred['grism']} / "
                 f"{preferred['exptime_s']:.0f}s "
                 f"(Median SNR {preferred['median_native_snr_4000_8500']:.1f})")
        ax.set(xlim=(4000, 8500), title=title,
               xlabel=r'Observed air wavelength ($\mathrm{\AA}$)',
               ylabel=r'$F_\lambda\;(10^{-16}\,\mathrm{erg\,s^{-1}\,cm^{-2}\,\AA^{-1}})$')
        ax.margins(y=.08)
        style.set_plotparams(ax, xticks=(1000, 250), yticks=None, fs=18)
        if len(plotted) != 2:
            # The legend reports which actual export exists; no failed result
            # is silently drawn as though it were a second reduction.
            style.styled_legend(ax, fontsize=13, loc='upper right')
        records.append(dict(object=preferred['object'], grism=preferred['grism'],
                            raw_sha256=key, title=title,
                            title_snr_version='3.0.0' if key in new_rows else '1.14.0',
                            plotted=plotted))
    for ax in list(axes.flat)[len(keys):]:
        ax.set_visible(False)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=colors[v], lw=2.) for v in ['1.14.0', '3.0.0']],
               ['PypeIt 1.14.0', 'PypeIt 3.0.0'], loc='upper right',
               bbox_to_anchor=(.96, .992), ncol=2, fontsize=16, frameon=False)
    style.savefig_light(fig, output/'science-comparison', dpi_pdf=300, dpi_jpg=300)
    plt.close(fig)
    for row in records:
        for product in row['plotted']:
            if digest(product['product']) != product['sha256']:
                raise ValueError('source spectrum changed while plotting')
    metadata = dict(night=night, old_run=str(args.old_run.resolve()), new_run=str(args.new_run.resolve()),
                    old_manifest_sha256=old_sha, new_manifest_sha256=new_sha,
                    wspace=.288, title_snr_policy='PypeIt 3 when available, otherwise preserved 1.14',
                    old_science_exports=len(old_rows), new_science_exports=len(new_rows),
                    old_errors=old['errors'], new_errors=new['errors'], sources=records,
                    scientific_policy='No extra wavelength shift, interpolation, normalization or smoothing applied for display.')
    (output/'comparison.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(output/'science-comparison.pdf')


if __name__ == '__main__':
    main()
