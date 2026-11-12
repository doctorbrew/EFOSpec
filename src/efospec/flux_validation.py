"""Flux diagnostics and isolated response trials, never scientific approval."""
import numpy as np

CONTINUUM_BANDS = ((4600,4800),(5100,5300),(5600,5800),(6000,6200),
                   (6600,6800),(7000,7100),(7800,8000),(8400,8600))


def transfer_summary(waveair, ratio, valid, continuum):
    """Separate multiplicative scale from colour; keep missing bands missing.

    Five samples and half-band support are diagnostic coverage requirements,
    not accuracy thresholds. No absolute calibration claim follows from these.
    """
    wave,ratio=np.asarray(waveair,float),np.asarray(ratio,float)
    valid=np.asarray(valid,bool)&np.asarray(continuum,bool)&np.isfinite(ratio)&(ratio>0)
    bands=[]
    for lo,hi in CONTINUUM_BANDS:
        domain=(wave>=lo)&(wave<hi); m=domain&valid
        covered=int(m.sum())>=5 and m.sum()>=.5*domain.sum()
        bands.append(dict(band_air_angstrom=[lo,hi],samples=int(m.sum()),
            grid_samples=int(domain.sum()),median_ratio=float(np.median(ratio[m])) if covered else None))
    values=np.array([b['median_ratio'] for b in bands if b['median_ratio'] is not None])
    grey=float(np.median(values)) if len(values)>=2 else None
    return dict(continuum_bands=bands,grey_ratio=grey,
        maximum_shape_departure_fraction=float(np.max(abs(values/grey-1))) if grey else None,
        absolute_accuracy_validated=False,
        interpretation='Equal-weight continuum-band medians; grey scale and residual colour are diagnostics, not slit-loss corrections.')


def paired_zeropoint(wave, free, free_valid, filtered_wave, filtered, filtered_valid):
    """Experimental Gr13 response splice in *additive* zeropoint magnitudes.

    Inputs use vacuum Å. Anchor/blend is 5400--5600 vacuum Å near the published
    5500 Å splice. Assumes a grey filter throughput there; this is an explicit
    trial assumption to test on other pairs, not a calibrated filter model.
    """
    wave,filtered_wave=np.asarray(wave,float),np.asarray(filtered_wave,float)
    free,filtered=np.asarray(free,float),np.asarray(filtered,float)
    free_valid,filtered_valid=np.asarray(free_valid,bool),np.asarray(filtered_valid,bool)
    for w,z,g in ((wave,free,free_valid),(filtered_wave,filtered,filtered_valid)):
        if w.ndim!=1 or w.size<2 or z.shape!=w.shape or g.shape!=w.shape or not np.isfinite(w).all() or not np.all(np.diff(w)>0):
            raise ValueError('response trial requires increasing finite matching grids')
    free_valid=free_valid&np.isfinite(free)
    filtered_valid=filtered_valid&np.isfinite(filtered)
    interp=np.interp(wave,filtered_wave,filtered,left=np.nan,right=np.nan)
    support=np.interp(wave,filtered_wave,filtered_valid.astype(float),left=0.,right=0.)>=1.-1e-9
    anchor=(wave>=5400)&(wave<=5600)&free_valid&support
    if anchor.sum()<10 or np.ptp(wave[anchor])<150:
        raise ValueError('insufficient common response anchor support')
    offset=float(np.median(free[anchor]-interp[anchor]))
    weight=np.clip((wave-5400)/200,0,1)
    valid=np.where(weight==0,free_valid,np.where(weight==1,support,free_valid&support))
    merged=np.full(wave.shape,np.nan)
    blue=valid&(weight==0);red=valid&(weight==1);blend=valid&(weight>0)&(weight<1)
    merged[blue]=free[blue];merged[red]=interp[red]+offset
    merged[blend]=(1-weight[blend])*free[blend]+weight[blend]*(interp[blend]+offset)
    return merged,valid,dict(anchor_vacuum_angstrom=[5400,5600],offset_mag=offset,
        anchor_residual_scatter_mag=float(1.4826*np.median(abs(free[anchor]-interp[anchor]-offset))),
        science_second_order_removed=False,approved_for_science=False,
        assumption='Grey filtered/unfiltered throughput near anchor; no red extrapolation or science-order decontamination.')
