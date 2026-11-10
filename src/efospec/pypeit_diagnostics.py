"""PypeIt-readable diagnostic images, with explicit stage and window geometry."""
from pathlib import Path

import numpy as np


def write_spec2d(path, science, slits, wavevac, tilts, sky, *, arrays=None,
                 raw_origin=None, stage='source_review'):
    """Save actual image/variance/masks; distinguish absent object models.

This is the extraction window, not a newly calibrated full detector. Sky and
object models are zero only when that stage has not run, recorded in headers.
The original input inverse variance and extraction model variance stay distinct.
"""
    from pypeit.spec2dobj import Spec2DObj, AllSpec2DObj
    from pypeit import io
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    model=np.zeros_like(science.image) if arrays is None else arrays[1]
    variance=science.ivar if arrays is None else arrays[2]
    mask=science.fullmask if arrays is None else arrays[3]
    obj=Spec2DObj(sciimg=science.image,ivarraw=science.ivar,skymodel=sky,bkg_redux_skymodel=None,
        objmodel=model,ivarmodel=variance,
        scaleimg=np.ones_like(science.image) if science.img_scale is None else np.broadcast_to(science.img_scale,science.image.shape).copy(),
        waveimg=wavevac,bpmmask=mask,detector=science.detector,
        sci_spat_flexure=None,sci_spec_flexure=None,vel_type='observed',vel_corr=1.,
        slits=slits,wavesol=None,tilts=tilts,maskdef_designtab=None)
    product=AllSpec2DObj();product[obj.detname]=obj
    header=io.initialize_header()
    header['PYP_SPEC']='ntt_efosc2_epessto'
    header['PYPELINE']='MultiSlit';header['WAVEMED']='vacuum'
    header['SPECSYS']='TOPOCENT';header['BUNIT']='electron'
    header['EPSTATUS']='EXPERIMENTAL';header['QCSTAGE']=stage
    header['OBJMODEL']=arrays is not None
    header['WINCOORD']='zero-based extraction-window pixels'
    if raw_origin is not None:
        header['RAWY0'],header['RAWX0']=map(int,raw_origin)
    product.write_to_fits(str(path),pri_hdr=header,overwrite=False)
    # Exercise the same loader as the upstream inspection tools.
    loaded=Spec2DObj.from_file(str(path),obj.detname)
    if not np.array_equal(loaded.waveimg,wavevac):
        raise ValueError('diagnostic wavelength image failed round-trip')
    return str(path)
