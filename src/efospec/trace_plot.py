"""Shared nightly wavelength-horizontal detector rendering."""
import numpy as np
from matplotlib.colors import to_rgb, to_hex
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from .figure_style import style
from .image_display import image_normalization
set_plotparams = style.set_plotparams
styled_legend = style.styled_legend
PYPEIT_COLOUR = to_hex(.6*np.array(to_rgb('xkcd:red'))+.4)
BACKGROUND_COLOUR = 'xkcd:pastel blue'
SKY_LINES = (5577.338, 6300.304, 6363.776)
TICK_LABEL_PT = 18
BRIGHT_PERCENTILE = 99.5
TRACE_STAGES = {
    'before': ('Before sky subtraction: data and sky', False),
    'after': ('After sky subtraction: data minus fitted sky', True),
}

def mark_sky_lines(ax):
    for wavelength in SKY_LINES:
        if ax.get_xlim()[0] < wavelength < ax.get_xlim()[1]:
            ax.axvline(wavelength, color='0.4', linestyle=':', linewidth=0.9,
                       alpha=0.65, zorder=0.5)

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
