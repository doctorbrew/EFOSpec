"""Shared scientific plot style; choose the matplotlib backend before importing.

Requires matplotlib, numpy, SciencePlots, pypalettes, and a working LaTeX setup.
The module applies the house rcParams at import, preserving the historic API.
It never changes scientific selection or suppresses warnings.
"""
from pathlib import Path
import math
import shutil

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, AutoLocator, AutoMinorLocator
from matplotlib.lines import Line2D

try:
    import scienceplots  # Registers the science style.
    from pypalettes import load_cmap
except ImportError as exc:
    raise ImportError("House plot style requires SciencePlots and pypalettes; install them in the project environment.") from exc

HIROSHIGE = load_cmap("Hiroshige", cmap_type="continuous")
HIROSHIGE_R = load_cmap("Hiroshige", cmap_type="continuous", reverse=True)
COMP_COLORS = [HIROSHIGE(i / 5) for i in range(6)]
COL_TYPE_II, COL_TYPE_IIb, COL_TYPE_IIn, COL_TYPE_Ib, COL_TYPE_Ic, COL_TYPE_IcBL = COMP_COLORS

# Exact colors recorded in the archived plot/atlas conventions.
BAND_COLORS = {
    "u": "#8f2ff3", "g": "#228B22", "r": "#DC143C", "i": "#FF8C00",
    "z": "#8B0000", "y": "#00ffff", "b": "#3e82fc", "v": "#0cff0c",
    "c": "#00BFFF", "o": "#FF4500",
    "ATLAS-c": "#00BFFF", "ATLAS-o": "#FF4500",
    "ZTF-g": "#228B22", "ZTF-r": "#DC143C", "ZTF-i": "#FF8C00",
}

# Optional 1987A host-sample encodings retained from the original helper.
COL_SECURE, COL_CAND, COL_MUSE, COL_EXCL = "#1A5276", "#AED6F1", "#C0392B", "#BDC3C7"
APT_COL = {"global": "#1A5276", "local": "#C0392B"}
APT_FILL = {"global": "#AED6F1", "local": "#F1948A"}
FILT_GROUPS = {
    "UV": ["GALEX_FUV", "GALEX_NUV"],
    "Opt": ["SDSS_u", "SDSS_g", "SDSS_r", "SDSS_i", "SDSS_z",
            "PanSTARRS_g", "PanSTARRS_r", "PanSTARRS_i", "PanSTARRS_z", "PanSTARRS_y",
            "DES_g", "DES_r", "DES_i", "DES_z", "DES_Y"],
    "NIR": ["2MASS_J", "2MASS_H", "2MASS_K"],
    "MIR": ["WISE_W1", "WISE_W2", "WISE_W3", "WISE_W4"],
}
FILT_GRP_COL = dict(zip(FILT_GROUPS, [HIROSHIGE(x) for x in np.linspace(0.05, 0.95, 4)]))


def apply_style():
    """Apply the established SciencePlots + LaTeX rcParams."""
    plt.style.use("science")
    plt.rcParams.update({
        "text.usetex": True, "font.family": "serif", "font.size": 18,
        "axes.labelsize": 22, "axes.titlesize": 20, "legend.fontsize": 18,
        "xtick.labelsize": 18, "ytick.labelsize": 18,
        "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
        "lines.linewidth": 2.0, "lines.markersize": 10, "errorbar.capsize": 3,
    })


def band_color(band, lambda_eff=None):
    """Return an established color, or map a supplied Angstrom wavelength.

    Wavelength is used for color only: this function never identifies a filter.
    Unknown bands without a wavelength are neutral gray.
    """
    if band in BAND_COLORS:
        return BAND_COLORS[band]
    if lambda_eff is None:
        return (0.4, 0.4, 0.4)
    wavelength = float(lambda_eff)
    if not math.isfinite(wavelength) or wavelength <= 0:
        raise ValueError("lambda_eff must be a positive finite wavelength in Angstrom")
    return HIROSHIGE_R(float(np.clip((wavelength - 2000.0) / 8500.0, 0, 1)))


def filter_group(name):
    """Return a known host-SED filter group, or None for an unknown filter."""
    return next((group for group, names in FILT_GROUPS.items() if name in names), None)


def filter_color(name):
    return FILT_GRP_COL.get(filter_group(name), "#555555")


def _safe_spacing(spacing, limits):
    spacing = float(spacing)
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("Tick spacing must be positive and finite")
    span = abs(limits[1] - limits[0])
    return spacing * max(1, math.ceil(span / spacing / 490))


