"""Scientific behavior: blind line recovery, blends, nulls and spatial evidence."""
import numpy as np
import pytest
from efospec.host_redshift import GROUPS,measure_redshift,spatial_line_check,extract_2d_line_spectrum


def emission(wave,z,fwhm,names=('OII','Hgamma','Hbeta','OIII','Halpha_NII','SII')):
    result=np.zeros_like(wave)
    for name in names:
        for i,rest in enumerate(GROUPS[name][0]):
            result+=(20+5*i)*np.exp(-.5*((wave-rest*(1+z))/(fwhm/2.355))**2)
    return result


@pytest.mark.parametrize('z,fwhm',[(.0126,18),(.0238,35),(.1,18),(.3,35)])
def test_blind_multiline_redshift_recovery_with_blended_doublets(z,fwhm):
    wave=np.arange(3650.,9500.,4.);error=np.ones_like(wave)
    flux=30+.002*(wave-6000)+emission(wave,z,fwhm)+np.random.default_rng(18).normal(size=len(wave))
    before=flux.copy();r=measure_redshift(wave,flux,error,fwhm=fwhm)
    assert r['status']=='candidate'
    assert abs(r['z']-z)<8e-5
    assert len(r['solutions'][0]['consistent_groups'])>=3
    assert np.array_equal(flux,before)


@pytest.mark.parametrize('names',[('OIII',),('Halpha_NII',),('Hbeta','Halpha_NII')])
def test_components_of_blends_are_not_three_independent_groups(names):
    w=np.arange(3650.,9500.,4.)
    r=measure_redshift(w,emission(w,.024,35,names),np.ones_like(w),fwhm=35)
    assert r['z'] is None


def test_seeded_noise_and_single_sky_lines_do_not_get_redshifts():
    w=np.arange(3650.,9500.,4.)
    for seed in range(10):
        f=np.random.default_rng(seed).normal(size=len(w))
        for centre in (5578.,6302.,6365.):f+=40*np.exp(-.5*((w-centre)/8)**2)
        assert measure_redshift(w,f,np.ones_like(w),fwhm=18)['z'] is None


def test_a_masked_line_core_cannot_validate_a_redshift():
    w=np.arange(3650.,9500.,4.)
    r=measure_redshift(w,emission(w,.3,35),np.ones_like(w),fwhm=35)
    assert r['z'] is not None
    hbeta=next(g for g in r['solutions'][0]['groups'] if g['group']=='Hbeta')
    assert not hbeta['detected'] and hbeta['core_coverage']<.75


def spatial_example(localized):
    w=np.arange(4000.,7500.,4.);x=np.arange(200)
    line=emission(w,.024,18,('Hbeta','OIII','Halpha_NII'))
    spatial=np.exp(-.5*((x-103)/3.)**2) if localized else np.ones_like(x)
    e=dict(wave_vacuum=w,rectified_sky_subtracted=line[:,None]*spatial,
        rectified_variance=np.ones((len(w),len(x))),spatial_pixel=x,trace=np.full(len(w),100.),aperture_radius_pixels=20.)
    solution=dict(consistent_groups=['Hbeta','OIII','Halpha_NII'],groups=[
        dict(group=name,observed_vacuum_angstrom=(np.array(GROUPS[name][0])*1.024).tolist())
        for name in ('Hbeta','OIII','Halpha_NII')])
    return e,solution


def test_spatial_test_requires_localized_coherent_emission():
    e,s=spatial_example(True);r=spatial_line_check(e,s,18.)
    assert r['passed'] and len(r['coherent_groups'])==3
    e,s=spatial_example(False)
    assert not spatial_line_check(e,s,18.)['passed']


def test_rectification_removes_common_sky_and_uses_vacuum_coordinates():
    w=np.linspace(4000,7500,500);x=np.arange(200);trace=np.full(len(w),100.)
    sky=500+100*np.exp(-.5*((w-5577)/8)**2)
    a=dict(data=np.broadcast_to(sky[:,None],(len(w),len(x))),ivar=np.ones((len(w),len(x))),
           waveair=np.broadcast_to(w[:,None],(len(w),len(x))),mask=np.zeros((len(w),len(x)),int),trace=trace,spatial_origin=349)
    result=extract_2d_line_spectrum(a)
    assert np.nanmax(abs(result['counts']))<1e-7
    assert np.all(result['wave_vacuum']>w)
    assert np.all(result['sigma'][result['valid']]>0)
