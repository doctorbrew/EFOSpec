"""Render spectra, spectrum/2-D panels, and binned spatial-profile figures.

Run in the existing base Conda environment, which has the style dependencies:
    /Users/avinash/Softwares/miniconda3/bin/python scripts/preview_spectrum_style.py --target SN2023xxj

Without --target, render all exposures in --run. No validation.json or legacy
spectrum is required. --no-legacy explicitly selects standalone science plots.
"""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter

import matplotlib
import numpy as np
from astropy.io import fits

matplotlib.use("Agg")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from plot_style import savefig_light, set_plotparams, styled_legend
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, to_hex
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from efospec.inventory import sha256
from efospec.qa import compare_legacy, read_flux
from efospec.spatial_profiles import wavelength_binned_profiles
from efospec.run_paths import resolve_result_paths


# White mixing keeps the line opaque while making xkcd:red a pastel hue.
PYPEIT_COLOUR = to_hex(0.6 * np.array(to_rgb('xkcd:red')) + 0.4)
IRAF_COLOUR = 'xkcd:black'
BACKGROUND_COLOUR = 'xkcd:pastel blue'
SKY_LINES = (5577.338, 6300.304, 6363.776)
TICK_LABEL_PT = 22


def mark_sky_lines(ax):
    for wavelength in SKY_LINES:
        if ax.get_xlim()[0] < wavelength < ax.get_xlim()[1]:
            ax.axvline(wavelength, color='0.4', linestyle=':', linewidth=0.9,
                       alpha=0.65, zorder=0.5)


def draw_spectrum(ax, result, wave, bands, comparison=None, legacy_data=None):
    display_label = result['object'].replace('_', r'\_')
    joint = bool(result.get('joint'))
    uncertainty = ax.fill_between(
        wave, (bands[0]-bands[3])/1e-16, (bands[0]+bands[3])/1e-16,
        color=PYPEIT_COLOUR, alpha=0.18, linewidth=0, zorder=1,
        label=(r'Conditional $\pm 1\sigma$' if joint else r'Propagated $\pm 1\sigma$'))
    if comparison:
        old_wave, old_bands = legacy_data
        legacy, = ax.plot(old_wave, old_bands[0]/1e-16, color=IRAF_COLOUR,
                         linewidth=1.1, zorder=2, label='IRAF')
    native, = ax.plot(wave, bands[0]/1e-16, color=PYPEIT_COLOUR,
                      linewidth=1.5, zorder=3, label='Joint fixed profiles' if joint else 'PypeIt')
    good = np.isfinite(wave) & np.isfinite(bands[0]) & np.isfinite(bands[3])
    if not good.any():
        raise ValueError(f"no finite spectrum to plot: {result['product']}")
    lower, upper = (bands[0][good]-bands[3][good])/1e-16, (bands[0][good]+bands[3][good])/1e-16
    low, high = min(0., float(lower.min())), float(upper.max())
    span = max(high-low, 0.01)
    ax.set_xlim(np.floor(wave[good].min()/100)*100, np.ceil(wave[good].max()/100)*100)
    ax.set_ylim(low-0.16*span, high+0.25*span)
    ax.set_xlabel(r'Observed air wavelength [$\AA$]', labelpad=10)
    ax.set_ylabel(r'$F_\lambda$ [$10^{-16}\,\mathrm{erg}\,\mathrm{s}^{-1}'
                  r'\,\mathrm{cm}^{-2}\,\AA^{-1}$]', labelpad=13)
    set_plotparams(ax, xticks=(1000, 200), yticks=None, fs=TICK_LABEL_PT)
    for spine in ax.spines.values():
        spine.set_visible(True)
    ax.set_title(rf"{display_label} (EFOSC2 / {result['grism']} $\cdot$ {result['exptime_s']:.0f}\,s)",
                 loc='center', pad=17)
    handles = [native, uncertainty] + ([legacy] if comparison else [])
    styled_legend(ax, handles=handles, loc='upper right', ncol=len(handles),
                  columnspacing=1.1, borderpad=0.55)
    ax.text(0.5, 0.035,
            rf"Median SNR = {result['median_native_snr_4000_8500']:.1f} per pixel",
            transform=ax.transAxes, color='0.35', fontsize=18, ha='center', va='bottom')
    mark_sky_lines(ax)


