"""Load the one project house-style helper; no embedded or fallback style."""
import importlib.util
from functools import wraps
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')

_path=Path(__file__).resolve().parents[2]/'plot_style.py'
_spec=importlib.util.spec_from_file_location('efospec_house_plot_style',_path)
style=importlib.util.module_from_spec(_spec)
with matplotlib.rc_context():
    _spec.loader.exec_module(style)
    HOUSE_RC=matplotlib.rcParams.copy()
COLORS=[style.HIROSHIGE_R(float(p)) for p in (.05,.25,.95)]


def house_style(function):
    """Style our figures without leaking TeX into third-party PypeIt labels."""
    @wraps(function)
    def wrapped(*args,**kwargs):
        with matplotlib.rc_context(HOUSE_RC):
            return function(*args,**kwargs)
    return wrapped


def plain_tex(text):
    # Preserve intentional math and already escaped metadata on repeated draws.
    parts=re.split(r'(\$[^$]*\$)',text)
    for i in range(0,len(parts),2):
        part=parts[i].replace('—','--').replace('−','-')
        part=re.sub(r'(?<!\\)([_#%&])',r'\\\1',part)
        parts[i]=part.replace('Å',r'$\mathrm{\AA}$').replace('σ',r'$\sigma$')
    return ''.join(parts)


@house_style
def save_qc(fig, directory, kind, object_name, *, tick_fontsize=18, legend_fontsize=18, title_fontsize=20, label_fontsize=None):
    """Export house-style figures; tick_fontsize is the base before the 1.3 factor."""
    from matplotlib.ticker import MaxNLocator,FixedLocator,NullLocator
    from matplotlib.text import Text
    for ax in fig.axes:
        if not ax.get_visible():continue
        if ax.get_label()=='<colorbar>':
            # ImageNormalize uses a function scale; linear/log tick locators
            # would misrepresent that colour scale.
            ax.tick_params(direction='in',which='both',labelsize=style.tick_label_size(tick_fontsize),length=9,width=1.6)
            ax.xaxis.get_offset_text().set_fontsize(style.tick_label_size(tick_fontsize))
            ax.yaxis.get_offset_text().set_fontsize(style.tick_label_size(tick_fontsize))
            if label_fontsize is not None:
                ax.xaxis.label.set_fontsize(label_fontsize)
                ax.yaxis.label.set_fontsize(label_fontsize)
            continue
        limits=ax.get_xlim()
        ticks=MaxNLocator(nbins=6).tick_values(*limits)
        step=abs(ticks[1]-ticks[0])
        fixed=ax.xaxis.get_major_locator()
        style.set_plotparams(ax,xticks=(step,step/4),yticks=None,grid=False,fs=tick_fontsize)
        if isinstance(fixed,FixedLocator):
            ax.xaxis.set_major_locator(fixed);ax.xaxis.set_minor_locator(NullLocator())
        ax.title.set_fontsize(title_fontsize)
        if label_fontsize is not None:
            ax.xaxis.label.set_fontsize(label_fontsize)
            ax.yaxis.label.set_fontsize(label_fontsize)
        handles,labels=ax.get_legend_handles_labels()
        if handles:
            style.styled_legend(ax,ncol=min(3,len(handles)),loc='upper center',
                                bbox_to_anchor=(.5,-.2),fontsize=legend_fontsize)
    # QC labels are plain metadata strings, not arbitrary TeX input.
    for text in fig.findobj(Text):
        if text.get_text():text.set_text(plain_tex(text.get_text()))
    safe=re.sub(r'[^A-Za-z0-9.+-]','_',object_name)
    stem=Path(directory)/f'FitQC_{safe}_{kind}'
    # Rotated TeX labels at the larger profile font can extend beyond the
    # raster backend's tight bounds. Retain a physical margin in every format.
    padding = .5 if kind == 'profiles' else matplotlib.rcParams['savefig.pad_inches']
    with matplotlib.rc_context({'savefig.pad_inches': padding}):
        style.savefig_light(fig,stem,dpi_pdf=300,dpi_jpg=300)
        fig.savefig(Path(directory)/(kind+'.png'),dpi=150,bbox_inches='tight')
    return stem
