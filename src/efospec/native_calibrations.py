"""PypeIt raw calibration groups with independently identified He–Ar lamps.

Every group is built in a fresh output directory. The legacy reference library
is neither accepted as an argument nor searched as a fallback.
"""
import json
from pathlib import Path
import numpy as np

from .inventory import inspect_file, sha256
from .planning import compatibility, validate_frame
from .native_wave import identify_spectrum


def native_parameters(instrument):
    par=instrument.profile_parameters('full')
    par.reset_all_processimages_par(use_biasimage=True,use_pixelflat=False,
        use_illumflat=False,use_specillum=False,use_overscan=False,
        use_darkimage=False,mask_cr=False)
    par['calibrations']['biasframe']['process']['use_biasimage']=False
    par['calibrations']['wavelengths']['reid_arxiv']=None
    par['calibrations']['wavelengths']['lamps']=['HeI','ArI']
    for group in (par['scienceframe'],par['calibrations']['standardframe']):
        group['process']['use_pixelflat']=True
        group['process']['use_illumflat']=True
        group['process']['mask_cr']=True
    return par


def validate_associations(frame, associations):
    """Re-open and verify selected raw frames at execution time."""
    if frame['role'] not in ('science','standard_candidate') or validate_frame(frame):
        raise ValueError('native reduction needs valid raw EFOSC2 science or standard metadata')
    setup=frame['setup']
    if (setup['grism'] not in ('Gr11','Gr13') or setup['filter'] not in ('Free','GG495')
            or setup['binx']!=2 or setup['biny']!=2 or setup['slit'] not in ('slit1.0','slit1.5')):
        raise ValueError('native calibration currently enables centered Gr11/Gr13, 2x2, slit1.0/slit1.5 only')
    files={frame['path']:'science' if frame['role']=='science' else 'standard'}
    for role in ('bias','flat','arc'):
        record=associations.get(role,{})
        paths,digests=record.get('files',[]),record.get('sha256',[])
        minimum=3 if role in ('bias','flat') else 1
        if record.get('status')!='selected' or len(paths)<minimum or len(paths)!=len(digests):
            raise ValueError(f'native {role} association is incomplete')
        for path,digest in zip(paths,digests):
            candidate=inspect_file(Path(path))
            if (candidate['role']!=role or validate_frame(candidate)
                    or compatibility(frame,candidate,role) or candidate['sha256']!=digest):
                raise ValueError(f'incompatible or changed raw {role}: {Path(path).name}')
            files[path]={'bias':'bias','flat':'pixelflat,trace,illumflat','arc':'arc,tilt'}[role]
    if sha256(Path(frame['path']))!=frame['sha256']:
        raise ValueError('science input changed')
    return files


