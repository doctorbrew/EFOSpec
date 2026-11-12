"""Shared before-subtraction spatial profiles for successful and review spectra."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb, to_hex
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from .figure_style import house_style, style, plain_tex
from .spatial_profiles import wavelength_binned_profiles
from .profile_limits import _profile_limit_samples, _profile_limits
set_plotparams = style.set_plotparams
styled_legend = style.styled_legend
TICK_LABEL_PT = 18
PYPEIT_COLOUR = to_hex(.6*np.array(to_rgb('xkcd:red'))+.4)
BACKGROUND_COLOUR = 'xkcd:pastel blue'


def _observed_profile_limits(profiles, *, background=None):
    """Pad the local range; include zero only for a near-zero background."""
    values=np.concatenate(profiles)
    values=values[np.isfinite(values)]
    if not values.size:return None
    low,high=float(values.min()),float(values.max())
    samples=values if background is None else np.asarray(background)
    samples=samples[np.isfinite(samples)]
    if not samples.size:samples=values
    median=float(np.median(samples))
    scatter=1.4826*float(np.median(np.abs(samples-median))) if samples.size>=5 else 0.
    near_zero=abs(median)<=3*scatter
    scale=high-low or max(abs(low),abs(high)) or 1.
    lower=low-.1*scale
    if near_zero:
        lower=min(0.,low)-.1*scale
    elif low>0:
        # A bright source must not pull a positive background down to zero.
        lower=max(lower,.9*low)
    return lower, high+.15*(abs(high) or scale)


def _candidate_centroid(candidate, data, bounds, *, last):
    """Use the candidate's own tilted wavelength map, in the displayed frame."""
    trace = np.asarray(candidate['trace'], float)
    if trace.shape != (len(data['data']),) or not np.isfinite(trace).all():
        raise ValueError('candidate trace must be finite for every spectral row')
    local = trace-data['spatial_origin']
    x = np.arange(data['data'].shape[1])
    wave = np.array([np.interp(t, x, w) for t, w in zip(local, data['waveair'])])
    lo, hi = bounds
    rows = (wave >= lo) & ((wave <= hi) if last else (wave < hi))
    return float(np.median(trace[rows])) if rows.any() else None


