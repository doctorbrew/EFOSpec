import numpy as np
import pytest


@pytest.mark.parametrize('grism,low,disp', [('Gr13',3650.,5.55), ('Gr11',3350.,4.05)])
def test_independent_atomic_lines_recover_curved_raw_wavelengths(grism,low,disp):
    from efospec.native_wave import atlas, identify_spectrum
    refs=atlas()['wave'].data
    pixels=np.arange(1024.)
    wave=low+disp*pixels+35.*(pixels/1023.)**2
    spectrum=np.full(1024,50.)
    used=refs[(refs>wave[15])&(refs<wave[-15])]
    rng=np.random.default_rng(41)
    for wavelength in used:
        center=np.interp(wavelength,wave,pixels)
        spectrum+=rng.uniform(2000,8000)*np.exp(-.5*((pixels-center)/1.8)**2)
    spectrum+=rng.normal(0,3,len(spectrum))
    fit,qa=identify_spectrum(spectrum,grism,fwhm=4.2,nonlinear_counts=1e6)
    bracket=(wave>=qa['reference_lines_vacuum'][0])&(wave<=qa['reference_lines_vacuum'][-1])
    assert np.max(abs(fit.pypeitfit.eval(pixels[bracket]/1023)-wave[bracket]))<.5
    assert qa['held_out_rms_angstrom']<.5
    assert qa['n_lines']>=8
    assert qa['source']=='ESO_EFOSC2_manual_4.2_table_17_physical_wavelengths'


def test_no_lines_and_unsupported_grism_stop():
    from efospec.native_wave import identify_spectrum
    with pytest.raises(ValueError,match='grism'):
        identify_spectrum(np.ones(1024),'Gr16')
    with pytest.raises(ValueError,match='lines'):
        identify_spectrum(np.ones(1024),'Gr13')


def test_small_rms_never_accepts_nonphysical_wavelengths():
    from efospec.native_wave import check_physical_range
    with pytest.raises(ValueError,match='physical'):
        check_physical_range(np.linspace(-4000,3500,1024),'Gr13')
    with pytest.raises(ValueError,match='increasing'):
        check_physical_range(np.linspace(9300,3650,1024),'Gr13')


def test_pair_runner_rejects_endpoint_error_allowed_by_old_center_gate():
    from efospec.native_wave import check_physical_range
    # Plausible central wavelength and dispersion, but shifted detector endpoints.
    with pytest.raises(ValueError, match='range'):
        check_physical_range(np.linspace(3885.,9515.,1024),'Gr13')
