"""Fit and validate one night's standard-star telluric models in a new revision."""
from .native_sky import wavelength_accepted
import json
from pathlib import Path
import numpy as np
from astropy import units as u

from .inventory import sha256
from .native_calibration import save_json
from .telluric_model import Atmosphere, fit_standard, predict, BANDS, continuum_basis, correct_flux


def read_config(path):
    from ast import literal_eval
    from configobj import ConfigObj
    from pypeit.par.pypeitpar import TelluricPar
    cfg=ConfigObj(str(path))
    if set(cfg)!={'telluric'}:raise ValueError('expected only a telluric configuration section')
    def parse(x):
        if isinstance(x,list):return [parse(v) for v in x]
        try:return literal_eval(x)
        except (ValueError,SyntaxError):return x
    values={k:parse(v) for k,v in cfg['telluric'].items()}
    if 'resln_frac_bounds' in values:values['resln_frac_bounds']=tuple(values['resln_frac_bounds'])
    par=TelluricPar.from_dict(values)  # Reject obsolete/unknown PypeIt keys.
    allowed={'teltype','telgridfile','objmodel','polyorder','fit_wv_min_max','resln_guess',
             'resln_frac_bounds','tell_npca','sn_clip','seed'}
    if set(values)-allowed:raise ValueError('unsupported options in the EFOSpec fitting wrapper: '+str(set(values)-allowed))
    if par['teltype']!='pca' or par['objmodel']!='star':raise ValueError('nightly transfer requires the PCA + physical-standard model')
    if not 100<=par['resln_guess']<=5000:raise ValueError('resln_guess is resolving power, not FWHM in Angstrom')
    if not 0<=par['polyorder']<=3:raise ValueError('standard continuum degree must be between zero and three')
    if len(par['fit_wv_min_max'])!=2 or not 5800<=par['fit_wv_min_max'][0]<par['fit_wv_min_max'][1]<=9500:
        raise ValueError('this optical transfer workflow requires a range within 5800--9500 vacuum Angstrom')
    return {k:par[k] for k in allowed}


def load_standard(entry,cache):
    from pypeit.specobjs import SpecObjs
    from pypeit.core import flux_calib
    from .native_acceptance import standard_recovery
    from .standard_reference import standard_reference
    frame,counts,response=entry['frame'],entry['counts'],entry['fit']['response']
    for path,digest in {**counts['product_sha256'],frame['path']:frame['sha256'],
                        response['path']:response['sha256']}.items():
        if sha256(Path(path))!=digest:raise ValueError('telluric input hash mismatch: '+path)
    obj=SpecObjs.from_fitsfile(counts['native_spec1d'])[0]
    reference=standard_reference(frame,cache)
    if sha256(Path(reference['cal_file']))!=sha256(Path(response['reference_file'])):
        raise ValueError('standard physical reference differs from recorded response')
    _,data=standard_recovery(frame,obj,response['path'],reference)
    sigma=np.divide(abs(data['ratio']),abs(obj.OPT_COUNTS)*np.sqrt(np.maximum(obj.OPT_COUNTS_IVAR,0)),
        out=np.full(len(obj.OPT_WAVE),np.nan),where=(obj.OPT_COUNTS>0)&(obj.OPT_COUNTS_IVAR>0))
    bad,stellar,_=flux_calib.get_mask(obj.OPT_WAVE,obj.OPT_COUNTS,obj.OPT_COUNTS_IVAR,
        data['valid'],mask_helium_lines=True,mask_telluric=False,hydrogen_mask_wid=40.)
    return dict(wave=np.asarray(obj.OPT_WAVE),ratio=data['ratio'],sigma=sigma,valid=bad&stellar)


def test_continuum(atmosphere,data):
    """Fit the held-out star's nuisance continuum using no atmospheric-band data."""
    from pypeit.core.wave import vactoair
    w=data['wave'];air=vactoair(w*u.AA).value
    use=(w>=atmosphere.lower)&(w<=atmosphere.upper)
    good=data['valid']&use&np.isfinite(data['ratio'])&(data['ratio']>0)&(data['sigma']>0)
    for lo,hi in list(BANDS.values())+[(6200,6400)]:good&=~((air>=lo-30)&(air<=hi+30))
    if good.sum()<40:raise ValueError('insufficient independent continuum for transfer validation')
    b=continuum_basis(w,atmosphere.lower,atmosphere.upper,3)
    weight=np.minimum(data['ratio'][good]/data['sigma'][good],30.)
    coeff=np.linalg.lstsq(b[good]*weight[:,None],np.log(data['ratio'][good])*weight,rcond=None)[0]
    return np.exp(b@coeff)