@house_style
def draw_spatial_profiles(result, wave, data, *, display=None):
    display = display or {}
    model_available = data.get('model_available', True)
    show_aperture = data.get('show_aperture', True)
    show_trace = data.get('show_trace', True)
    display_label = plain_tex(result['object'])
    grism_label = plain_tex(result['grism'])
    # Equal wavelength intervals over the same calibrated range as the spectrum.
    profiles = wavelength_binned_profiles(data, np.linspace(wave[0], wave[-1], 4),
                                          data['box_radius'])
    fig, model_axes = plt.subplots(3, 1, figsize=(13, 13), sharex=True)
    # Removing the explanatory paragraph frees the band under the legend.
    fig.subplots_adjust(left=0.12, right=0.985, bottom=0.08, top=0.79, hspace=0.27)
    fig.suptitle(rf"{display_label} (EFOSC2 / {grism_label} $\cdot$ {result['exptime_s']:.0f}\,s)",
                 x=0.53, y=0.985, fontsize=20)
    degree = data.get('sky_spatial_degree', result.get('processing', {}).get('background_fit', {}).get('spatial_degree'))
    model_label = data.get('sky_label', 'Saved PypeIt sky') + (f' (spatial degree {int(degree)})' if degree is not None else '')
    model_axes[0].set_title('Before Subtraction: Observed data and fitted background' if model_available
                            else 'Before Subtraction: Observed data (no accepted background)', pad=16)
    # Display provenance stays in the saved diagnostics and the report caption;
    # the figure itself carries no explanatory paragraphs.
    trace_colour = data.get('trace_colour', '0.3')
    for bin_index, (model_ax, profile) in enumerate(zip(model_axes, profiles)):
        ax = model_ax
        if not show_aperture: profile['aperture_fraction'][:] = 0.
        if not model_available: profile['background_fraction'][:] = 0.
        x = profile['spatial_pixel']
        y = profile['summed_electrons']/1000.
        # Opacity is the fraction selected within each wavelength bin; this
        # retains curved aperture edges and wavelength-dependent sky selection.
        for fractions, colour, alpha in (
                (profile['background_fraction'], BACKGROUND_COLOUR, 0.32),
                (profile['aperture_fraction'], PYPEIT_COLOUR, 0.22)):
            overlay = np.zeros((1, len(x), 4))
            overlay[:, :, :3] = to_rgb(colour)
            overlay[:, :, 3] = alpha*fractions
            for panel in (model_ax,):
                panel.imshow(overlay, extent=(x[0]-0.5, x[-1]+0.5, 0., 1.),
                      transform=panel.get_xaxis_transform(), origin='lower', aspect='auto',
                      interpolation='nearest', rasterized=True, zorder=0)
        raw = profile['summed_data_electrons']/1000.
        fitted = profile['summed_sky_electrons']/1000.
        supported = profile['sky_model_supported']
        model_ax.plot(x, raw, color='0.3', linewidth=1.3, zorder=3)
        if model_available:
            model_ax.plot(x, np.where(supported, fitted, np.nan), color='xkcd:dark blue',
                          linestyle='--', linewidth=2., zorder=4)
        if show_trace:
            model_ax.axvline(profile['median_trace_pixel'], color=trace_colour, linestyle='--', linewidth=1.2)
            if data.get('selected_label'):
                model_ax.text(profile['median_trace_pixel']+1, .035, data['selected_label'],
                    transform=model_ax.get_xaxis_transform(), color=trace_colour, fontsize=18,
                    ha='left', va='bottom', zorder=6)
        centroids = []
        for candidate in data.get('candidate_traces', []):
            position = _candidate_centroid(candidate, data, profile['wavelength_air_angstrom'],
                                           last=bin_index==len(profiles)-1)
            centroids.append(dict(label=candidate['label'], spatial_pixel=position,
                                  note=candidate.get('note'), source_label=candidate.get('source_label',candidate['label'])))
            if position is None or candidate['label']==data.get('selected_label'): continue
            colour = candidate.get('colour', '0.3')
            model_ax.axvline(position, color=colour, linestyle=':', linewidth=1.2)
            label = candidate['label']+('?' if candidate.get('note') else '')
            model_ax.text(position+1,.035,label,transform=model_ax.get_xaxis_transform(),
                          color=colour,fontsize=16,va='bottom')
        profile['candidate_centroids'] = centroids
        protected = profile['aperture_fraction'] > 0
        for candidate in data.get('candidate_traces', []):
            t=np.asarray(candidate['trace'])
            protected |= (x>=np.min(t)-3)&(x<=np.max(t)+3)
        annotations = []
        for candidate in display.get('profile_candidates',[]):
            lo,hi = candidate['search_interval']
            region = (x >= lo) & (x < hi)
            protected |= region
            usable = np.flatnonzero(region & np.isfinite(y))
            if not len(usable):
                raise ValueError('requested profile candidate has no finite samples')
            peak = usable[np.argmax(y[usable])]
            position = float(x[peak])
            ax.axvline(position,color='xkcd:dodger blue',linestyle=':',linewidth=1.2)
            ax.text(position+1,.035,candidate['label'],transform=ax.get_xaxis_transform(),
                    color='xkcd:dodger blue',fontsize=16,va='bottom')
            annotations.append(dict(label=candidate['label'],spatial_pixel=position,
                method='maximum within user-identified profile interval; not a fitted trace',
                search_interval=list(candidate['search_interval']),identity_confirmed=False))
        limit_values, excluded = _profile_limit_samples(y,protected,spatial_pixel=x,
            exclude_ranges=display.get('ylim_exclude_intervals',[]),edge_margin=data.get('limit_edge_margin',0))
        _, automatic_excluded = _profile_limit_samples(y,protected,spatial_pixel=x)
        background_columns=np.flatnonzero(profile['background_fraction']>0)
        background_span=None
        outside=np.zeros(len(x),bool)
        if display.get('limits_within_background_and_candidates'):
            if len(background_columns)<2:
                raise ValueError('profile limits need two-sided background coverage')
            background_span=[float(x[background_columns[0]]),float(x[background_columns[-1]])]
            outside=(x<background_span[0])|(x>background_span[1])
            # Keep the neighbour context, but do not let distant polynomial
            # extrapolation dominate a local source/background diagnostic.
            unsupported=outside & ~protected
            limit_values[unsupported]=np.nan
            excluded |= unsupported & np.isfinite(y)
            for candidate in annotations:
                candidate['background_extrapolated']=not background_span[0]<=candidate['spatial_pixel']<=background_span[1]
        limits = _profile_limits([limit_values],background_subtracted=True)
        retained=np.isfinite(limit_values)
        baseline=retained & (profile['background_fraction']>0) & ~protected
        if not baseline.any():baseline=retained & ~protected
        raw_limits = _observed_profile_limits([np.where(retained, raw, np.nan),
                                     np.where(supported & model_available, fitted, np.nan)],
                                     background=raw[baseline])
        if raw_limits is not None:model_ax.set_ylim(*raw_limits)
        profile.update(ylim=list(limits) if limits is not None else None,ylim_excluded_spatial_pixels=x[excluded].tolist(),
                       data_model_ylim=list(model_ax.get_ylim()),
                       automatic_spike_excluded_spatial_pixels=x[automatic_excluded].tolist(),
                       candidate_annotations=annotations,background_interpolation_span=background_span)
        lo, hi = profile['wavelength_air_angstrom']
        model_ax.text(.025, .93, rf'{lo:.0f}--{hi:.0f} $\AA$', transform=model_ax.transAxes,
                      fontsize=20, va='top')
        model_ax.set_xlim(x[0]-.5, x[-1]+.5)
        spacing=max(20.,10.*np.ceil((x[-1]-x[0])/100.))
        set_plotparams(model_ax, xticks=(spacing, spacing/4), yticks=None, fs=TICK_LABEL_PT)
        model_ax.set_ylabel(r'Summed signal [$10^3\,\mathrm{e}^{-}$]', labelpad=13)
        model_ax.tick_params(axis='x', labelbottom=True)
    model_axes[-1].set_xlabel(data.get('spatial_label', r'Spatial pixel (raw $-99$)'), labelpad=10)
    handles=[Line2D([], [], color='0.3', linewidth=1.3, label='Observed Data')]
    if model_available:
        handles.append(Line2D([], [], color='xkcd:dark blue', linestyle='--', linewidth=2., label=model_label))
    if show_trace:
        handles.append(Line2D([], [], color=trace_colour, linestyle='--', linewidth=1.2, label='Trace centre'))
    if any(c['label']!=data.get('selected_label') and c.get('colour', '0.3')=='0.3'
           for c in data.get('candidate_traces', [])):
        handles.append(Line2D([], [], color='0.3', linestyle=':', linewidth=1.2, label='Other candidate traces'))
    if show_aperture:
        handles.append(Patch(facecolor=PYPEIT_COLOUR, alpha=.22, label=data.get('aperture_label', 'Boxcar aperture')))
    if model_available:
        handles.append(Patch(facecolor=BACKGROUND_COLOUR, alpha=.32, label=data.get('bands_label', 'Background Sampling')))
    if data.get('supplemental_traces'):
        handles.append(Line2D([], [], color='xkcd:dodger blue', linestyle=':', linewidth=1.2,
                              label='Neighbour trace'))
    styled_legend(model_axes[0], handles=handles, loc='center', bbox_to_anchor=(.53,.91),
                  bbox_transform=fig.transFigure, ncol=2, borderpad=.55)
    diagnostics = {
        'display_settings':display, 'layout':'three wavelength panels; before subtraction only',
        'model_available':model_available, 'sky_subtracted':False,
        'data_model_ylim_rule':'10% local-span lower padding; positive minima stay at or above 90% of their value unless the background median is within 3 MAD-sigma of zero; retain negative data; 15% headroom above retained peak; only plotted models contribute; display exclusions unchanged',
        'ylim_rule':'QC limits: exclude isolated negative outliers and positive peaks with >20 MAD-sigma prominence, half-prominence width <=2 pixels and <=3-column >10-sigma core outside protected sources; explicit display exclusions also apply; include zero and pad outward',
        'display_only':True,'all_profile_samples_plotted':True,
        'binning': 'three equal air-wavelength intervals over the displayed spectrum range',
        'signal': 'sum of finite on-slit native data, in electrons; saved sky overlaid where available',
        'sky_model': {'source':'saved extraction sky image; no new fit' if model_available else 'unavailable; no model invented',
                      'spatial_degree':int(degree) if degree is not None else None,
                      'summation':'data, model and residual use identical detector pixels in each bin',
                      'display_support':'model drawn only inside the common saved sky-band envelope; no extrapolation drawn'},
        'excluded_spatial_columns': [int(data['spatial_origin']),
                                     int(data['spatial_origin'])+data['data'].shape[1]-1],
        'exclusion_reason': 'two off-slit boundary columns have no fitted sky model',
        'spatial_coordinates': 'zero-based legacy-trimmed detector pixels',
        'box_radius_pixels': data['box_radius'],
        'aperture': 'geometric boxcar aperture from native BOX_RADIUS and TRACE_SPAT; not optimal weights',
        'shading': 'opacity proportional to selection fraction in each wavelength bin',
        'sky_mask_stage': 'global_sky_input_before_iterative_rejection',
        'bins': [{key: np.where(np.isfinite(value), value, None).tolist()
                  if isinstance(value, np.ndarray) else value
                  for key, value in profile.items()} for profile in profiles],
    }
    return fig, diagnostics