def build_calibrations(frame, associations, output):
    from pypeit import __version__
    from pypeit.metadata import PypeItMetaData
    from pypeit.calibrations import Calibrations
    from pypeit.wavecalib import BuildWaveCalib, WaveCalib
    from pypeit.core.wavecal.autoid import map_fwhm
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    if __version__!='1.14.0':
        raise ValueError('native calibration is tested with PypeIt 1.14.0')
    files=validate_associations(frame,associations)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    record={'schema_version':1,'mode':'native_raw_only','status':'building',
            'pypeit_version':__version__,'setup':frame['setup'],
            'raw_inputs':{p:sha256(Path(p)) for p in files},
            'associations':{role:associations[role] for role in ('bias','flat','arc')}}
    (output/'calibration.json').write_text(json.dumps(record,indent=2)+'\n')
    try:
        instrument=EFOSpecEFOSC2Spectrograph()
        par=native_parameters(instrument)
        par['rdx']['redux_path']=str(output)
        table=PypeItMetaData(instrument,par,files=list(files),strict=True)
        table.get_frame_types(user={Path(p).name:role for p,role in files.items()})
        table.set_configurations()
        table.set_calibration_groups(default=True)
        table.set_combination_groups()
        index=int(np.flatnonzero(table.table['filename']==Path(frame['path']).name)[0])
        cal=Calibrations.get_instance(table,par['calibrations'],instrument,output/'Calibrations',
                                     qadir=output/'QA',reuse_calibs=False)
        cal.set_config(index,1)
        # PypeIt performs raw processing, stacking, detector masking, and edges.
        for step in ('bias','bpm','arc','tiltimg','slits'):
            if getattr(cal,'get_'+step)() is None:
                raise ValueError(f'PypeIt could not build native {step}')
        if cal.slits.nslits!=1 or cal.slits.mask[0]!=0:
            raise ValueError('native EFOSC2 requires one successfully traced long slit')
        builder=BuildWaveCalib(cal.msarc,cal.slits,instrument,par['calibrations']['wavelengths'],
                               ['HeI','ArI'],det=1,qa_path=output/'QA')
        spectra,bad=builder.extract_arcs()
        if bad.any():
            raise ValueError('raw arc central extraction failed')
        fwhm_map=map_fwhm(cal.msarc.image,builder.gpm,builder.slits_left,builder.slits_right,
                          builder.slitmask,nsample=10,slit_bpm=builder.wvc_bpm,specord=1,spatord=1)
        fwhm=float(fwhm_map[0].eval(cal.msarc.image.shape[0]//2,.5))
        fit,qa=identify_spectrum(spectra[:,0],frame['setup']['grism'],fwhm=fwhm,
                                 filter_name=frame['setup']['filter'],
                                 nonlinear_counts=float(builder.nonlinear_counts))
        fit.spat_id=int(cal.slits.spat_id[0]);fit.fwhm=fwhm
        wavecal=WaveCalib(wv_fits=np.array([fit],dtype=object),fwhm_map=fwhm_map,
            nslits=1,spat_ids=cal.slits.spat_id,PYP_SPEC=instrument.name,
            strpar=json.dumps(par['calibrations']['wavelengths'].data),
            arc_spectra=spectra,lamps='HeI,ArI')
        _,_,_,setup,calib_id,detname=cal.find_calibrations('arc',WaveCalib)
        wavecal.set_paths(cal.calib_dir,setup,calib_id,detname)
        wavecal.to_file()
        cal.wv_calib=wavecal
        cal.slits.mask_wvcalib(wavecal)
        if cal.get_tilts() is None or cal.get_flats() is None:
            raise ValueError('native tilt/flat construction failed')
        if cal.slits.mask[0]!=0:
            raise ValueError('PypeIt flagged the calibrated slit')
        slitmask=cal.slits.slit_img()
        tilts=cal.wavetilts.fit2tiltimg(slitmask)
        wavevac=cal.wv_calib.build_waveimg(tilts,cal.slits)
        good=slitmask>=0
        if not np.isfinite(wavevac[good]).all() or np.any(wavevac[good]<=0):
            raise ValueError('native wavelength map contains invalid pixels')
        np.savez_compressed(output/'wavelength-map.npz',wavevac=wavevac,tilts=tilts,slitmask=slitmask)
        record.update(status='experimental_complete',wavelength=qa,
            processed_files={str(p.relative_to(output)):sha256(p)
                             for p in sorted((output/'Calibrations').glob('*')) if p.is_file()},
            wavelength_map_sha256=sha256(output/'wavelength-map.npz'))
        if any(sha256(Path(p))!=digest for p,digest in record['raw_inputs'].items()):
            raise ValueError('raw calibration input changed while processing')
        return {'calibrations':cal,'parameters':par,'instrument':instrument,
                'wavevac':wavevac,'slitmask':slitmask,'record':record,'directory':output}
    except Exception as exc:
        record.update(status='failed',error=str(exc))
        raise
    finally:
        (output/'calibration.json').write_text(json.dumps(record,indent=2)+'\n')


def process_exposure(frame, bundle):
    """Return the full PypeIt image, including propagated variance and masks."""
    from pypeit.images.buildimage import buildimage_fromlist
    if sha256(Path(frame['path']))!=frame['sha256']:
        raise ValueError('raw exposure changed')
    cal,par=bundle['calibrations'],bundle['parameters']
    group=par['scienceframe'] if frame['role']=='science' else par['calibrations']['standardframe']
    return buildimage_fromlist(bundle['instrument'],1,group,[frame['path']],bias=cal.msbias,
        bpm=cal.msbpm,flatimages=cal.flatimages,slits=cal.slits,ignore_saturation=False)


def load_calibrations(directory):
    """Load only a complete, hash-verified group built by this raw-only runner."""
    from types import SimpleNamespace
    from pypeit.images.buildimage import BiasImage
    from pypeit.slittrace import SlitTraceSet
    from pypeit.flatfield import FlatImages
    from pypeit.wavecalib import WaveCalib
    from .native_wavelength import validate_solution
    from .pypeit_adapter import EFOSpecEFOSC2Spectrograph
    directory=Path(directory).resolve();record=json.loads((directory/'calibration.json').read_text())
    if record.get('status')!='experimental_complete' or record.get('mode')!='native_raw_only':
        raise ValueError('native calibration group is incomplete')
    for path,digest in record['raw_inputs'].items():
        if sha256(Path(path))!=digest:raise ValueError('raw calibration input changed')
    for path,digest in record['processed_files'].items():
        local=(directory/path).resolve()
        if not local.is_relative_to(directory) or sha256(local)!=digest:
            raise ValueError('processed calibration changed')
    if sha256(directory/'wavelength-map.npz')!=record['wavelength_map_sha256']:
        raise ValueError('wavelength map changed')
    def one(pattern):
        matches=list((directory/'Calibrations').glob(pattern))
        if len(matches)!=1:raise ValueError('ambiguous native calibration file')
        return matches[0]
    instrument=EFOSpecEFOSC2Spectrograph()
    wavecal=WaveCalib.from_file(one('WaveCalib_*fits'))
    # Hashes establish identity, not scientific validity under current gates.
    for fit in wavecal.wv_fits:
        validate_solution(fit,record['setup']['grism'],filter_name=record['setup']['filter'])
    bias=BiasImage.from_file(one('Bias_*fits'))
    slit=SlitTraceSet.from_file(one('Slits_*fits*'))
    flat=FlatImages.from_file(one('Flat_*fits'))
    bpm=instrument.bpm(next(iter(record['raw_inputs'])),1,shape=bias.image.shape)
    with np.load(directory/'wavelength-map.npz') as n:wavevac=n['wavevac'];slitmask=n['slitmask']
    cal=SimpleNamespace(msbias=bias,msbpm=bpm,flatimages=flat,slits=slit)
    return dict(calibrations=cal,parameters=native_parameters(instrument),instrument=instrument,
                wavevac=wavevac,slitmask=slitmask,record=record,directory=directory)
