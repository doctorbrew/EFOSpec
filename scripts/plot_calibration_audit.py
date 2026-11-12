#!/usr/bin/env python3
"""Plot retained one-night independent response trials using the project style."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.figure_style import house_style, save_qc, COLORS
import matplotlib.pyplot as plt
import numpy as np


@house_style
def draw(path):
    r=json.loads(path.read_text())
    labels=[];before=[];after=[]
    for trial in r['paired_response_trials']:
        train=next(s for s in r['standard_checks'] if s['raw']==trial['free_raw'])
        for qa in trial['held_out']:
            old=next(t for t in r['transfers'] if t['training_raw']==trial['free_raw'] and t['raw']==qa['raw'])
            labels.append(train['object']+' to '+qa['reference_name']+'\nGr13 / '+train['setup']['slit'])
            before.append(100*old['continuum_transfer']['maximum_shape_departure_fraction'])
            after.append(100*qa['continuum_transfer']['maximum_shape_departure_fraction'])
    if not labels:raise ValueError('no held-out response trials to plot')
    fig,ax=plt.subplots(figsize=(14,7),layout='constrained')
    x=np.arange(len(labels))
    ax.bar(x-.18,before,.36,color=COLORS[0],label='Original response')
    ax.bar(x+.18,after,.36,color=COLORS[1],label='Filtered-response trial')
    ax.set_xticks(x,labels);ax.set_ylim(0,max(before+after)*1.25)
    ax.set_ylabel('Maximum continuum colour residual (percent)')
    ax.set_title('EFOSpec / '+r['night']+' / Independent standard transfers')
    save_qc(fig,path.parent,'response-trials','EFOSC2');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('audit',type=Path)
    draw(p.parse_args().audit)
