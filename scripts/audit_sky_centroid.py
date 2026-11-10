#!/usr/bin/env python3
"""Audit a saved 6363-A centroid; never apply a shift or change acceptance gates."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from scipy.optimize import curve_fit, brentq
from scipy.special import erf

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO/'src')]
from efospec.inventory import sha256
from efospec.figure_style import house_style, style, COLORS


def audit(night, failure, profile, output):
    if date.fromisoformat(night).isoformat() != night or night not in output.parts:
        raise ValueError('select one observing date and an output inside that date')
    check = json.loads(failure.read_text())
    diagnostic = profile.parent/'diagnostic.json'
    source = json.loads(diagnostic.read_text())
    if source['raw_sha256'] != check['raw_sha256'] or sha256(profile) != source['profile_sha256']:
        raise ValueError('profile does not match the saved failure')
    lines = check['lines']
    if [x['rest_air_angstrom'] for x in lines] != [5577.338,6300.304,6363.776]:
        raise ValueError('this audit needs both anchors and the independent 6363-A fit')
    line = lines[2]
    width = line['projected_slit_width_angstrom']
    if line.get('profile') != 'uniform_slit_convolved_gaussian' or not width:
        raise ValueError('this audit requires a saved projected-slit profile')
    shift = float(np.mean([x['offset_angstrom'] for x in lines[:2]]))
    rest = line['rest_air_angstrom']; expected = rest-shift
    with np.load(profile) as data:
        wave, sky = data['wave_air'], data['sky_electron']
    old_wave = np.array(line['fit_samples']['wave_air'])
    old_sky = np.array(line['fit_samples']['sky_electron'])
    np.testing.assert_allclose(np.interp(old_wave,wave,sky),old_sky,rtol=0,atol=1e-9)
    before = {str(p):sha256(p) for p in (failure,profile,diagnostic)}

    def shape(w,c,s):
        return .5*(erf((w-c+width/2)/(np.sqrt(2)*s))
                   -erf((w-c-width/2)/(np.sqrt(2)*s)))
    def model(w,a,c,s,b,m):return a*shape(w,c,s)+b+m*(w-c)
    def fit(w,f):
        base=float(np.median(np.r_[f[:2],f[-2:]]))
        guess=[max(float(f.max()-base),1.),float(np.clip(w[f.argmax()],expected-19,expected+19)),3.,base,0.]
        p,cov=curve_fit(model,w,f,p0=guess,
            bounds=([0,expected-20,.5,-np.inf,-np.inf],[np.inf,expected+20,14,np.inf,np.inf]),maxfev=10000)
        error=np.sqrt(np.diag(cov)); correlation=cov/error[:,None]/error[None,:]
        residual=f-model(w,*p)
        noise=max(1.4826*np.median(abs(residual-np.median(residual))),1e-6)
        fwhm=2*brentq(lambda x:shape(x,0,p[2])-.5*shape(0,0,p[2]),0,3*width)
        return dict(samples=len(w),degrees_of_freedom=len(w)-len(p),
            parameters=p.tolist(),parameter_errors=error.tolist(),correlation=correlation.tolist(),
            centroid_air_angstrom=float(p[1]),centroid_error_angstrom=float(error[1]),
            residual_if_anchor_shift_applied_angstrom=float(p[1]-expected),
            amplitude_over_residual_mad=float(p[0]/noise),amplitude_over_formal_error=float(p[0]/error[0]),
            fitted_fwhm_angstrom=float(fwhm),sigma_angstrom=float(p[2]),
            wave_air=w.tolist(),sky_electron=f.tolist(),model_electron=model(w,*p).tolist())
    original=fit(old_wave,old_sky)
    np.testing.assert_allclose([original['centroid_air_angstrom'],original['centroid_error_angstrom']],
                              [line['measured_air_angstrom'],line['centroid_error_angstrom']],rtol=1e-6)
    midpoint=(6300.304+rest)/2-shift
    trials=[]
    for half in (32.,36.,40.,48.):
        keep=(abs(wave-expected)<half)&(wave>midpoint)&np.isfinite(sky)
        trials.append(dict(half_window_angstrom=half,lower_guard_angstrom=midpoint,
                           **fit(wave[keep],sky[keep])))
    output.mkdir(parents=True,exist_ok=False)
    report=dict(night=night,object=source['object'],raw=check['raw'],raw_sha256=check['raw_sha256'],
        status='diagnostic_only',shift_applied=False,acceptance_limits_changed=False,
        anchor_shift_angstrom=shift,expected_unshifted_centroid_angstrom=expected,
        dispersion_angstrom_per_pixel=float(np.median(np.diff(old_wave))),
        projected_slit_width_angstrom=width,original=original,guarded_window_trials=trials,
        input_sha256=before,script_sha256=sha256(Path(__file__)),
        limitations=['Formal errors use local least-squares covariance and fitted residual variance, not calibrated detection significance.',
            'The anchor correction is an unapplied diagnostic; trial offsets share those anchors.',
            'The midpoint guard reduces neighbouring 6300-A contamination; it does not prove the absence of other blends.',
            'Window trials are not independent observations or a validated automatic acceptance policy.'])
    draw(report,output,model,wave,sky)
    assert all(sha256(Path(p))==h for p,h in before.items())
    report['inputs_unchanged']=True
    report['figure_sha256']={p.name:sha256(p) for p in output.glob('FitSkyCentroid_*.*')}
    (output/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copy2(__file__,output/'audit-script.py')
    return report


@house_style
def draw(report,output,model,wave,sky):
    import matplotlib.pyplot as plt
    fig, (ax, precision)=plt.subplots(2,1,figsize=(14,12))
    fig.subplots_adjust(left=.12,right=.97,top=.91,bottom=.10,hspace=.5)
    expected=report['expected_unshifted_centroid_angstrom']
    original=report['original']; trial=report['guarded_window_trials'][2]
    keep=(wave>6330)&(wave<6425)&np.isfinite(sky)
    ax.plot(wave[keep],sky[keep],color='0.3',marker='o',ms=5,lw=1.,label='Saved sky samples')
    for record,color,label in [(original,COLORS[2],'Original: 9 samples'),(trial,COLORS[0],'Guarded wider window: 13 samples')]:
        xx=np.linspace(min(record['wave_air']),max(record['wave_air']),400)
        ax.plot(xx,model(xx,*record['parameters']),color=color,lw=2.,label=label)
        ax.axvline(record['centroid_air_angstrom'],color=color,lw=1.,ls=':')
    ax.axvline(expected,color='0.3',ls='--',lw=1.,label='Expected from 5577/6300 anchors')
    ax.set_xlim(6330,6425);ax.set_ylim(float(sky[keep].min())-30,float(sky[keep].max())+50)
    ax.set_xlabel(r'Unshifted air wavelength [$\AA$]');ax.set_ylabel(r'Sky signal [$e^{-}$]')
    style.set_plotparams(ax,xticks=(20,5),yticks=None)
    style.styled_legend(ax,loc='upper right',fontsize=16,ncol=2)
    records=[original,*report['guarded_window_trials']]
    for i,record in enumerate(records):
        color=COLORS[2] if i==0 else COLORS[0]
        value=record['residual_if_anchor_shift_applied_angstrom']
        precision.errorbar(i,value,yerr=record['centroid_error_angstrom'],fmt='none',ecolor=color,capsize=4)
        precision.plot(i,value,'o',mfc='white',mec=color,ms=9)
    precision.axhspan(-3,3,color='0.7',alpha=.15)
    precision.axhline(0,color='0.3',ls='--',lw=1.)
    precision.set_xlim(-.5,4.5);precision.set_ylim(-6,9)
    precision.set_ylabel(r'Offset after candidate shift [$\AA$]')
    precision.set_xlabel('Original window / guarded diagnostic half-window')
    style.set_plotparams(precision,xticks=(1,.5),yticks=(3,1))
    precision.set_xticks(range(5),['Original',r'$32\,\AA$',r'$36\,\AA$',r'$40\,\AA$',r'$48\,\AA$'])
    precision.text(.02,.95,r'Bars: formal $1\sigma$; shaded: current $\pm3\,\AA$ residual gate',
                   transform=precision.transAxes,fontsize=16,va='top')
    fig.suptitle(report['object']+' / 6363.78 A centroid audit / No correction applied',fontsize=20)
    style.savefig_light(fig,output/f"FitSkyCentroid_{report['object']}_Gr13_air")
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--night',required=True)
    parser.add_argument('--failure',required=True,type=Path)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    record=audit(args.night,args.failure,args.profile,args.output)
    print(json.dumps(dict(output=str(args.output),status=record['status'],inputs_unchanged=record['inputs_unchanged'])))