def load_trace_data(result):
    basename = Path(result['product']).name[:-7]
    image_path = Path(result['native_spec1d']).parent / (basename+'_images.npz')
    paths = [image_path]
    with np.load(image_path) as saved:
        data = {key: saved[key] for key in ('data', 'sky', 'waveair', 'trace', 'spatial_origin')}
        if 'sky_input_mask' in saved.files:
            data['sky_input_mask'] = saved['sky_input_mask']
            stage = str(saved['sky_mask_stage'])
        else:
            sidecar = image_path.with_name(basename+'_sky_regions.npz')
            source_details_path = sidecar.with_suffix('.json')
            if not sidecar.is_file() or not source_details_path.is_file():
                raise ValueError('sky background selection is missing; recover it with '
                                 'python -m efospec.sky_regions RUN in the PypeIt environment')
            source_details = json.loads(source_details_path.read_text())
            if (sha256(image_path) != source_details['images_sha256']
                    or sha256(sidecar) != source_details['sidecar_sha256']):
                raise ValueError('saved sky selection does not match these extraction images')
            with np.load(sidecar) as selected:
                data['sky_input_mask'] = selected['sky_input_mask']
                stage = str(selected['sky_mask_stage'])
            paths.extend([sidecar, source_details_path])
    if data['sky_input_mask'].shape != data['data'].shape:
        raise ValueError('sky selection and detector image have different geometry')
    # rapid.extract_frame defines straight slit boundaries at 0 and nx-1;
    # PypeIt uses strict inequalities, so neither boundary column has a sky
    # model. Exclude these two off-slit columns from sky-subtracted profiles.
    nx = data['data'].shape[1]
    x = np.arange(nx)
    data['onslit'] = np.broadcast_to((x > 0) & (x < nx-1), data['data'].shape)
    native = Path(result['native_spec1d'])
    with fits.open(native) as hdus:
        target = hdus[result['target']['selected']]
        data['box_radius'] = float(target.header.get('BOX_R_PIX',target.header.get('BOX_RADIUS')))
        if not np.array_equal(target.data['TRACE_SPAT'], data['trace']):
            raise ValueError('saved detector trace differs from the extracted target')
    paths.append(native)
    return data, paths, stage


def rectify_display(data, output_wave):
    """Interpolate the 2-D display column by column on its air-wavelength map.

    The spectrum stays unchanged. The categorical sky mask uses nearest pixels,
    and is never interpolated into a fabricated partially-selected region.
    """
    residual = data['data']-data['sky']
    ny, nx = residual.shape
    image = np.full((len(output_wave), nx), np.nan)
    background = np.zeros(image.shape, dtype=bool)
    for x in range(nx):
        w = data['waveair'][:, x]
        if not np.all(np.diff(w) > 0):
            raise ValueError('nonmonotonic wavelength image')
        image[:, x] = np.interp(output_wave, w, residual[:, x], left=np.nan, right=np.nan)
        upper = np.clip(np.searchsorted(w, output_wave), 1, ny-1)
        nearest = np.where(abs(w[upper]-output_wave) < abs(w[upper-1]-output_wave), upper, upper-1)
        inside = (output_wave >= w[0]) & (output_wave <= w[-1])
        background[:, x] = data['sky_input_mask'][nearest, x] & inside
    trace_wave = np.array([np.interp(t, np.arange(nx), data['waveair'][row])
                           for row, t in enumerate(data['trace'])])
    return image, background, trace_wave


def draw_trace(ax, result, wave, data):
    display_label = result['object'].replace('_', r'\_')
    image, background, trace_wave = rectify_display(data, wave)
    nx = image.shape[1]
    origin = int(data['spatial_origin'])
    step = float(np.median(np.diff(wave)))
    extent = (wave[0]-step/2, wave[-1]+step/2, origin-0.5, origin+nx-0.5)
    finite = np.isfinite(image)
    vmin, vmax = np.percentile(image[finite], [5, 99])
    ax.imshow(image.T, origin='lower', aspect='auto', extent=extent,
              vmin=vmin, vmax=vmax, cmap='gray_r', interpolation='nearest', rasterized=True)
    overlay = np.zeros((nx, len(wave), 4))
    overlay[:, :, :3] = to_rgb(BACKGROUND_COLOUR)
    overlay[:, :, 3] = 0.24 * (background & finite).T
    ax.imshow(overlay, origin='lower', aspect='auto', extent=extent,
              interpolation='nearest', rasterized=True)
    ax.plot(trace_wave, data['trace']+origin, color=PYPEIT_COLOUR, linewidth=1.6, zorder=4)
    ax.set_ylim(origin-0.5, origin+nx-0.5)
    ax.set_ylabel('Spatial pixel', labelpad=13)
    ax.set_xlabel(r'Observed air wavelength [$\AA$]', labelpad=10)
    ax.set_title('Sky-subtracted 2D Spectra', pad=16)
    set_plotparams(ax, xticks=(1000, 200), yticks=(20, 5), fs=TICK_LABEL_PT)
    mark_sky_lines(ax)
    styled_legend(ax, handles=[
        Line2D([], [], color=PYPEIT_COLOUR, linewidth=1.6, label=display_label+' trace'),
        Patch(facecolor=BACKGROUND_COLOUR, alpha=0.5, label='Sky background')],
        loc='upper right', ncol=2, borderpad=0.5)
    return {'sky_mask_fraction': float(data['sky_input_mask'].mean()),
            'sky_mask_stage': 'global_sky_input_before_iterative_rejection',
            'display_resampling': 'linear flux; nearest-neighbour binary sky mask',
            'spatial_coordinates': 'zero-based legacy-trimmed detector pixels',
            'sky_lines_air_angstrom': list(SKY_LINES)}