def _linear_locators(axis, limits, ticks):
    if ticks is None:
        axis.set_major_locator(AutoLocator())
        axis.set_minor_locator(AutoMinorLocator())
    else:
        if len(ticks) != 2:
            raise ValueError("Tick specification must be (major, minor) or None")
        axis.set_major_locator(MultipleLocator(_safe_spacing(ticks[0], limits)))
        axis.set_minor_locator(MultipleLocator(_safe_spacing(ticks[1], limits)))


def _tick_style(ax, fs):
    ax.xaxis.set_ticks_position("both")
    ax.yaxis.set_ticks_position("both")
    ax.tick_params(axis="both", which="major", direction="in", width=1.6, length=9, color="k", labelsize=fs)
    ax.tick_params(axis="both", which="minor", direction="in", width=1.0, length=5, color="k", labelsize=fs)


def set_plotparams(ax_obj, xticks=(1, 0.5), yticks=(1, 0.5), grid=True, fs=18, tick_fs=None):
    """Style linear axes with inward ticks; grid remains visually absent.

    Apply after setting data/limits. Use None for automatic tick locations.
    The retained grid argument does not enable a visible grid in the house style.
    """
    if ax_obj.get_xscale() != "linear" or ax_obj.get_yscale() != "linear":
        raise ValueError("Use set_plotparams_log for logarithmic axes")
    _linear_locators(ax_obj.xaxis, ax_obj.get_xlim(), xticks)
    _linear_locators(ax_obj.yaxis, ax_obj.get_ylim(), yticks)
    ax_obj.grid(False, which="both")
    _tick_style(ax_obj, fs if tick_fs is None else tick_fs)


def set_plotparams_log(ax_obj, axis="both", grid=True, fs=18):
    """Style already-logarithmic axes, preserving their bases and locators."""
    if axis not in {"x", "y", "both"}:
        raise ValueError("axis must be x, y, or both")
    for name in (["x", "y"] if axis == "both" else [axis]):
        if getattr(ax_obj, "get_" + name + "scale")() != "log":
            raise ValueError(f"Set {name} to log scale before calling set_plotparams_log")
    # Native or caller-supplied locators already match the scale's chosen base.
    # Replacing them with base-10 locators would corrupt base-2/e tick labels.
    ax_obj.grid(False, which="both")
    _tick_style(ax_obj, fs)


def styled_legend(ax, **kwargs):
    defaults = dict(fontsize=18, frameon=True, shadow=True, fancybox=True,
                    framealpha=0.9, handlelength=1.8, handletextpad=0.5)
    defaults.update(kwargs)
    return ax.legend(**defaults)


def sample_legend_handles():
    """Optional legend for the archived 1987A host-sample categories."""
    return [Line2D([0], [0], marker=marker, color="w", markerfacecolor=color,
                   markeredgecolor="k", markersize=12, label=label)
            for label, marker, color in [
                ("Secure 1987A-like", "o", COL_SECURE), ("Candidate", "D", COL_CAND),
                ("1987A-like (MUSE observed)", "*", COL_MUSE),
                ("Type II (comparison)", "o", COL_TYPE_II), ("Type IIb", "^", COL_TYPE_IIb),
                ("Type Ib", "s", COL_TYPE_Ib), ("Type Ic", "D", COL_TYPE_Ic)]]


def _save_pair(fig, stem, dpi_pdf, dpi_jpg):
    if not all(math.isfinite(dpi) and dpi > 0 for dpi in [dpi_pdf, dpi_jpg]):
        raise ValueError("Output DPI must be positive and finite")
    missing = [tool for tool in ["latex", "dvipng"] if not shutil.which(tool)]
    if missing:
        raise RuntimeError("House PDF/JPG export requires LaTeX tools: " + ", ".join(missing) + ". No alternate font rendering was used.")
    stem = Path(stem)
    if stem.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise ValueError("Pass an output stem without an image extension")
    stem.parent.mkdir(parents=True, exist_ok=True)
    pdf, jpg = Path(str(stem) + ".pdf"), Path(str(stem) + ".jpg")
    fig.savefig(pdf, dpi=dpi_pdf, format="pdf", bbox_inches="tight")
    fig.savefig(jpg, dpi=dpi_jpg, format="jpg", bbox_inches="tight")
    return pdf, jpg


def savefig(fig, path_no_ext):
    """Save PDF at 2000 raster DPI and JPG at 300 DPI; return their paths."""
    return _save_pair(fig, path_no_ext, 2000, 300)


def savefig_light(fig, path_no_ext, dpi_pdf=300, dpi_jpg=300):
    """Save a configurable lower-memory PDF/JPG pair; return their paths."""
    return _save_pair(fig, path_no_ext, dpi_pdf, dpi_jpg)


apply_style()