def validate_transfer(atmosphere,train,data,*,airmass_scale,return_arrays=False):
    """No atmospheric parameters are fitted to this held-out exposure."""
    from pypeit.core.wave import vactoair
    w=data['wave'];use=(w>=atmosphere.lower)&(w<=atmosphere.upper)
    air=vactoair(w[use]*u.AA).value
    cont=test_continuum(atmosphere,data)[use]
    ratio=data['ratio'][use]/cont
    t,tvar=predict(atmosphere,w[use],train,airmass_scale=airmass_scale)
    good=data['valid'][use]&np.isfinite(ratio)&(t>=.2)
    rows={}
    for name,(lo,hi) in BANDS.items():
        domain=(air>=lo)&(air<=hi);m=domain&good
        covered=m.sum()>=12 and m.sum()>=.7*domain.sum() and np.ptp(air[m])>=.8*(hi-lo) if m.any() else False
        if not covered:
            rows[name]=dict(status='insufficient_coverage',passed=False,samples=int(m.sum()));continue
        before=ratio[m]-1;after=ratio[m]/t[m]-1
        rms_before=float(np.sqrt(np.mean(before**2)));rms=float(np.sqrt(np.mean(after**2)))
        median=float(np.median(after))
        passed=abs(median)<=.05 and rms<=.10 and rms<=max(.8*rms_before,.02)
        rows[name]=dict(passed=bool(passed),status='passed' if passed else 'failed',samples=int(m.sum()),
            rms_before=rms_before,rms_after=rms,median_residual_after=median,
            fractional_variance_floor=rms**2)
    if return_arrays:
        corrected,variance,valid,stat,model=correct_flux(ratio,(data['sigma'][use]/cont)**2,t,tvar,good)
        return rows,dict(wave_air=air,ratio=ratio,corrected=corrected,variance=variance,
            valid=valid,transmission=t,transmission_variance=tvar,
            statistical_variance=stat,model_variance=model,continuum=cont)
    return rows


