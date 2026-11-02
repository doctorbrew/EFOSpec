"""Native processing must build masters without circular calibration inputs."""
import numpy as np
from astropy.io import fits
from efospec.pypeit_adapter import EFOSpecEFOSC2Spectrograph
from pypeit.images.buildimage import buildimage_fromlist
from test_pypeit_adapter import write_raw


def test_full_profile_builds_bias_without_requiring_a_bias(tmp_path):
    paths=[]
    for index, value in enumerate([199.,200.,201.]):
        p=write_raw(tmp_path,f'bias{index}.fits',**{'ESO DPR TYPE':'BIAS','ESO DPR CATG':'CALIB','EXPTIME':0.})
        with fits.open(p,mode='update') as h:h[0].data[:]=value
        paths.append(str(p))
    inst=EFOSpecEFOSC2Spectrograph()
    par=inst.profile_parameters('full')['calibrations']['biasframe']
    bias=buildimage_fromlist(inst,1,par,paths,calib_dir=tmp_path,setup='A',calib_id='0')
    assert bias.image.shape==(1024,1024)
    good = bias.select_flag(invert=True)
    assert good.mean() > .99
    np.testing.assert_allclose(bias.image[good],200.*.91)
    assert np.all(bias.ivar[good]>0)


def test_physical_gate_rejects_low_rms_impossible_solution():
    import pytest
    from types import SimpleNamespace
    from efospec.native_wavelength import validate_solution
    # This matches the observed failure mode: small RMS, impossible wavelength range.
    fit=SimpleNamespace(wave_soln=np.linspace(-200.,7200.,1024),pypeitfit=object(),rms=.02)
    with pytest.raises(ValueError,match='instrument'):
        validate_solution(fit,'Gr13')


def test_calibration_identity_changes_when_any_raw_hash_changes():
    from copy import deepcopy
    from efospec.native_calibration import calibration_key
    entry={'setup':{'grism':'Gr13'},'raw_calibrations':{
        role:{'files':['b','a'],'sha256':['2','1']} for role in ('arc','flat','bias')}}
    original=calibration_key(entry)
    swapped=deepcopy(entry)
    for value in swapped['raw_calibrations'].values():
        value['files'].reverse();value['sha256'].reverse()
    assert calibration_key(swapped)==original
    swapped['raw_calibrations']['flat']['sha256'][0]='changed'
    assert calibration_key(swapped)!=original


def test_small_rms_and_held_out_residuals_do_not_validate_wrong_blue_range():
    import pytest
    from types import SimpleNamespace
    from efospec.native_wavelength import validate_solution
    # All residual and coverage checks pass. The earlier 300-A prior also
    # passed this plausible but physically wrong Gr11 wavelength range.
    wave=np.linspace(3081.,7521.,1024)
    pixels=np.linspace(180.,1000.,13)
    fit=SimpleNamespace(wave_soln=wave,rms=.1,pixel_fit=pixels,
        wave_fit=np.interp(pixels,np.arange(1024),wave),
        pypeitfit=SimpleNamespace(gpm=np.ones(13,dtype=bool),fitc=np.zeros(2)))
    with pytest.raises(ValueError,match='instrument range'):
        validate_solution(fit,'Gr11')


def test_synthetic_raw_arc_recovers_physical_vacuum_solution():
    from efospec.native_wavelength import physical_lines,fit_raw_arc_spectrum
    # Known curved dispersion, physical lines, finite-width peaks, and detector noise.
    pixel=np.arange(1024,dtype=float)
    wave=3650.+5.25*pixel+.00027*pixel**2
    refs=np.asarray(physical_lines()['wave'])
    refs=refs[(refs>wave[0]+20)&(refs<wave[-1]-20)]
    selected=[]
    for ref in refs:
        if not selected or ref-selected[-1]>35:selected.append(ref)
    spectrum=np.full(1024,40.)
    for ref in selected:
        center=np.interp(ref,wave,pixel)
        spectrum+=2000.*np.exp(-.5*((pixel-center)/1.6)**2)
    spectrum+=np.random.default_rng(92).normal(0,2.,1024)
    fit,qa=fit_raw_arc_spectrum(spectrum,'Gr13')
    inside=(wave>qa['valid_wave_vacuum_angstrom'][0])&(wave<qa['valid_wave_vacuum_angstrom'][1])
    assert qa['n_lines']>=10
    assert np.max(abs(fit.wave_soln[inside]-wave[inside]))<1.  # <0.2 spectral pixel
    assert qa['held_out_rms_pixel']<.25
    from efospec.native_wavelength import reidentify_raw_arc
    # A shifted new exposure must be refit, not receive copied coefficients.
    shifted=np.interp(pixel-2.,pixel,spectrum)
    recovered,recovered_qa=reidentify_raw_arc(shifted,'Gr13',fit,spectrum)
    truth=3650.+5.25*(pixel-2.)+.00027*(pixel-2.)**2
    bracket=recovered_qa['valid_wave_vacuum_angstrom']
    inside=(truth>bracket[0])&(truth<bracket[1])
    assert np.max(abs(recovered.wave_soln[inside]-truth[inside]))<1.
    assert np.median(recovered.wave_soln-fit.wave_soln)<-9.


