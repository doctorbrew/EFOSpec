"""Render saved trace arrays for the manual, without refitting or reducing data."""
from pathlib import Path
import hashlib
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import plot_style as style

SOURCE = ROOT / 'runs/2026-10-29/nightly/20261110T171353Z-aa76fb/reduction/exposures/EFOSC.2026-10-30T03:07:16.495/native/tvma2_20261029_Gr13_Free_slit1.0_1_images.npz'
OUT = ROOT / 'manuals_pessto/figures/FitManual_vma2_saved_traces'
source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
with np.load(SOURCE) as saved:
    traces = saved['found_traces'].copy()
    names = saved['found_names'].tolist()
    selected = saved['trace'].copy()
fig, axes = plt.subplots(len(traces), 1, figsize=(13, 12), sharex=True)
for index, (ax, trace) in enumerate(zip(axes, traces)):
    pixel = np.arange(len(trace))
    is_selected = np.allclose(trace, selected, rtol=0, atol=1e-6)
    label = 'Saved trace '+str(index+1)+(' (selected extraction)' if is_selected else '')
    ax.plot(pixel, trace, color=style.HIROSHIGE_R([0.12, 0.85, 0.98][index]), lw=2, label=label)
    ax.set_xlim(pixel[0], pixel[-1])
    span = float(np.ptp(trace))
    pad = max(0.3, 0.25*span)
    ax.set_ylim(float(np.min(trace))-pad, float(np.max(trace))+2*pad)
    ax.set_ylabel('Spatial pixel', fontsize=22)
    style.set_plotparams(ax, xticks=(200,50), yticks=None)
    style.styled_legend(ax, loc='upper left')
axes[-1].set_xlabel('Spectral pixel', fontsize=22)
fig.subplots_adjust(hspace=0.12, left=0.14, bottom=0.09, top=0.98, right=0.98)
assert plt.rcParams['text.usetex'] is True
for ax in axes:
    assert all(abs(t.get_fontsize()-23.4)<1e-6 for t in ax.get_yticklabels())
style.savefig_light(fig, OUT, dpi_pdf=300, dpi_jpg=300)
plt.close(fig)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash
record = {'source': str(SOURCE.relative_to(ROOT)), 'sha256': source_hash,
          'arrays': ['found_traces', 'trace'], 'candidate_names': names,
          'coordinate_system': 'saved extraction-window pixels; no raw-origin offset added',
          'selection': 'all three stored candidate traces, original order',
          'processing': 'plot only; no fitting, smoothing or new reduction',
          'style': {'helper':'plot_style.py','usetex':True,'tick_size_pt':23.4,'jpg_dpi':300,'palette':'Hiroshige reversed'},
          'outputs': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT.with_suffix('.jpg'),OUT.with_suffix('.pdf')]}}
OUT.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
print(OUT)
