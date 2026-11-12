import numpy as np
import pytest

from efospec.flux_validation import transfer_summary, paired_zeropoint


def test_transfer_distinguishes_grey_loss_colour_and_absorption():
    wave=np.arange(4500.,8500.,2.)
    continuum=~((wave>=7160)&(wave<=7340))
    ratio=np.full(wave.size,.8)
    ratio[~continuum]=.2
    summary=transfer_summary(wave,ratio,np.ones(wave.size,bool),continuum)
    assert summary['grey_ratio']==pytest.approx(.8)
    assert summary['maximum_shape_departure_fraction']==pytest.approx(0.)
    ratio[wave>7500]*=1.2
    summary=transfer_summary(wave,ratio,np.ones(wave.size,bool),continuum)
    assert summary['maximum_shape_departure_fraction']==pytest.approx(.2)
    assert summary['absolute_accuracy_validated'] is False
    assert transfer_summary(wave,ratio,np.zeros(wave.size,bool),continuum)['grey_ratio'] is None


def test_paired_response_removes_standard_red_excess_not_science_contamination():
    wave=np.arange(4500.,8500.,5.)
    truth=np.full(wave.size,20.)
    # Zeropoints add log throughput; contamination brightens the free standard.
    free=truth+2.5*np.log10(np.where(wave>7400,1.3,1.))
    filtered=truth+2.5*np.log10(.9)
    good=np.ones(wave.size,bool)
    merged,support,qa=paired_zeropoint(wave,free,good,wave,filtered,good)
    np.testing.assert_allclose(merged[support],truth[support],atol=1e-12)
    assert qa['science_second_order_removed'] is False
    # Unsupported bins cannot be bridged or replaced with contaminated Free data.
    good[(wave>7900)&(wave<8100)]=False
    _,support,_=paired_zeropoint(wave,free,np.ones_like(good),wave,filtered,good)
    assert not support[(wave>7900)&(wave<8100)].any()
    with pytest.raises(ValueError,match='anchor'):
        paired_zeropoint(wave,free,np.ones_like(good),wave[wave>6000],filtered[wave>6000],good[wave>6000])


def test_telluric_depression_requires_local_continuum_and_is_not_a_correction():
    from efospec.calibration_audit import telluric_residuals
    wave=np.arange(6600.,8000.,2.)
    ratio=np.ones(wave.size)*.8
    ratio[(wave>=7590)&(wave<7700)]*=.7
    arrays=dict(waveair=wave,ratio=ratio,valid=np.ones(wave.size,bool))
    band=telluric_residuals(arrays)[2]
    assert band['relative_band_ratio']==pytest.approx(.7)
    assert band['status']=='measured_depression_not_model'
    arrays['valid'][wave>7750]=False
    assert telluric_residuals(arrays)[2]['relative_band_ratio'] is None