def test_noisy_arc_cannot_create_a_calibration():
    import pytest
    from efospec.native_wavelength import fit_raw_arc_spectrum
    with pytest.raises(ValueError):
        fit_raw_arc_spectrum(np.random.default_rng(1).normal(40.,2.,1024),'Gr13')


def test_native_masters_and_wave_map_from_synthetic_raw_frames(tmp_path):
    from efospec.native_calibration import calibrate_night
    from efospec.native_wavelength import physical_lines
    from efospec.inventory import sha256
    rawdir=tmp_path/'raw';rawdir.mkdir()
    y,x=np.indices((1030,1030));slit=(x>100)&(x<950)
    wave=3650.+5.25*y+.00027*y**2
    lamp=np.zeros_like(wave,dtype=float)
    previous=0.
    for rest in physical_lines()['wave']:
        if not 3700.<rest<9250. or rest-previous<35:continue
        previous=rest
        lamp+=15000.*np.exp(-.5*((wave-rest)/9.)**2)
    records=[]
    def write(name,values,**headers):
        p=write_raw(rawdir,name,**headers)
        with fits.open(p,mode='update') as h:h[0].data=values.astype(float)
        records.append((p,sha256(p)))
    for i in range(3):
        write(f'bias{i}.fits',np.full_like(wave,200.),**{'ESO DPR TYPE':'BIAS','ESO DPR CATG':'CALIB','EXPTIME':0.})
        write(f'flat{i}.fits',200.+slit*(12000.+1000*np.sin(y/400.)),OBJECT='flat',
              **{'ESO DPR TYPE':'FLAT','ESO DPR CATG':'CALIB','ESO OBS ID':100})
    write('arc.fits',200.+slit*lamp,**{'ESO DPR TYPE':'WAVE','ESO DPR CATG':'CALIB'})
    write('science.fits',200.+slit*100.)
    out=tmp_path/'native'
    result=calibrate_night([rawdir],out)
    assert result['status']=='complete', result['groups']
    assert result['science_reduction_ready'] is False
    group=result['groups'][0]
    assert group['wave_qa'][0]['rms_pixel']<.25
    with np.load(out/group['id']/'calibrated_geometry.npz') as geometry:
        valid=geometry['valid'][:,500]
        assert valid.any()
        low,high=group['wave_qa'][0]['valid_wave_vacuum_angstrom']
        keep=valid&(wave[:1024,500]>low)&(wave[:1024,500]<high)
        assert np.median(abs(geometry['wave_vacuum'][keep,500]-wave[:1024,500][keep]))<2.
    assert all(sha256(p)==digest for p,digest in records)
    assert not list(out.rglob('*_f.fits'))  # masters are not flux-calibrated science
    from efospec.native_validation import validate_native_run
    validation=validate_native_run(out,tmp_path/'sky-check')
    assert not validation['science_reduction_ready']
    # A constant sky cannot provide the independent wavelength check.
    assert len(validation['errors'])==1 and not validation['results']
    assert validation['errors'][0]['processing']['bias']
    from efospec.native_calibration import load_native_template
    import pytest
    template=out/group['id']
    wave,provenance=load_native_template(template,group['setup'])
    assert provenance['wavecalib_sha256']
    with pytest.raises(ValueError,match='identical setup'):
        load_native_template(template,dict(group['setup'],filter='GG495'))
    master=next((template/'Calibrations').glob('WaveCalib_*.fits'))
    master.write_bytes(master.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='product changed'):
        load_native_template(template,group['setup'])
    invalid=validate_native_run(out,tmp_path/'tampered-check')
    assert invalid['status']=='incomplete'
    assert invalid['errors'][0]['stage']=='load_calibrations'