def draw_spatial_profiles(result, wave, data):
    display_label = result['object'].replace('_', r'\_')
    # Equal wavelength intervals over the same calibrated range as the spectrum.
    profiles = wavelength_binned_profiles(data, np.linspace(wave[0], wave[-1], 4),
                                          data['box_radius'])
    fig, axes = plt.subplots(3, 1, figsize=(13, 12), sharex=True)
    fig.subplots_adjust(left=0.13, right=0.985, bottom=0.09, top=0.86, hspace=0.27)
    fig.suptitle(rf"{display_label} (EFOSC2 / {result['grism']} $\cdot$ {result['exptime_s']:.0f}\,s)",
                 x=0.5575, y=0.97, fontsize=20)
    for ax, profile in zip(axes, profiles):
        x = profile['spatial_pixel']
        y = profile['summed_electrons']/1000.
        # Opacity is the fraction selected within each wavelength bin; this
        # retains curved aperture edges and wavelength-dependent sky selection.
        for fractions, colour, alpha in (
                (profile['background_fraction'], BACKGROUND_COLOUR, 0.32),
                (profile['aperture_fraction'], PYPEIT_COLOUR, 0.22)):
            overlay = np.zeros((1, len(x), 4))
            overlay[:, :, :3] = to_rgb(colour)
            overlay[:, :, 3] = alpha*fractions
            ax.imshow(overlay, extent=(x[0]-0.5, x[-1]+0.5, 0., 1.),
                      transform=ax.get_xaxis_transform(), origin='lower', aspect='auto',
                      interpolation='nearest', rasterized=True, zorder=0)
        ax.plot(x, y, color=PYPEIT_COLOUR, linewidth=1.6, zorder=3)
        ax.axvline(profile['median_trace_pixel'], color='0.3', linestyle='--', linewidth=1.2)
        finite = y[np.isfinite(y)]
        low, high = min(0., float(finite.min())), float(finite.max())
        span = max(high-low, 0.01)
        ax.set_xlim(x[0]-0.5, x[-1]+0.5)
        ax.set_ylim(low-0.08*span, high+0.27*span)
        lo, hi = profile['wavelength_air_angstrom']
        ax.text(0.025, 0.93, rf'{lo:.0f}--{hi:.0f} $\AA$', transform=ax.transAxes,
                fontsize=20, va='top')
        set_plotparams(ax, xticks=(20, 5), yticks=None, fs=TICK_LABEL_PT)
        ax.set_ylabel(r'Summed signal [$10^3\,\mathrm{e}^{-}$]', labelpad=13)
        ax.tick_params(axis='x', labelbottom=True)
    axes[-1].set_xlabel('Spatial pixel', labelpad=10)
    styled_legend(axes[0], handles=[
        Line2D([], [], color='0.3', linestyle='--', linewidth=1.2, label='Trace centre'),
        Patch(facecolor=PYPEIT_COLOUR, alpha=0.22, label='Boxcar aperture'),
        Patch(facecolor=BACKGROUND_COLOUR, alpha=0.32, label='Sky background')],
        loc='lower center', bbox_to_anchor=(0.5, 1.12), ncol=3, borderpad=0.55)
    diagnostics = {
        'binning': 'three equal air-wavelength intervals over the exported spectrum range',
        'signal': 'sum of finite on-slit native data minus sky, in electrons; no resampling or clipping',
        'excluded_spatial_columns': [int(data['spatial_origin']),
                                     int(data['spatial_origin'])+data['data'].shape[1]-1],
        'exclusion_reason': 'two off-slit boundary columns have no fitted sky model',
        'spatial_coordinates': 'zero-based legacy-trimmed detector pixels',
        'box_radius_pixels': data['box_radius'],
        'aperture': 'geometric boxcar aperture from native BOX_RADIUS and TRACE_SPAT; not optimal weights',
        'shading': 'opacity proportional to selection fraction in each wavelength bin',
        'sky_mask_stage': 'global_sky_input_before_iterative_rejection',
        'bins': [{key: np.where(np.isfinite(value), value, None).tolist()
                  if isinstance(value, np.ndarray) else value
                  for key, value in profile.items()} for profile in profiles],
    }
    return fig, diagnostics