def draw_review_profiles(images, result, *, spatial_origin=0, traces=None, background=None,
                         selection=None, candidate_notes=None, supplemental_traces=(),
                         hidden_candidates=(), candidate_labels=None, candidate_evidence=None,
                         spatial_label='Spatial pixel (saved window)'):
    """Show explicit review geometry without accepting an extraction or sky fit."""
    data=np.asarray(images['data'])
    traces=list(images.get('found_traces', [])) if traces is None else list(traces)
    stage=str(images.get('sky_mask_stage',''))
    mask=np.asarray(images.get('sky_input_mask',np.zeros_like(data,dtype=bool)))
    if background is not None:mask=background.get('input_mask',mask)
    available=background is not None or (not stage.startswith('source_finding_only_no_') and mask.any())
    sky=(data-background['residual'] if background else images.get('sky',np.zeros_like(data)))
    if background is not None:sky=background.get('sky',sky)
    trace=np.asarray(traces[0]) if traces else np.full(len(data),(data.shape[1]-1)/2)
    # Without an operator selection this only defines wavelength-bin coverage.
    prepared=dict(images, data=data, sky=sky if available else np.zeros_like(data),
        trace=trace,spatial_origin=spatial_origin,box_radius=1.,sky_input_mask=mask,
        model_available=bool(available),show_aperture=False,show_trace=False,spatial_label=spatial_label,
        limit_edge_margin=3,
        candidate_traces=[dict(label=f'C{i+1}',trace=np.asarray(t)+spatial_origin) for i,t in enumerate(traces)])
    if selection is not None:
        candidate = selection['candidate']
        radius = float(selection['radius_pixels'])
        if isinstance(candidate, bool) or not isinstance(candidate, int) or not 1 <= candidate <= len(traces):
            raise ValueError('review candidate must identify a saved trace')
        if not np.isfinite(radius) or not 0 < radius < data.shape[1]/2:
            raise ValueError('review aperture radius must be finite, positive and inside the saved window')
        if not selection.get('radius_source') or not selection.get('method'):
            raise ValueError('review aperture needs radius provenance and selection method')
        prepared.update(trace=np.asarray(traces[candidate-1]), box_radius=radius,
            show_aperture=True, show_trace=True, selected_label=f'C{candidate}', trace_colour='xkcd:red',
            aperture_label='Adopted Aperture',
            sky_label='PypeIt sky', bands_label='Background Sampling')
    notes = candidate_notes or {}
    labels = candidate_labels or {}
    original_labels = {c['label'] for c in prepared['candidate_traces']}
    if not set(hidden_candidates) <= original_labels:
        raise ValueError('hidden candidate must identify a saved trace')
    if prepared.get('selected_label') in hidden_candidates:
        raise ValueError('cannot hide the selected aperture')
    prepared['candidate_traces'] = [c for c in prepared['candidate_traces'] if c['label'] not in hidden_candidates]
    for candidate in prepared['candidate_traces']:
        candidate['note'] = notes.get(candidate['label'])
    for candidate in supplemental_traces:
        prepared['candidate_traces'].append(dict(candidate, trace=np.asarray(candidate['trace'])+spatial_origin,
                                                 colour='xkcd:dodger blue'))
    # A stored polynomial path is a proposal, not evidence of a source. Apply
    # the measured decisions to every candidate, including old review packets.
    # Bind saved decisions by name AND trace, since callers can reorder traces.
    checks = dict(candidate_evidence or {})
    recorded_evidence = images.get('candidate_evidence_json')
    if candidate_evidence is None and recorded_evidence is not None:
        import json
        saved_checks = json.loads(str(recorded_evidence))
        originals = list(zip(images.get('found_names', []), images.get('found_traces', [])))
        for i, t in enumerate(traces):
            matches = [str(name) for name, original in originals if np.array_equal(t, original)]
            if len(matches)==1 and matches[0] in saved_checks:
                checks[f'C{i+1}'] = saved_checks[matches[0]]
    validation_hidden = []
    validated_display = selection is not None or candidate_evidence is not None or recorded_evidence is not None
    if validated_display:
        retained = []
        for candidate in prepared['candidate_traces']:
            label = candidate['label']
            if label==prepared.get('selected_label') or checks.get(label, {}).get('accepted') is True:
                retained.append(candidate)
            else:
                validation_hidden.append(label)
        prepared['candidate_traces'] = retained
    prepared['supplemental_traces'] = any(c.get('colour')=='xkcd:dodger blue' for c in prepared['candidate_traces'])
    # Number the visible, validated apertures from left to right. In particular,
    # a lone retained aperture is C1 even if its historical proposal was C2/C3.
    # The selection, evidence keys and original arrays remain in their old IDs.
    display_labels = ({c['label']:f'C{i+1}' for i,c in enumerate(sorted(
        prepared['candidate_traces'],key=lambda c:float(np.median(c['trace']))))}
        if validated_display else dict(labels))
    for candidate in prepared['candidate_traces']:
        candidate['source_label'] = candidate['label']
        candidate['label'] = display_labels.get(candidate['label'], candidate['label'])
    if len({c['label'] for c in prepared['candidate_traces']}) != len(prepared['candidate_traces']):
        raise ValueError('display candidate labels must be distinct')
    if prepared.get('selected_label'):
        prepared['selected_label'] = display_labels.get(prepared['selected_label'], prepared['selected_label'])
    columns=np.arange(data.shape[1])
    if background is not None:
        prepared['sky_valid_rows']=background['valid_rows']
        if 'accepted_mask' in background:prepared['sky_accepted_mask']=background['accepted_mask']
        if 'spatial_degree' in background:prepared['sky_spatial_degree']=background['spatial_degree']
    prepared['onslit']=np.broadcast_to((columns>0)&(columns<data.shape[1]-1),data.shape)
    wave=np.asarray(images['waveair'])[:,data.shape[1]//2]
    fig,record=draw_spatial_profiles(result,wave,prepared)
    record.update(profile_statistic='sum of native data in three wavelength intervals; saved sky overlaid where available',
                  background_source=background.get('provenance') if background else None,
                  selection=selection, candidate_notes=notes, extraction_accepted=False,
                  hidden_candidates=list(hidden_candidates), candidate_labels=labels,
                  display_label_map=display_labels, selected_display_label=prepared.get('selected_label'),
                  label_policy='consecutive visible apertures ordered by spatial position; original IDs retained in provenance' if validated_display else 'historical candidate IDs',
                  candidate_evidence=checks, validation_hidden_candidates=validation_hidden,
                  candidate_display_policy='reviewed profiles require positive validation for every non-selected trace; explicit operator aperture retained',
                  sky_mask_stage=stage, spatial_coordinates=spatial_label,
                  aperture='review geometry only; '+selection['radius_source'] if selection else 'none selected')
    return fig,record


@house_style
def save_review_profile(fig, output, object_name):
    import re
    from pathlib import Path
    safe=re.sub(r'[^A-Za-z0-9.+-]','_',object_name)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    style.savefig_light(fig,output/f'FitQC_{safe}_profiles',dpi_pdf=300,dpi_jpg=300)
    fig.savefig(output/'profiles.png',dpi=150,bbox_inches='tight')
