"""Dated, explicit-target trials of bounded PypeIt backgrounds."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from copy import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import uuid
import traceback

import numpy as np

from .inventory import sha256
from .local_sky import BackgroundSupportError, exposure_sky_inputs
from .recipes import validate_recipe
from .revisions import Exposure, FailedExposure, reextract, expand_archive_window


def candidate_objects(exposure):
    """Keep failed-exposure candidates as hypotheses, including in filenames."""
    if isinstance(exposure, FailedExposure):
        row=exposure.window.shape[0]//2
        return [dict(id='primary',label=f'{exposure.result["object"]}_C{i+1}_trial',kind='point',
                     spec=float(row+exposure.window.origin[0]),spat=float(t[row]+exposure.window.origin[1]),
                     fwhm=4.,radius=7.) for i,t in enumerate(exposure.images['found_traces'])]
    return [dict(exposure.primary_object(),label=exposure.result['object']+'_trial')]


def plot_geometry(exposure, directory):
    """Show actual raw electrons, saved model and candidate traces, not mock data."""
    from .figure_style import COLORS, house_style, save_qc
    @house_style
    def draw():
        import matplotlib.pyplot as plt
        from astropy.visualization import ImageNormalize, AsinhStretch
        data=exposure.images['data'];ny,nx=data.shape;y0,x0=exposure.window.origin
        x=np.arange(nx)+x0
        fig,(profile,image)=plt.subplots(2,1,figsize=(18,14),gridspec_kw={'height_ratios':[1,1.4]})
        profile.plot(x,np.nanmedian(data,axis=0),color=COLORS[0],label='Raw electrons: median over rows')
        profile.plot(x,np.nanmedian(exposure.images['sky'],axis=0),color=COLORS[1],ls='--',label='Previous background model')
        lo,hi=np.nanpercentile(data,[2,99])
        image.imshow(data,origin='lower',aspect='auto',cmap='gray_r',
                     norm=ImageNormalize(vmin=lo,vmax=hi,stretch=AsinhStretch()),
                     extent=[x0-.5,x0+nx-.5,y0-.5,y0+ny-.5])
        traces=exposure.images.get('found_traces',np.asarray([exposure.images.get('trace')]))
        for i,trace in enumerate(traces):
            position=float(trace[ny//2]+x0);color=COLORS[i%len(COLORS)]
            profile.axvline(position,color=color,ls=':',label=f'C{i+1}: x={position:.1f} (unverified)')
            image.plot(trace+x0,np.arange(ny)+y0,color=color,lw=1.2)
        for ax in (profile,image):ax.set_xlim(x0,x0+nx-1);ax.set_xlabel('Raw spatial detector pixel x')
        profile.set_ylabel('Electrons per pixel');image.set_ylabel('Raw spectral detector row y')
        profile.set_title(exposure.result['object']+' -- local background geometry')
        fig.subplots_adjust(hspace=.58,bottom=.08,top=.95)
        save_qc(fig,directory,'local-background-geometry',exposure.result['object'])
        plt.close(fig)
    draw()


def plot_extraction(directory,exposure,obj,degree):
    from .figure_style import COLORS, house_style, save_qc
    @house_style
    def draw():
        import matplotlib.pyplot as plt
        with np.load(next((directory/'native').glob('*_images.npz'))) as z:
            data,sky,mask,accepted,trace,wave=(z[k] for k in ('data','sky','sky_input_mask','sky_accepted_mask','trace','waveair'))
        ny,nx=data.shape;x=np.arange(nx)+exposure.window.origin[1]
        fig,axes=plt.subplots(3,1,figsize=(18,18))
        for ax,rows in zip(axes,np.array_split(np.arange(ny),3)):
            profile=np.nanmedian(data[rows],axis=0);model=np.nanmedian(sky[rows],axis=0)
            ax.plot(x,profile,color=COLORS[0],label='Data')
            ax.plot(x,model,color=COLORS[1],label=f'PypeIt background, degree {degree}')
            ax.fill_between(x,0,mask[rows].mean(axis=0),transform=ax.get_xaxis_transform(),alpha=.15,color=COLORS[0],label='Selected background')
            center=float(np.median(trace[rows]))+exposure.window.origin[1]
            ax.axvspan(center-obj['radius'],center+obj['radius'],alpha=.15,color=COLORS[2],label='Source aperture')
            # Display only the sampled region and aperture; the model outside
            # both bands is extrapolation, not an inferred detector-wide sky.
            sampled=np.flatnonzero(mask[rows].any(axis=0));lo=max(0,sampled.min()-4);hi=min(nx,sampled.max()+5)
            ax.set_xlim(x[lo],x[hi-1]);values=np.r_[profile[lo:hi],model[lo:hi]]
            margin=max(np.ptp(values)*.12,1.);ax.set_ylim(values.min()-margin,values.max()+margin)
            ax.set(xlabel='Raw spatial detector pixel x',ylabel='Median electrons per pixel',
                   title=f'{np.nanmin(wave[rows]):.0f}–{np.nanmax(wave[rows]):.0f} Å')
        fig.suptitle(obj['label']+' -- unverified source; two-sided background')
        fig.subplots_adjust(hspace=.8,bottom=.12,top=.94)
        save_qc(fig,directory/'qa','local-background-fit',obj['label']);plt.close(fig)
        image=next((directory/'native').glob('*_images.npz'))
        (directory/'qa/local-background-figure.json').write_text(json.dumps({
            'images_sha256':sha256(image),'figures':{p.name:sha256(p) for p in (directory/'qa').glob('FitQC_*local-background-fit.jpg')}},indent=2)+'\n')
    draw()


def run_trials(night, targets, project_root, *, width_pixels=None, degrees=(1,2), minimum_width_pixels=None, padding_pixels=0):
    """Without width_pixels, inspect geometry only; never choose spatial units."""
    if date.fromisoformat(night).isoformat()!=night:raise ValueError('use one ISO observing date')
    if not targets:raise ValueError('name the targets explicitly')
    root=Path(project_root).resolve()/'runs'/night
    pointer=json.loads((root/'nightly/current.json').read_text())
    run=root/'nightly'/pointer['revision']/'reduction'
    run.resolve().relative_to(root)
    manifest=json.loads((run/'run.json').read_text())
    names={name.removeprefix('SN').removeprefix('AT') for name in targets}
    matches=[]
    for key,failed in [('results',False),('errors',True)]:
        for record in manifest.get(key,[]):
            name=record.get('object','')
            if name.removeprefix('SN').removeprefix('AT') not in names:continue
            if failed and record.get('code') not in {'source_selection_required', 'background_support_required'}:
                raise ValueError(f'{name}: cannot start a background trial before {record.get("code")} is resolved')
            product=Path(record['path'] if failed else record['product']).name
            matches.append(((FailedExposure if failed else Exposure)(run,product),product,failed))
    if {e.result['object'].removeprefix('SN').removeprefix('AT') for e,_,_ in matches} != names:
        raise ValueError('one or more requested targets are absent from the selected epoch')
    token=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    output=root/'QC'/('local-background-'+token);output.mkdir(parents=True,exist_ok=False)
    summary=dict(night=night,parent_run=str(run),parent_manifest_sha256=sha256(run/'run.json'),
                 mode='geometry_preflight' if width_pixels is None else 'pypeit_extraction_trials',
                 width_unit='spatial_detector_pixels',width_policy_confirmed=width_pixels is not None,
                 targets=[],limitations=['Candidate labels do not verify target identity.',
                     'Saved neighbours use the requested source guard; broad-host classification is not automated.',
                     'These trials do not change the epoch-selected reduction or its accepted products.'])
    for exposure,product,failed in matches:
        directory=output/exposure.result['object'];directory.mkdir()
        plot_geometry(exposure,directory)
        record=dict(object=exposure.result['object'],raw_name=Path(exposure.frame['path']).name,
                    input_sha256=exposure.hashes,window_shape=list(exposure.window.shape),
                    raw_origin=list(exposure.window.origin),cases=[])
        for index,obj in enumerate(candidate_objects(exposure),1):
            for width in ((30,40,50) if width_pixels is None else (width_pixels,)):
                recipe=exposure.default_recipe();recipe.update(source_mode='manual',objects=[obj])
                recipe['sky']=dict(mode='pypeit_local',include=[],exclude=[],width_pixels=width,degree=1,sigma_clip=4.)
                if minimum_width_pixels is not None:recipe['sky']['minimum_width_pixels']=minimum_width_pixels
                case=dict(candidate=index,raw_x=obj['spat'],width_pixels=width,identity='unverified')
                try:
                    recipe=validate_recipe(recipe,exposure.window,exposure.hashes)
                    selected=exposure
                    try:
                        mask,trace,info=exposure_sky_inputs(selected,recipe)
                    except BackgroundSupportError as exc:
                        if not padding_pixels:raise
                        case['original_window_failure']=str(exc)
                        selected=expand_archive_window(copy(exposure),padding_pixels)
                        recipe.update(spatial_padding_pixels=padding_pixels,input_sha256=selected.hashes)
                        recipe=validate_recipe(recipe,selected.window,selected.hashes)
                        mask,trace,info=exposure_sky_inputs(selected,recipe)
                        case['expanded_window']={'shape':list(selected.window.shape),'origin':list(selected.window.origin)}
                    case.update(status='geometry_pass',selection=info)
                    row=selected.window.shape[0]//2
                    x=np.arange(selected.window.shape[1])+selected.window.origin[1]
                    case['midrow_bands']=[[int(values.min()),int(values.max()+1)] for values in
                        (x[mask[row]&(x<obj['spat'])],x[mask[row]&(x>obj['spat'])])]
                    for degree in degrees:
                        recipe['sky']['degree']=degree
                        stem=f'candidate-{index}-width-{width}-degree-{degree}'
                        path=directory/(stem+'.json')
                        path.write_text(json.dumps(recipe,indent=2,allow_nan=False)+'\n')
                        if width_pixels is not None:
                            trial={'degree':degree,'recipe':str(path.relative_to(output))}
                            case.setdefault('extractions',[]).append(trial)
                            log=directory/(night+'-'+stem+'.log')
                            trial['log']=str(log.relative_to(output))
                            with log.open('w') as stream,redirect_stdout(stream),redirect_stderr(stream):
                                print(f'Observing date {night}; {obj["label"]}; width {width} spatial pixels; degree {degree}',flush=True)
                                try:
                                    result=reextract(run,product,recipe,directory/stem,render_report=False,failed=failed)
                                    trial.update(status='extracted_unverified',results=result['results'])
                                    plot_extraction(directory/stem,selected,obj,degree)
                                except Exception as exc:
                                    traceback.print_exc()
                                    trial.update(status='failed',error=str(exc),code=getattr(exc,'code',type(exc).__name__))
                except BackgroundSupportError as exc:
                    case.update(status='insufficient_two_sided_space',error=str(exc),diagnostics=exc.diagnostics)
                record['cases'].append(case)
        record['figures']={p.name:sha256(p) for p in directory.glob('FitQC_*.jpg')}
        summary['targets'].append(record)
        if (FailedExposure if failed else Exposure)(run,product).hashes!=exposure.hashes:
            raise ValueError('inputs changed during local-background trials')
        (output/'local-background.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('night');parser.add_argument('--targets',nargs='+',required=True)
    parser.add_argument('--project-root',type=Path,default=Path.cwd())
    parser.add_argument('--width-pixels',type=int,help='Explicit spatial width per side. Omit for geometry-only 30/40/50-pixel checks.')
    parser.add_argument('--degrees',nargs='+',type=int,choices=(1,2,3),default=[1,2])
    parser.add_argument('--minimum-width-pixels',type=int)
    parser.add_argument('--padding-pixels',type=int,default=0)
    args=parser.parse_args()
    print(run_trials(args.night,args.targets,args.project_root,width_pixels=args.width_pixels,degrees=args.degrees,
                     minimum_width_pixels=args.minimum_width_pixels,padding_pixels=args.padding_pixels))


if __name__=='__main__':main()