def run_night(run_path,output,*,night,config,apply_science=False,review_extrapolation=False):
    from contextlib import redirect_stdout,redirect_stderr
    from .run_record import snapshot_sources
    from .daily_reduction import matches
    import pypeit,sys
    run_path=Path(run_path).resolve();run=json.loads(run_path.read_text())
    if run['night']!=night:raise ValueError('telluric revision must name the saved observing night')
    config=Path(config).resolve();par=read_config(config)
    if review_extrapolation and not apply_science:
        raise ValueError('--review-extrapolation requires --apply-science')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    (output/'telluric.par').write_bytes(config.read_bytes())
    report=dict(night=night,source_run=str(run_path),source_run_sha256=sha256(run_path),
        config=par,config_sha256=sha256(config),pypeit_version=pypeit.__version__,python=sys.executable,
        source_sha256=snapshot_sources(output),fits=[],fit_errors=[],transfers=[],products=[],skipped=[],
        status='running',independent_absolute_flux_validated=False,
        review_extrapolation_requested=review_extrapolation,
        thresholds=dict(maximum_band_median_residual=.05,maximum_band_rms=.10,
                        minimum_rms_improvement=.20,minimum_transmission=.2,maximum_age_hours=2.),
        limitations=['Experimental standard-to-science transfer; tests do not certify arbitrary time/airmass changes.',
            'PCA fit covariance and empirical transfer residuals propagate; continuum/reference errors are not fully known.',
            'One native pixel of shift uncertainty and 20 percent resolution uncertainty are added for science transfer.',
            'Corrected-pixel errors share atmospheric-model covariance; diagonal variances are not independent.',
            'No new slit-loss, second-order or absolute-flux correction.'])
    protected={str(run_path):sha256(run_path),str(config):sha256(config)};data_by_raw={};entries={}
    with (output/'execution.log').open('w') as stream,redirect_stdout(stream),redirect_stderr(stream):
        atmosphere=Atmosphere(par['telgridfile'],npca=par['tell_npca'],lower=par['fit_wv_min_max'][0],upper=par['fit_wv_min_max'][1])
        report['atmospheric_model']=dict(path=str(atmosphere.path),sha256=atmosphere.sha256)
        protected[str(atmosphere.path)]=atmosphere.sha256
        for entry in run['standards']:
            if entry['fit']['status']!='response_built_unvalidated':continue
            f=entry['frame'];raw=f['path'];entries[raw]=entry
            protected.update(entry['counts']['product_sha256']);protected[raw]=f['sha256']
            response=entry['fit']['response'];protected[response['path']]=response['sha256']
            protected[response['reference_file']]=sha256(Path(response['reference_file']))
            protected[response['extinction']['path']]=response['extinction']['sha256']
            try:
                data=load_standard(entry,output/'physical-references');data_by_raw[raw]=data
                fit,arrays=fit_standard(atmosphere,**data,resolution=par['resln_guess'],polyorder=par['polyorder'],
                    sn_clip=par['sn_clip'],seed=par['seed'],resolution_bounds=par['resln_frac_bounds'])
                fit.update(raw=raw,raw_sha256=f['sha256'],object=f['metadata']['OBJECT'],setup=f['setup'],
                    mjd=f['metadata']['MJD-OBS'],airmass=f['metadata']['ESO TEL AIRM START'],
                    fit_id=len(report['fits'])+1)
                np.savez_compressed(output/f'standard-{fit["fit_id"]}.npz',**arrays)
                fit['arrays']=f'standard-{fit["fit_id"]}.npz'
                fit['arrays_sha256']=sha256(output/fit['arrays'])
                report['fits'].append(fit)
            except ValueError as exc:report['fit_errors'].append(dict(raw=raw,error=str(exc)))
            save_json(output/'run.json',report)
        for train in report['fits']:
            for raw,data in data_by_raw.items():
                a,b=entries[train['raw']]['frame'],entries[raw]['frame']
                if a['sha256']==b['sha256'] or not matches(a,b):continue
                try:
                    bands,arrays=validate_transfer(atmosphere,train,data,
                        airmass_scale=b['metadata']['ESO TEL AIRM START']/train['airmass'],return_arrays=True)
                    array_file=f'transfer-{len(report["transfers"])+1}.npz'
                    np.savez_compressed(output/array_file,**arrays)
                    report['transfers'].append(dict(training_raw=train['raw'],test_raw=raw,
                        arrays=array_file,arrays_sha256=sha256(output/array_file),
                        test_airmass=b['metadata']['ESO TEL AIRM START'],
                        independent_exposure=True,independent_star=a['metadata']['OBJECT']!=b['metadata']['OBJECT'],
                        time_hours=abs(b['metadata']['MJD-OBS']-train['mjd'])*24,
                        delta_airmass=abs(b['metadata']['ESO TEL AIRM START']-train['airmass']),bands=bands))
                except ValueError as exc:report['transfers'].append(dict(training_raw=train['raw'],test_raw=raw,error=str(exc)))
        save_json(output/'run.json',report)
        if apply_science:
            apply_products(run,report,entries,atmosphere,output,protected,review_extrapolation=review_extrapolation)
    if not all(sha256(Path(p))==h for p,h in protected.items()):raise ValueError('protected telluric input changed')
    save_json(output/'protected-inputs.json',protected)
    report.update(status='complete',protected_inputs_unchanged=True,protected_file_count=len(protected))
    save_json(output/'run.json',report)
    return report


