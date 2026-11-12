"""Read-only presentation of the background and response evidence actually saved."""
from html import escape
from pathlib import Path

from .naming import source_order


def _number(value, precision=3):
    if value is None:return '—'
    return escape(f'{value:.{precision}g}' if isinstance(value,(int,float)) else str(value))


def background_evidence(run):
    from .epoch_report import _table
    records = [(r, 'Flux product') for r in run.get('results', [])]
    records += [(r, 'Review counts') for r in run.get('review_counts', [])]
    rows=[]
    for item, kind in sorted(records,key=lambda pair:source_order(pair[0])):
        processing=item.get('processing', {})
        fit=processing.get('background_fit') or item.get('background') or {}
        setup=item.get('setup', {})
        selection=fit.get('selection', {})
        automatic=selection.get('automatic_background_selection', {})
        width=selection.get('actual_width_spatial_pixels',automatic.get('selected_width_spatial_pixels'))
        status=('Fit converged' if fit.get('pypeit_exit_status')==0 else
                'Fit did not converge' if fit.get('pypeit_exit_status') is not None else
                'Fit recorded; convergence unspecified' if fit else 'Background evidence unavailable')
        if fit.get('pypeit_exit_status') not in (0,None) or not fit:
            status='<span class="qc-status-bad">'+status+'</span>'
        geometry=('Default retained; comparison unavailable' if automatic.get('geometry_unresolved') is True else
                  'Compared using withheld pixels' if automatic.get('geometry_unresolved') is False else 'Not recorded')
        rows.append([escape(item.get('object','Unknown')),escape(item.get('grism',setup.get('grism',''))),kind,
            status,_number(fit.get('spatial_degree')),_number(width),_number(fit.get('minimum_side_samples')),
            len(fit['invalid_rows']) if 'invalid_rows' in fit else '—',_number(fit.get('reduced_chi2')),geometry])
    content='<h3>Backgrounds used in this reduction</h3>'
    if rows:
        content += ('<p>Saved extraction records include the background fit, spatial degree, retained samples and masked rows. '
                    'Separate manual polynomial experiments are optional.</p>'
                    +_table(['Target','Grism','Product','Fit status','Spatial degree','Band width (px/side)',
                             'Minimum accepted samples/side','Masked rows','Reduced χ²','Geometry comparison'],rows))
        content += ('<p class="caption">“Default retained” means the fit could not compare alternative geometries using a clean withheld ring. '
                    'Background subtraction was still performed where the fit is recorded. Convergence alone does not establish host removal '
                    'or target identity; fixed-sky extraction does not propagate background-model covariance.</p>')
    else:
        content += '<p>No extracted products with background evidence are recorded in this revision.</p>'
    failures=[e for e in run.get('errors',[]) if e.get('code')=='background_support_required']
    if failures:
        content += '<p class="qc-status-bad">'+str(len(failures))+' exposures remain blocked by background checks; see Issues for their recorded reasons.</p>'
    return content


def response_status(fit):
    """Separate successful construction from unfinished scientific validation."""
    if fit.get('status')=='response_built_unvalidated' and fit.get('response'):
        return 'Response built · <span class="qc-status-bad">absolute accuracy unvalidated</span>'
    status=str(fit.get('status','unknown')).replace('_',' ')
    return '<span class="qc-status-bad">'+escape(status)+'</span>'


def calibration_overview(run):
    from .epoch_report import _table
    standards=run.get('standards',[])
    responses=[s for s in standards if s.get('fit',{}).get('response')]
    science=[r for r in run.get('results',[]) if r.get('role')=='science']
    content='<h3>Same-night standard responses</h3>'
    content += (f'<p>{len(responses)} response functions recorded from {len(standards)} standard extractions; '
                f'{len(science)} science flux products delivered. Response files and their exposure associations are listed below.</p>')
    # Report successful operations separately from the limits recorded by the reducer.
    if science:
        steps=[]
        for key,label in [('bias','Bias subtraction'),('flat','Flat-field correction'),('cosmic_ray_premask','Cosmic-ray premasking')]:
            done=sum(r.get('processing',{}).get(key) is True for r in science)
            steps.append([label,f'{done}/{len(science)} science products recorded as applied'])
        content+=_table(['Processing step','Saved evidence'],steps)
    content+='<details><summary>Flux-calibration scope and remaining validation</summary>'
    if run.get('independent_flux_validation') is True:
        content+='<p>Independent flux validation is recorded in this run.</p>'
    else:
        content+='<p class="qc-status-bad">Independent absolute accuracy unvalidated.</p>'
    limits=run.get('limitations',[])
    if limits:
        content+='<ul>'+''.join('<li>'+escape(str(note))+'</li>' for note in limits)+'</ul>'
    else:
        content+='<p>No correction-scope record is available in this manifest.</p>'
    content+='</details>'
    errors=run.get('held_out_errors',[])
    if errors:
        content+='<h3>Failed response-transfer checks</h3>'+_table(['Response exposure','Test exposure','Failure'],[
            [escape(Path(e.get('training_raw','')).name),escape(Path(e.get('test_raw','')).name),escape(e.get('error','Unspecified'))]
            for e in errors])
    return content