def find_comparison(result, run, legacy_root=None):
    """Look for an actual matching spectrum; recompute statistics from its data."""
    if legacy_root is not None:
        return compare_legacy(result, legacy_root)
    validation_path = run / "validation.json"
    if validation_path.is_file():
        saved = json.loads(validation_path.read_text()).get("comparisons", {}).get(result["object"])
        if saved and Path(saved["path"]).is_file():
            return compare_legacy(result, Path(saved["path"]).parent)
    raw_path = result.get("raw")
    return compare_legacy(result, Path(raw_path).parent) if raw_path else None


def render_spectrum(result, run, *, no_legacy=False, legacy_root=None, suffix=""):
    result = resolve_result_paths(result, run)
    comparison = None if no_legacy else find_comparison(result, run, legacy_root)
    inputs = [Path(result['product'])]
    if comparison:
        inputs.append(Path(comparison['path']))
    trace_data, trace_paths, mask_stage = load_trace_data(result)
    inputs.extend(trace_paths)
    before = {str(p): sha256(p) for p in inputs}
    wave, bands, _ = read_flux(inputs[0])
    legacy_data = None
    if comparison:
        old_wave, old_bands, _ = read_flux(inputs[1])
        legacy_data = old_wave, old_bands

    stem = run / 'style-preview' / f"FitSpectrum_{result['object']}_{result['grism']}_air{suffix}"
    fig, ax = plt.subplots(figsize=(13, 6.8))
    fig.subplots_adjust(left=0.115, right=0.985, bottom=0.16, top=0.88)
    draw_spectrum(ax, result, wave, bands, comparison, legacy_data)
    pdf, jpg = savefig_light(fig, stem, dpi_pdf=300, dpi_jpg=300)
    record = {
        'product': str(Path(result['product']).resolve()),
        'purpose': 'individual spectrum, spectrum/2-D, and wavelength-binned spatial-profile figures',
        'style_helper': str(REPO / 'plot_style.py'),
        'style_helper_sha256': sha256(REPO / 'plot_style.py'),
        'python_executable': sys.executable,
        'matplotlib_version': matplotlib.__version__,
        'latex': bool(plt.rcParams['text.usetex']),
        'font_family': list(plt.rcParams['font.family']),
        'axis_label_pt': plt.rcParams['axes.labelsize'],
        'title': ax.get_title(),
        'legend_labels': [text.get_text() for text in ax.get_legend().get_texts()],
        'footer_text': [text.get_text() for text in fig.texts],
        'spectrum_annotations': [text.get_text() for text in ax.texts],
        'tick_label_pt': TICK_LABEL_PT, 'legend_pt': 18,
        'major_ticks': {'direction': 'in', 'length': 9, 'width': 1.6},
        'minor_ticks': {'direction': 'in', 'length': 5, 'width': 1.0},
        'colours': {'Joint fixed profiles' if result.get('joint') else 'PypeIt': PYPEIT_COLOUR,
                    'legacy': to_hex(IRAF_COLOUR)},
        'pastel_definition': '60 percent xkcd:red mixed with 40 percent white',
        'legacy_comparison': comparison,
        'target_association': result['target']['association'],
        'display_limits': {'wavelength_air_angstrom': list(ax.get_xlim()),
                           'flux_in_1e_minus16_cgs': list(ax.get_ylim())},
        'legacy_samples_below_display': 0 if not comparison else int(
            ((old_wave >= ax.get_xlim()[0]) & (old_wave <= ax.get_xlim()[1])
             & (old_bands[0]/1e-16 < ax.get_ylim()[0])).sum()),
        'input_sha256': before,
        'outputs': [str(pdf), str(jpg)],
    }
    plt.close(fig)

    combined, (spectral_ax, trace_ax) = plt.subplots(
        2, 1, figsize=(13, 11.5), sharex=True, gridspec_kw={'height_ratios': [1.25, 1.]})
    combined.subplots_adjust(left=0.115, right=0.985, top=0.93, bottom=0.10, hspace=0.40)
    draw_spectrum(spectral_ax, result, wave, bands, comparison, legacy_data)
    spectral_ax.set_xlabel('')
    spectral_ax.tick_params(axis='x', which='both', bottom=True, labelbottom=True)
    wavelength_limits = spectral_ax.get_xlim()
    diagnostics = draw_trace(trace_ax, result, wave, trace_data)
    trace_ax.set_xlim(wavelength_limits)
    combined_stem = stem.with_name(stem.name.replace('FitSpectrum_', 'FitSpectrumTrace_', 1))
    combined_pdf, combined_jpg = savefig_light(combined, combined_stem, dpi_pdf=300, dpi_jpg=300)
    record['outputs'].extend([str(combined_pdf), str(combined_jpg)])
    record['trace_diagnostics'] = {**diagnostics, 'sky_mask_stage': mask_stage,
                                   'title': trace_ax.get_title(), 'display_percentiles': [5, 99]}
    record['combined_upper_wavelength_ticklabels'] = [t.get_text() for t in spectral_ax.get_xticklabels()]
    plt.close(combined)

    profile_fig, profile_diagnostics = draw_spatial_profiles(result, wave, trace_data)
    profile_stem = stem.with_name(stem.name.replace('FitSpectrum_', 'FitSpatialProfile_', 1))
    profile_pdf, profile_jpg = savefig_light(profile_fig, profile_stem, dpi_pdf=300, dpi_jpg=300)
    record['outputs'].extend([str(profile_pdf), str(profile_jpg)])
    record['spatial_profile_diagnostics'] = profile_diagnostics
    plt.close(profile_fig)

    trace_fig, trace_only_ax = plt.subplots(figsize=(13, 6.8))
    trace_fig.subplots_adjust(left=0.115, right=0.985, bottom=0.16, top=0.85)
    trace_only_ax.set_xlim(record['display_limits']['wavelength_air_angstrom'])
    draw_trace(trace_only_ax, result, wave, trace_data)
    trace_stem = stem.with_name(stem.name.replace('FitSpectrum_', 'FitTrace_', 1))
    trace_pdf, trace_jpg = savefig_light(trace_fig, trace_stem, dpi_pdf=300, dpi_jpg=300)
    record['outputs'].extend([str(trace_pdf), str(trace_jpg)])
    plt.close(trace_fig)
    record['input_files_unchanged'] = all(sha256(p) == before[str(p)] for p in inputs)
    if not record['input_files_unchanged']:
        raise ValueError('input files changed while rendering')
    # A repeated-target stem contains decimal slit widths (e.g. slit1.5).
    # Append the extension: with_suffix would truncate the identifying suffix.
    stem.with_name(stem.name+'.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path,
                        default=REPO / "runs/2024-11-14-pypeit-rapid")
    parser.add_argument("--target", help="Optional target; default: all exposures")
    legacy = parser.add_mutually_exclusive_group()
    legacy.add_argument("--legacy", type=Path, help="Optional directory of comparison spectra")
    legacy.add_argument("--no-legacy", action="store_true", help="Plot only PypeIt and its uncertainty")
    args = parser.parse_args()
    run = args.run.resolve()
    manifest = json.loads((run / "run.json").read_text())
    matches = [r for r in manifest["results"] if not args.target or r["object"] == args.target]
    if not matches:
        parser.error("no matching reduced exposures")
    counts = Counter((r["object"], r["grism"]) for r in manifest['results'])
    records = []
    for result in matches:
        # Distinct same-target exposures must not overwrite one another.
        suffix = ""
        if counts[(result["object"], result["grism"])] > 1:
            suffix = "_" + Path(result["product"]).stem
        records.append(render_spectrum(result, run, no_legacy=args.no_legacy,
                                       legacy_root=args.legacy, suffix=suffix))
    from efospec.report import write_report
    all_records = [json.loads(path.read_text())
                   for path in sorted((run/'style-preview').glob('FitSpectrum_*.json'))]
    (run/'style-preview/all-plots.json').write_text(json.dumps(all_records, indent=2)+'\n')
    write_report(run)
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