def apply_products(run,report,entries,atmosphere,output,protected,*,review_extrapolation=False):
    import shutil
    from astropy.io import fits
    from pypeit.core.wave import airtovac
    from .daily_reduction import matches
    products=output/'products';products.mkdir()
    originals=output/'uncorrected';originals.mkdir()
    for item in run['results']:
        if item.get('role')!='science':continue
        source=Path(item['product']);protected[str(source)]=sha256(source)
        raw=item['raw']
        # The original raw header is authoritative for setup, time and airmass.
        from .inventory import inspect_file
        protected[raw]=item['raw_sha256']
        if sha256(Path(raw))!=protected[raw]:raise ValueError('science raw input changed')
        frame=inspect_file(Path(raw))
        if not wavelength_accepted(item.get('sky_flexure',{})):
            report['skipped'].append(dict(raw=raw,reason='Science wavelength validation required'));continue
        candidates=[f for f in report['fits'] if matches(frame,entries[f['raw']]['frame'])]
        candidates.sort(key=lambda f:abs(frame['metadata']['MJD-OBS']-f['mjd']))
        if not candidates:
            report['skipped'].append(dict(raw=raw,reason='No fitted standard with identical setup'));continue
        if len(candidates)>1 and np.isclose(abs(frame['metadata']['MJD-OBS']-candidates[0]['mjd']),
                abs(frame['metadata']['MJD-OBS']-candidates[1]['mjd']),rtol=0.,atol=1e-9):
            report['skipped'].append(dict(raw=raw,reason='Ambiguous nearest standard'));continue
        train=candidates[0];age=abs(frame['metadata']['MJD-OBS']-train['mjd'])*24
        checks=[v for v in report['transfers'] if v['training_raw']==train['raw']]
        delta_air=abs(frame['metadata']['ESO TEL AIRM START']-train['airmass'])
        qualified={name:max(c['bands'][name]['fractional_variance_floor'] for c in checks)
            for name in BANDS if checks and all(c.get('bands',{}).get(name,{}).get('passed',False) for c in checks)}
        tested_delta=max((c.get('delta_airmass',0.) for c in checks),default=0.)
        tested_air=[train['airmass']]+[c['test_airmass'] for c in checks if 'test_airmass' in c]
        air_range=[min(tested_air),max(tested_air)]
        science_airmass=frame['metadata']['ESO TEL AIRM START']
        air_review=not air_range[0]<=science_airmass<=air_range[1]
        time_review=age>2.
        extrapolation=air_review or time_review
        review_reasons=(['airmass outside tested range'] if air_review else [])+(['standard more than two hours away'] if time_review else [])
        reason=('No independently passing band' if not qualified else
                '; '.join(review_reasons) if extrapolation and not review_extrapolation else None)
        if reason:
            report['skipped'].append(dict(raw=raw,reason=reason,standard_raw=train['raw'],
                age_hours=age,delta_airmass=delta_air,maximum_tested_delta_airmass=tested_delta,
                tested_airmass_range=air_range,
                independently_passing_bands=list(qualified)));continue
        with fits.open(source) as hdus:
            if any(hdu.verify_checksum()!=1 or hdu.verify_datasum()!=1 for hdu in hdus):
                raise ValueError('science FITS checksum missing or invalid')
            h=hdus[0].header;data=hdus[0].data.copy()
            if h.get('WAVEMED')!='air' or data.shape[:2]!=(4,1):raise ValueError('unexpected science spectrum convention')
            if h.get('TELLURIC')=='PARTIAL':raise ValueError('source spectrum is already telluric corrected')
            air=h['CRVAL1']+(np.arange(data.shape[-1])+1-h.get('CRPIX1',1))*h['CD1_1'];vac=airtovac(air*u.AA).value
            use=(vac>=atmosphere.lower)&(vac<=atmosphere.upper)
            t=np.ones(air.size);tv=np.zeros(air.size);eligible=np.zeros(air.size,bool);affected=np.zeros(air.size,bool)
            # Science is on its accepted sky-corrected grid; do NOT copy the standard's raw-grid offset.
            pred,var,detail=predict(atmosphere,vac[use],train,shift=0.,return_details=True,
                airmass_scale=frame['metadata']['ESO TEL AIRM START']/train['airmass'],
                shift_sigma=float(np.median(np.diff(vac))),resolution_sigma=.2*train['resolution'])
            t[use]=pred;tv[use]=var
            for name,(lo,hi) in BANDS.items():
                band=(air>=lo)&(air<=hi);affected|=band
                if name in qualified:
                    eligible|=band&use;tv[band&use]+=t[band&use]**2*qualified[name]
            original_valid=hdus['VALID'].data[0].astype(bool)
            f,total,valid,stat,model=correct_flux(data[0,0],data[3,0]**2,t,tv,original_valid&eligible)
            applied=valid.copy();out=data.copy();out[0,0,affected]=np.nan;out[1,0,affected]=np.nan;out[3,0,affected]=np.nan
            out[0,0,applied]=f[applied];out[1,0,applied]=data[1,0,applied]/t[applied];out[3,0,applied]=np.sqrt(total[applied])
            final_valid=original_valid&(~affected|applied)
            stat[~affected]=data[3,0,~affected]**2;model[~affected]=0.
            copied=fits.HDUList([hdu.copy() for hdu in hdus]);copied[0].data=out
            copied['VALID'].data[0]=final_valid.astype(copied['VALID'].data.dtype)
            copied[0].header['TELLURIC']='PARTIAL';copied[0].header['TELSTD']=Path(train['raw']).name
            copied[0].header['TELMODEL']=atmosphere.sha256[:16]
            copied[0].header['TELFIT']=train['fit_id']
            copied[0].header['TELXSCL']=frame['metadata']['ESO TEL AIRM START']/train['airmass']
            copied[0].header['TELBANDS']=','.join(qualified)
            copied[0].header['TELVALID']='REVIEW' if extrapolation else 'TRANSFER'
            if extrapolation:
                copied[0].header['HISTORY']='REVIEW ONLY: '+'; '.join(review_reasons)+'.'
                copied[0].header['HISTORY']='Additional transfer error is not calibrated.'
            copied[0].header['HISTORY']='Telluric model and transfer variances added; unqualified atmospheric bands masked.'
            copied[0].header['HISTORY']='Sky diagnostic band retained uncorrected. Absolute flux remains unvalidated.'
            copied.append(fits.ImageHDU(data=data,name='UNCORRECTED'))
            copied.append(fits.ImageHDU(data=np.sqrt(stat),name='STAT_SIGMA'))
            copied.append(fits.ImageHDU(data=model,name='TELL_MODEL_VAR'))
            copied.append(fits.ImageHDU(data=detail['covariance'],name='TELL_PARAM_COV'))
            copied.append(fits.ImageHDU(data=detail['theta'],name='TELL_PARAMS'))
            # Together J and covariance recover correlated transmission errors;
            # the empirical transfer term remains a separate diagonal envelope.
            jacobian=np.zeros((air.size,len(detail['theta'])));jacobian[use]=detail['jacobian']
            copied.append(fits.ImageHDU(data=jacobian,name='TELL_JACOBIAN'))
            copied.append(fits.BinTableHDU.from_columns([
                fits.Column(name='WAVE_AIR',format='D',array=air),fits.Column(name='TRANSMISSION',format='D',array=t),
                fits.Column(name='TRANSMISSION_VARIANCE',format='D',array=tv),fits.Column(name='APPLIED',format='L',array=applied),
                fits.Column(name='ORIGINAL_VALID',format='L',array=original_valid)],name='TELLURIC'))
            destination=products/source.name;copied.writeto(destination,checksum=True)
            ascii_path=destination.with_suffix('.asci')
            np.savetxt(ascii_path,np.column_stack([air,out[0,0],out[3,0],final_valid,applied]),
                header='air_A flux_erg_s-1_cm-2_A-1 total_sigma valid telluric_applied\n'
                +'Telluric status: '+('REVIEW: '+'; '.join(review_reasons) if extrapolation else 'standard transfer checked'))
        original=originals/source.name;shutil.copyfile(source,original)
        original_ascii=original.with_suffix('.asci');source_ascii=source.with_suffix('.asci')
        if source_ascii.exists():
            protected[str(source_ascii)]=sha256(source_ascii);shutil.copyfile(source_ascii,original_ascii)
        else:
            np.savetxt(original_ascii,np.column_stack([air,data[0,0],data[3,0],original_valid]),
                header='air_A flux_erg_s-1_cm-2_A-1 statistical_sigma valid; derived from original FITS')
        report['products'].append(dict(raw=raw,source_product=str(source),source_sha256=protected[str(source)],
            raw_sha256=item['raw_sha256'],uncorrected_product=str(original),uncorrected_sha256=sha256(original),
            uncorrected_ascii=str(original_ascii),uncorrected_ascii_sha256=sha256(original_ascii),
            ascii=str(ascii_path),ascii_sha256=sha256(ascii_path),
            product=str(destination),sha256=sha256(destination),standard_raw=train['raw'],age_hours=age,
            delta_airmass=delta_air,bands=list(qualified),corrected_pixels=int(applied.sum()),
            maximum_tested_delta_airmass=tested_delta,tested_airmass_range=air_range,
            airmass_transfer_validated=not air_review,review_reasons=review_reasons,
            masked_atmospheric_pixels=int((original_valid&affected&~applied).sum()),
            status='review_required_transfer' if extrapolation else 'experimental_partial_telluric_correction',
            uncertainty_limit='Extrapolation model error is not calibrated' if extrapolation else
                'Empirical standard-transfer envelope; absolute flux remains unvalidated'))


def add_arguments(p):
    p.add_argument('night');p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--apply-science',action='store_true')
    p.add_argument('--review-extrapolation',action='store_true',
        help='Also retain time/airmass transfer review products; never replace accepted data')
    p.add_argument('--attach-to-report',action='store_true',help='Render both reductions in the source run plots and nightly report')


def execute(args):
    r=run_night(args.run,args.output,night=args.night,config=args.config,apply_science=args.apply_science,
        review_extrapolation=args.review_extrapolation)
    if getattr(args,'attach_to_report',False):
        from .telluric_products import select_for_report,render_selected
        select_for_report(Path(args.run).parent,Path(args.output)/'run.json')
        render_selected(Path(args.run).parent)
    print(json.dumps(dict(status=r['status'],fits=len(r['fits']),fit_errors=r['fit_errors'],products=len(r['products']),skipped=r['skipped'])))
    return 0


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);add_arguments(p)
    return execute(p.parse_args())


if __name__=='__main__':main()
