"""Render spectra, spectrum/2-D panels, and binned spatial-profile figures.

Run in the existing base Conda environment, which has the style dependencies:
    /Users/avinash/Softwares/miniconda3/bin/python scripts/preview_spectrum_style.py --target SN2023xxj

Without --target, render all exposures in --run. Main report plots are PypeIt-only;
--legacy explicitly requests overlays. No validation.json or legacy spectrum is required.
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
from efospec.profile_limits import _profile_limit_samples, _profile_limits
from efospec.run_paths import resolve_result_paths
from efospec.image_display import image_normalization


# White mixing keeps the line opaque while making xkcd:red a pastel hue.
PYPEIT_COLOUR = to_hex(0.6 * np.array(to_rgb('xkcd:red')) + 0.4)
IRAF_COLOUR = 'xkcd:black'
BACKGROUND_COLOUR = 'xkcd:pastel blue'
SKY_LINES = (5577.338, 6300.304, 6363.776)
TICK_LABEL_PT = 18


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
                      linewidth=1.5, zorder=3, label='Joint fixed profiles' if joint else
                      'PypeIt boxcar' if result.get('primary_extraction')=='boxcar' else 'PypeIt')
    good = np.isfinite(wave) & np.isfinite(bands[0]) & np.isfinite(bands[3])
    if not good.any():
        raise ValueError(f"no finite spectrum to plot: {result['product']}")
    lower, upper = (bands[0][good]-bands[3][good])/1e-16, (bands[0][good]+bands[3][good])/1e-16
    low, high = min(0., float(lower.min())), float(upper.max())
    ax.set_xlim(np.floor(wave[good].min()/100)*100, np.ceil(wave[good].max()/100)*100)
    if comparison:
        # Include every finite legacy sample visible on this wavelength axis.
        # Native uncertainty remains included; neither spectrum is rescaled.
        visible = (np.isfinite(old_wave) & np.isfinite(old_bands[0])
                   & (old_wave >= ax.get_xlim()[0]) & (old_wave <= ax.get_xlim()[1]))
        if visible.any():
            low = min(low, float(np.min(old_bands[0][visible]/1e-16)))
            high = max(high, float(np.max(old_bands[0][visible]/1e-16)))
    span = max(high-low, 0.01)
    ax.set_ylim(low-0.16*span, high+0.25*span)
    ax.set_xlabel(r'Observed air wavelength [$\AA$]', labelpad=10)
    ax.set_ylabel(r'$F_\lambda$ [$10^{-16}\,\mathrm{erg}\,\mathrm{s}^{-1}'
                  r'\,\mathrm{cm}^{-2}\,\AA^{-1}$]', labelpad=13)
    set_plotparams(ax, xticks=(1000, 200), yticks=None, fs=TICK_LABEL_PT)
    for spine in ax.spines.values():
        spine.set_visible(True)
    suffix=' / Provisional wavelengths' if result.get('status')=='PROVISIONAL' else ''
    ax.set_title(rf"{display_label} (EFOSC2 / {result['grism']} $\cdot$ {result['exptime_s']:.0f}\,s)"+suffix,
                 loc='center', pad=17, fontsize=28)
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
        for key in ('sky_accepted_mask', 'sky_valid_rows', 'sky_spatial_degree'):
            if key in saved.files:
                data[key] = saved[key]
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
    observed = np.asarray(data['data'], float)
    ny, nx = residual.shape
    image = np.full((len(output_wave), nx), np.nan)
    raw = np.full((len(output_wave), nx), np.nan)
    background = np.zeros(image.shape, dtype=bool)
    for x in range(nx):
        w = data['waveair'][:, x]
        if not np.all(np.diff(w) > 0):
            raise ValueError('nonmonotonic wavelength image')
        image[:, x] = np.interp(output_wave, w, residual[:, x], left=np.nan, right=np.nan)
        raw[:, x] = np.interp(output_wave, w, observed[:, x], left=np.nan, right=np.nan)
        upper = np.clip(np.searchsorted(w, output_wave), 1, ny-1)
        nearest = np.where(abs(w[upper]-output_wave) < abs(w[upper-1]-output_wave), upper, upper-1)
        inside = (output_wave >= w[0]) & (output_wave <= w[-1])
        background[:, x] = data['sky_input_mask'][nearest, x] & inside
    trace_wave = np.array([np.interp(t, np.arange(nx), data['waveair'][row])
                           for row, t in enumerate(data['trace'])])
    return image, raw, background, trace_wave


# A sky-subtracted trace sits hundreds of background sigma above zero. Clamping
# the scale at five sigma saturates it, so only the noise texture stays visible.
BRIGHT_PERCENTILE = 99.5

TRACE_STAGES = {
    'before': ('Before sky subtraction: data and sky', False),
    'after': ('After sky subtraction: data minus fitted sky', True),
}


def draw_trace(ax, result, wave, data, *, stage='after', rectified=None, legend=True):
    """Draw one sky-subtraction stage of the rectified 2-D detector image."""
    if stage not in TRACE_STAGES:
        raise ValueError('2-D display stage must be "before" or "after" sky subtraction')
    display_label = result['object'].replace('_', r'\_')
    image, raw, background, trace_wave = rectified or rectify_display(data, wave)
    title, subtracted = TRACE_STAGES[stage]
    shown = image if subtracted else raw
    nx = shown.shape[1]
    origin = int(data['spatial_origin'])
    step = float(np.median(np.diff(wave)))
    extent = (wave[0]-step/2, wave[-1]+step/2, origin-0.5, origin+nx-0.5)
    finite = np.isfinite(shown)
    # Both stages take their noise scale from the sky-sampling bands, and their
    # upper limit from the data, so the trace keeps structure instead of
    # saturating. The before-subtraction panel keeps its own sky pedestal.
    norm, scaling = image_normalization(shown, residual=subtracted,
        samples=shown[background & finite], bright_percentile=BRIGHT_PERCENTILE)
    ax.imshow(shown.T, origin='lower', aspect='auto', extent=extent,
              norm=norm, cmap='gray_r', interpolation='nearest', rasterized=True)
    overlay = np.zeros((nx, len(wave), 4))
    overlay[:, :, :3] = to_rgb(BACKGROUND_COLOUR)
    overlay[:, :, 3] = 0.24 * (background & finite).T
    ax.imshow(overlay, origin='lower', aspect='auto', extent=extent,
              interpolation='nearest', rasterized=True)
    ax.plot(trace_wave, data['trace']+origin, color=PYPEIT_COLOUR, linewidth=1.6, zorder=4)
    ax.set_ylim(origin-0.5, origin+nx-0.5)
    ax.set_ylabel('Spatial pixel', labelpad=13)
    ax.set_xlabel(r'Observed air wavelength [$\AA$]', labelpad=10)
    ax.set_title(title, pad=16)
    set_plotparams(ax, xticks=(1000, 200), yticks=(20, 5), fs=TICK_LABEL_PT)
    mark_sky_lines(ax)
    if legend:
        styled_legend(ax, handles=[
            Line2D([], [], color=PYPEIT_COLOUR, linewidth=1.6, label=display_label+' trace'),
            Patch(facecolor=BACKGROUND_COLOUR, alpha=0.5, label='Sky background')],
            loc='upper right', ncol=2, borderpad=0.5)
    return {'sky_mask_fraction': float(data['sky_input_mask'].mean()),
            'sky_mask_stage': 'global_sky_input_before_iterative_rejection',
            'display_resampling': 'linear flux; nearest-neighbour binary sky mask',
            'spatial_coordinates': 'zero-based legacy-trimmed detector pixels',
            'sky_subtracted': subtracted, 'stage': stage,
            'image_display': scaling,
            'sky_lines_air_angstrom': list(SKY_LINES)}


def draw_spatial_profiles(result, wave, data, *, display=None):
    display = display or {}
    display_label = result['object'].replace('_', r'\_')
    # Equal wavelength intervals over the same calibrated range as the spectrum.
    profiles = wavelength_binned_profiles(data, np.linspace(wave[0], wave[-1], 4),
                                          data['box_radius'])
    fig, panels = plt.subplots(3, 2, figsize=(22, 13), sharex=True)
    model_axes, axes = panels[:, 0], panels[:, 1]
    # Removing the explanatory paragraph frees the band under the legend.
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.08, top=0.85,
                        hspace=0.27, wspace=0.25)
    fig.suptitle(rf"{display_label} (EFOSC2 / {result['grism']} $\cdot$ {result['exptime_s']:.0f}\,s)",
                 x=0.53, y=0.985, fontsize=20)
    degree = data.get('sky_spatial_degree', result.get('processing', {}).get('background_fit', {}).get('spatial_degree'))
    model_label = 'Saved PypeIt sky' + (f' (spatial degree {int(degree)})' if degree is not None else '')
    model_axes[0].set_title('Before subtraction: data and fitted sky', pad=16)
    axes[0].set_title('After subtraction: data minus fitted sky', pad=16)
    # Display provenance stays in the saved diagnostics and the report caption;
    # the figure itself carries no explanatory paragraphs.
    for ax, model_ax, profile in zip(axes, model_axes, profiles):
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
            for panel in (ax, model_ax):
                panel.imshow(overlay, extent=(x[0]-0.5, x[-1]+0.5, 0., 1.),
                      transform=panel.get_xaxis_transform(), origin='lower', aspect='auto',
                      interpolation='nearest', rasterized=True, zorder=0)
        ax.plot(x, y, color=PYPEIT_COLOUR, linewidth=1.6, zorder=3)
        ax.axvline(profile['median_trace_pixel'], color='0.3', linestyle='--', linewidth=1.2)
        raw = profile['summed_data_electrons']/1000.
        fitted = profile['summed_sky_electrons']/1000.
        supported = profile['sky_model_supported']
        model_ax.plot(x, raw, color='0.3', linewidth=1.3, zorder=3)
        model_ax.plot(x, np.where(supported, fitted, np.nan), color='xkcd:dark blue',
                      linestyle='--', linewidth=2., zorder=4)
        model_ax.axvline(profile['median_trace_pixel'], color='0.3', linestyle='--', linewidth=1.2)
        protected = profile['aperture_fraction'] > 0
        annotations = []
        for candidate in display.get('profile_candidates',[]):
            lo,hi = candidate['search_interval']
            region = (x >= lo) & (x < hi)
            protected |= region
            usable = np.flatnonzero(region & np.isfinite(y))
            if not len(usable):
                raise ValueError('requested profile candidate has no finite samples')
            peak = usable[np.argmax(y[usable])]
            position = float(x[peak])
            ax.axvline(position,color='xkcd:dodger blue',linestyle=':',linewidth=1.2)
            ax.text(position+1,.035,candidate['label'],transform=ax.get_xaxis_transform(),
                    color='xkcd:dodger blue',fontsize=16,va='bottom')
            annotations.append(dict(label=candidate['label'],spatial_pixel=position,
                method='maximum within user-identified profile interval; not a fitted trace',
                search_interval=list(candidate['search_interval']),identity_confirmed=False))
        limit_values, excluded = _profile_limit_samples(y,protected,spatial_pixel=x,
            exclude_ranges=display.get('ylim_exclude_intervals',[]))
        _, automatic_excluded = _profile_limit_samples(y,protected,spatial_pixel=x)
        background_columns=np.flatnonzero(profile['background_fraction']>0)
        background_span=None
        outside=np.zeros(len(x),bool)
        if display.get('limits_within_background_and_candidates'):
            if len(background_columns)<2:
                raise ValueError('profile limits need two-sided background coverage')
            background_span=[float(x[background_columns[0]]),float(x[background_columns[-1]])]
            outside=(x<background_span[0])|(x>background_span[1])
            # Keep the neighbour context, but do not let distant polynomial
            # extrapolation dominate a local source/background diagnostic.
            unsupported=outside & ~protected
            limit_values[unsupported]=np.nan
            excluded |= unsupported & np.isfinite(y)
            for candidate in annotations:
                candidate['background_extrapolated']=not background_span[0]<=candidate['spatial_pixel']<=background_span[1]
        limits = _profile_limits([limit_values],background_subtracted=True)
        ax.set_xlim(x[0]-0.5, x[-1]+0.5)
        if limits is not None:ax.set_ylim(*limits)
        raw_limits = _profile_limits([np.where(np.isfinite(limit_values), raw, np.nan),
                                     np.where(supported, fitted, np.nan)])
        if raw_limits is not None:model_ax.set_ylim(*raw_limits)
        profile.update(ylim=list(ax.get_ylim()),ylim_excluded_spatial_pixels=x[excluded].tolist(),
                       data_model_ylim=list(model_ax.get_ylim()),
                       automatic_spike_excluded_spatial_pixels=x[automatic_excluded].tolist(),
                       candidate_annotations=annotations,background_interpolation_span=background_span)
        lo, hi = profile['wavelength_air_angstrom']
        ax.text(0.025, 0.93, rf'{lo:.0f}--{hi:.0f} $\AA$', transform=ax.transAxes,
                fontsize=20, va='top')
        set_plotparams(ax, xticks=(20, 5), yticks=None, fs=TICK_LABEL_PT)
        ax.set_ylabel(r'Summed signal [$10^3\,\mathrm{e}^{-}$]', labelpad=13)
        ax.tick_params(axis='x', labelbottom=True)
        model_ax.text(.025, .93, rf'{lo:.0f}--{hi:.0f} $\AA$', transform=model_ax.transAxes,
                      fontsize=20, va='top')
        model_ax.set_xlim(x[0]-.5, x[-1]+.5)
        set_plotparams(model_ax, xticks=(20, 5), yticks=None, fs=TICK_LABEL_PT)
        model_ax.set_ylabel(r'Summed signal [$10^3\,\mathrm{e}^{-}$]', labelpad=13)
        model_ax.tick_params(axis='x', labelbottom=True)
    axes[-1].set_xlabel(r'Spatial pixel (raw $-99$)', labelpad=10)
    model_axes[-1].set_xlabel(r'Spatial pixel (raw $-99$)', labelpad=10)
    styled_legend(axes[0], handles=[
        Line2D([], [], color='0.3', linewidth=1.3, label='Data (sky included)'),
        Line2D([], [], color='xkcd:dark blue', linestyle='--', linewidth=2., label=model_label),
        Line2D([], [], color=PYPEIT_COLOUR, linewidth=1.6, label='Data minus sky'),
        Line2D([], [], color='0.3', linestyle='--', linewidth=1.2, label='Trace centre'),
        Patch(facecolor=PYPEIT_COLOUR, alpha=0.22, label='Boxcar aperture'),
        Patch(facecolor=BACKGROUND_COLOUR, alpha=0.32, label='Sky fit bands')],
        loc='center', bbox_to_anchor=(.53,.925), bbox_transform=fig.transFigure,
        ncol=3, borderpad=0.55)
    diagnostics = {
        'display_settings':display,
        'ylim_rule':'QC limits: exclude isolated negative outliers and positive peaks with >20 MAD-sigma prominence, half-prominence width <=2 pixels and <=3-column >10-sigma core outside protected sources; explicit display exclusions also apply; include zero and pad outward',
        'display_only':True,'all_profile_samples_plotted':True,
        'binning': 'three equal air-wavelength intervals over the exported spectrum range',
        'signal': 'sum of finite on-slit native data minus sky, in electrons; no resampling or clipping',
        'sky_model': {'source':'saved extraction sky image; no new fit',
                      'spatial_degree':int(degree) if degree is not None else None,
                      'summation':'data, model and residual use identical detector pixels in each bin',
                      'display_support':'model drawn only inside the common saved sky-band envelope; no extrapolation drawn'},
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
    display = {}
    display_path = Path(run)/'profile-display.json'
    if display_path.exists():
        settings = json.loads(display_path.read_text())
        if (settings.get('schema_version')!=1 or settings.get('coordinates')!='zero_based_legacy_trimmed_detector_pixels'
                or settings.get('display_only') is not True):
            raise ValueError('invalid spatial-profile display settings')
        display = settings['exposures'].get(Path(result['raw']).name,{})
        if display and display.get('raw_sha256')!=result['raw_sha256']:
            raise ValueError('spatial-profile display settings belong to different raw data')
        inputs.append(display_path)
    if comparison:
        inputs.append(Path(comparison['path']))
    trace_data, trace_paths, mask_stage = load_trace_data(result)
    inputs.extend(trace_paths)
    before = {str(p): sha256(p) for p in inputs}
    wave, bands, _ = read_flux(inputs[0])
    legacy_data = None
    if comparison:
        old_wave, old_bands, _ = read_flux(Path(comparison['path']))
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
        'profile_limit_helper_sha256':sha256(REPO/'src/efospec/profile_limits.py'),
        'image_display_helper_sha256':sha256(REPO/'src/efospec/image_display.py'),
        'renderer_script_sha256':sha256(Path(__file__)),
        'python_executable': sys.executable,
        'matplotlib_version': matplotlib.__version__,
        'latex': bool(plt.rcParams['text.usetex']),
        'font_family': list(plt.rcParams['font.family']),
        'axis_label_pt': plt.rcParams['axes.labelsize'],
        'title': ax.get_title(),
        'legend_labels': [text.get_text() for text in ax.get_legend().get_texts()],
        'footer_text': [text.get_text() for text in fig.texts],
        'spectrum_annotations': [text.get_text() for text in ax.texts],
        'tick_label_base_pt': TICK_LABEL_PT,
        'tick_label_pt': ax.xaxis.get_major_ticks()[0].label1.get_fontsize(), 'legend_pt': 18,
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
        'legacy_samples_above_display': 0 if not comparison else int(
            ((old_wave >= ax.get_xlim()[0]) & (old_wave <= ax.get_xlim()[1])
             & (old_bands[0]/1e-16 > ax.get_ylim()[1])).sum()),
        'ylim_policy': 'Native flux plus uncertainty and all visible finite IRAF flux samples, with outward padding',
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
                                   'title': trace_ax.get_title()}
    record['combined_upper_wavelength_ticklabels'] = [t.get_text() for t in spectral_ax.get_xticklabels()]
    plt.close(combined)

    profile_fig, profile_diagnostics = draw_spatial_profiles(result, wave, trace_data,display=display)
    profile_stem = stem.with_name(stem.name.replace('FitSpectrum_', 'FitSpatialProfile_', 1))
    profile_pdf, profile_jpg = savefig_light(profile_fig, profile_stem, dpi_pdf=300, dpi_jpg=300)
    record['outputs'].extend([str(profile_pdf), str(profile_jpg)])
    record['spatial_profile_diagnostics'] = profile_diagnostics
    plt.close(profile_fig)

    # The daily log's middle card shows both sky-subtraction stages on one
    # wavelength axis, so the fitted sky can be judged against its residual.
    trace_fig, trace_axes = plt.subplots(2, 1, figsize=(13, 12.4), sharex=True)
    trace_fig.subplots_adjust(left=0.115, right=0.985, bottom=0.09, top=0.93, hspace=0.33)
    rectified = rectify_display(trace_data, wave)
    stage_diagnostics = {}
    for panel, stage in zip(trace_axes, ('before', 'after')):
        panel.set_xlim(record['display_limits']['wavelength_air_angstrom'])
        stage_diagnostics[stage] = draw_trace(panel, result, wave, trace_data,
                                              stage=stage, rectified=rectified,
                                              legend=stage == 'before')
        panel.tick_params(axis='x', which='both', bottom=True, labelbottom=True)
    trace_axes[0].set_xlabel('')
    trace_stem = stem.with_name(stem.name.replace('FitSpectrum_', 'FitTrace_', 1))
    trace_pdf, trace_jpg = savefig_light(trace_fig, trace_stem, dpi_pdf=300, dpi_jpg=300)
    record['outputs'].extend([str(trace_pdf), str(trace_jpg)])
    record['trace_stage_diagnostics'] = stage_diagnostics
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
        records.append(render_spectrum(result, run, no_legacy=args.no_legacy or args.legacy is None,
                                       legacy_root=args.legacy, suffix=suffix))
    from efospec.report import write_report
    all_records = [json.loads(path.read_text())
                   for path in sorted((run/'style-preview').glob('FitSpectrum_*.json'))]
    (run/'style-preview/all-plots.json').write_text(json.dumps(all_records, indent=2)+'\n')
    write_report(run)
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
