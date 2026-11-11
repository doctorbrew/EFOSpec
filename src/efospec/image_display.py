"""Display-only, sigma-clipped arcsinh scaling for detector and residual images."""
import numpy as np
from astropy.stats import sigma_clip, mad_std
from matplotlib.colors import FuncNorm


def image_normalization(data, *, residual=False, samples=None, cmap='gray_r',
                        bright_percentile=None, symmetric=False):
    """Estimate a robust scale without replacing or clipping any image pixels.

    Raw images are centred on the clipped median; sky residuals on zero. Both
    sides of the colour scale use the same arcsinh mapping and five-sigma range.
    A supplied background sample avoids letting the source set the contrast.

    ``bright_percentile`` extends only the upper limit to that percentile of the
    finite data, keeping the arcsinh linear width at the background sigma. A
    sky-subtracted spectrum is many hundreds of background sigma at its trace;
    a five-sigma upper limit saturates it and leaves only noise texture visible.
    The lower limit stays at five sigma, where the residuals really are noise.

    ``symmetric`` mirrors the upper limit below the centre, which a diverging
    colour map needs so that zero lands on its midpoint.
    """
    array = np.asarray(data, dtype=float)
    if samples is None:
        # Do not let overscan/vignetted detector borders determine contrast.
        dy, dx = [max(1, int(.03*n)) for n in array.shape]
        samples = array[dy:-dy, dx:-dx]
    good = np.asarray(samples, dtype=float)
    good = good[np.isfinite(good)]
    if not good.size:
        good = array[np.isfinite(array)]
    if not good.size:
        raise ValueError('no finite pixels for image display')
    clipped = sigma_clip(good, sigma=3., maxiters=5, cenfunc='median',
                         stdfunc='mad_std', masked=False)
    if not clipped.size:
        raise ValueError('no pixels remain for image display scaling')
    median = float(np.median(clipped))
    sigma = float(mad_std(clipped))
    # A perfectly constant image has no measurable dispersion. Retain a
    # finite, explicitly recorded display scale rather than divide by zero.
    fallback = not np.isfinite(sigma) or sigma <= 0
    if fallback:
        sigma = max(float(np.std(clipped)), 1.)
    center = 0. if residual else median
    high = center+5*sigma
    if bright_percentile is not None:
        if not np.isfinite(bright_percentile) or not 50 < bright_percentile <= 100:
            raise ValueError('bright percentile must lie above 50 and at most 100')
        finite = array[np.isfinite(array)]
        if not finite.size:
            raise ValueError('no finite pixels for image display')
        high = max(high, float(np.percentile(finite, bright_percentile)))
    low = center-(high-center) if symmetric else center-5*sigma
    norm = FuncNorm((lambda value: np.arcsinh((value-center)/sigma),
                     lambda value: center+sigma*np.sinh(value)),
                    vmin=low, vmax=high, clip=True)
    return norm, dict(stretch='arcsinh', colormap=cmap, display_only=True,
        bright_percentile=bright_percentile, symmetric_limits=bool(symmetric),
        upper_limit_rule=('background five sigma' if bright_percentile is None else
                          f'maximum of background five sigma and the {bright_percentile:g}th data percentile'),
        clipping='scale estimation only; all finite image pixels retained',
        sigma_clip=3., maximum_iterations=5, statistic='median and MAD sigma',
        input_samples=int(good.size), retained_samples=int(clipped.size),
        clipped_median=median, center=center, robust_sigma=sigma,
        degenerate_scale_fallback=fallback, linear_width=sigma,
        vmin=float(norm.vmin), vmax=float(norm.vmax))


def mark_zoom_region(full_ax, zoom_ax, *, label="Zoom at right"):
    """Outline the exact displayed pixel bounds of the companion zoom axes."""
    from matplotlib.patches import Rectangle
    from matplotlib import patheffects
    x0, x1 = sorted(zoom_ax.get_xlim())
    y0, y1 = sorted(zoom_ax.get_ylim())
    box = Rectangle((x0, y0), x1-x0, y1-y0, fill=False,
                    edgecolor='xkcd:golden yellow', linewidth=2.5, zorder=8)
    box.set_path_effects([patheffects.Stroke(linewidth=4.5, foreground='black'),
                          patheffects.Normal()])
    full_ax.add_patch(box)
    full_ax.annotate(label, (x0, y1), xytext=(5, -6),
                     textcoords='offset points', color='black', fontsize=18,
                     va='top', zorder=9, bbox=dict(facecolor='white', alpha=.8,
                                                 edgecolor='none', pad=2))
    return [float(x0), float(x1), float(y0), float(y1)]
