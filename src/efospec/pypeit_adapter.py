"""EFOSC2 metadata/parameter integration tested against PypeIt 1.14.0.

Import only inside the PypeIt environment. No site-packages edits or registry
patches: pass the spectrograph instance to PypeIt's public metadata interface.
This does not provide missing wavelength templates or perform a reduction.
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import astropy
import pypeit
from pypeit.core import framematch
from pypeit import io
from pypeit.metadata import PypeItMetaData
from pypeit.spectrographs.ntt_efosc2 import NTTEFOSC2Spectrograph

from .inventory import classify, sha256
from .planning import RAW_ROLES, validate_frame


class EFOSpecEFOSC2Spectrograph(NTTEFOSC2Spectrograph):
    # Persistent PYP_SPEC identifier: retain compatibility with saved FITS files.
    name = "ntt_efosc2_epessto"
    supported = False  # metadata integration is not scientific certification

    def init_meta(self):
        super().init_meta()
        self.meta["filter1"] = dict(ext=0, card="ESO INS FILT1 NAME")
        self.meta["mode"] = dict(ext=0, card="ESO DET READ SPEED")
        self.meta["idname"] = dict(card=None, compound=True)

    def get_headarr(self, inp, strict=True):
        # PypeIt 1.14's filename branch leaves its opened HDUList unclosed.
        # Own the handle here; caller-supplied HDULists remain caller-owned.
        if isinstance(inp, (str, Path)):
            try:
                with io.fits_open(inp) as hdus:
                    return [h.copy() for h in super().get_headarr(hdus, strict=strict)]
            except OSError:
                if strict:
                    raise
                warnings.warn(f"Cannot open {inp}", RuntimeWarning)
                return None
        return super().get_headarr(inp, strict=strict)

    def compound_meta(self, headarr, meta_key):
        if meta_key == "idname":
            return classify(headarr[0])
        if meta_key == "binning":
            h = headarr[0]
            x, y = h["ESO DET WIN1 BINX"], h["ESO DET WIN1 BINY"]
            if x != h["CDELT1"] or y != h["CDELT2"]:
                raise ValueError("raw CDELT disagrees with detector binning")
            if x != 2 or y != 2:
                raise ValueError("only the inspected 2x2 EFOSC2 mode is enabled")
            return f"{y},{x}"
        return super().compound_meta(headarr, meta_key)

    def configuration_keys(self):
        return super().configuration_keys() + ["filter1", "mode"]

    def config_independent_frames(self):
        return {"bias": ["binning", "datasec", "mode"],
                "dark": ["binning", "datasec", "mode"]}

    def raw_header_cards(self):
        return super().raw_header_cards() + ["ESO INS FILT1 NAME", "ESO DET READ SPEED",
                                           "ESO DET OUT1 GAIN", "ESO DET OUT1 RON",
                                           "ESO DPR TECH", "ESO DPR TYPE", "ESO DPR CATG"]

    def get_detector_par(self, det, hdu=None):
        if det != 1 or hdu is None:
            raise ValueError("EFOSC2 detector 1 requires a raw FITS header")
        h = hdu[0].header
        if classify(h) not in RAW_ROLES:
            raise ValueError("not an inspected raw EFOSC2 spectroscopy/calibration frame")
        detector = super().get_detector_par(det, hdu=hdu)
        for key, card in (("gain", "ESO DET OUT1 GAIN"), ("ronoise", "ESO DET OUT1 RON")):
            value = float(h[card])
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"invalid {card}")
            detector[key] = np.array([value])
        return detector

    def check_frame_type(self, ftype, fitstbl, exprng=None):
        role = {"science": "science", "standard": "standard_candidate", "bias": "bias",
                "dark": "dark", "arc": "arc", "tilt": "arc", "pixelflat": "flat",
                "illumflat": "flat", "trace": "flat"}.get(ftype)
        good_exp = framematch.check_frame_exptime(fitstbl["exptime"], exprng)
        return good_exp & (np.asarray(fitstbl["idname"]) == role) if role else np.zeros(len(fitstbl), dtype=bool)

    @classmethod
    def default_pypeit_par(cls):
        par = super().default_pypeit_par()
        par["calibrations"]["wavelengths"]["refframe"] = "observed"
        # Avoid accidental default overscan/dark/CR processing in either profile.
        par.reset_all_processimages_par(use_overscan=False, use_darkimage=False, mask_cr=False)
        return par

    def profile_parameters(self, profile):
        if profile not in {"rapid", "full"}:
            raise ValueError("profile must be rapid or full")
        par = self.default_pypeit_par()
        if profile == "rapid":
            par.reset_all_processimages_par(use_biasimage=False, use_pixelflat=False,
                                             use_illumflat=False, use_specillum=False)
        else:
            par.reset_all_processimages_par(use_biasimage=True)
            # A master bias is an input to the other frames, never to itself.
            par['calibrations']['biasframe']['process']['use_biasimage'] = False
            for frame in (par["scienceframe"], par["calibrations"]["standardframe"]):
                frame["process"]["use_pixelflat"] = True
                frame["process"]["use_illumflat"] = True
        return par


def inspect_setup(report, plan, profile="full"):
    """Exercise native metadata, setup grouping, and pixel reader; JSON results.

Explicit frame types come from the catalogue-aware plan, avoiding PypeIt's
different standard-star catalogue/radius. No runnable .pypeit file is emitted
until calibration groups and wavelength solutions are validated.
"""
    if pypeit.__version__ != "1.14.0":
        raise ValueError(f"adapter currently tested only with PypeIt 1.14.0, found {pypeit.__version__}")
    if plan["profile"] != profile:
        raise ValueError("plan/profile mismatch")
    if report["errors"] or report["identity_conflicts"] or plan["invalid_inputs"]:
        raise ValueError("resolve inventory/plan errors before inspecting PypeIt setup")
    selected = sorted((f for f in report["frames"] if f["role"] in RAW_ROLES and "duplicate_of" not in f),
                      key=lambda f: f["path"])
    if not selected:
        raise ValueError("no raw spectroscopy/calibration frames")
    names = [Path(f["path"]).name for f in selected]
    if len(set(names)) != len(names):
        raise ValueError("PypeIt metadata requires unique basenames; conflicting names must be resolved")
    planned = {e["path"]: e for e in plan["exposures"]}
    if not planned:
        raise ValueError("no planned science or standard exposures")
    roles = {"science": "science", "standard": "standard", "arc": "arc,tilt",
             "flat": "pixelflat,trace,illumflat", "bias": "bias", "dark": "dark"}
    user_types = {}
    for f in selected:
        if validate_frame(f) or sha256(Path(f["path"])) != f["sha256"]:
            raise ValueError(f"invalid or changed raw input: {f['path']}")
        role = planned[f["path"]]["role"] if f["path"] in planned else f["role"]
        if role not in roles:
            raise ValueError(f"unverified standard identity: {f['path']}")
        user_types[Path(f["path"]).name] = roles[role]
    instrument = EFOSpecEFOSC2Spectrograph()
    parameters = instrument.profile_parameters(profile)
    table = PypeItMetaData(instrument, parameters, files=[f["path"] for f in selected], strict=True)
    table.get_frame_types(user=user_types)
    table.set_configurations()
    rows, missing_templates = [], set()
    # PypeIt sorts metadata by MJD; input order is not a row identity.
    rows_by_name = {str(row["filename"]): row for row in table.table}
    for f in selected:
        row = rows_by_name[Path(f["path"]).name]
        detector, raw, hdu, exposure, data_mask, overscan_mask = instrument.get_rawimage(f["path"], 1)
        try:
            configured = instrument.config_specific_par(f["path"], inp_par=instrument.profile_parameters(profile))
            template = configured["calibrations"]["wavelengths"]["reid_arxiv"]
            if not template and f["role"] in {"science", "standard_candidate"}:
                missing_templates.add(f["setup"]["grism"])
            rows.append({"path": f["path"], "sha256": f["sha256"],
                         "target": str(row["target"]), "frametype": str(row["frametype"]),
                         "setup": str(row["setup"]), "grism": str(row["dispname"]),
                         "filter": str(row["filter1"]), "slit": str(row["decker"]),
                         "readout": str(row["mode"]), "binning": detector["binning"],
                         "gain_e_per_adu": float(detector["gain"][0]),
                         "read_noise_e": float(detector["ronoise"][0]),
                         "raw_shape": list(raw.shape), "data_pixels": int(np.count_nonzero(data_mask)),
                         "overscan_pixels": int(np.count_nonzero(overscan_mask)),
                         "datasec": detector["datasec"].tolist(),
                         "wavelength_template": template})
        finally:
            hdu.close()
    process = parameters["scienceframe"]["process"]
    return {"schema_version": 1, "purpose": "pypeit_setup_inspection_only",
            "python_executable": sys.executable, "pypeit_version": pypeit.__version__,
            "python_version": sys.version.split()[0], "numpy_version": np.__version__,
            "astropy_version": astropy.__version__,
            "adapter": instrument.name, "profile": profile,
            "configuration_keys": instrument.configuration_keys(),
            "reference_frame": parameters["calibrations"]["wavelengths"]["refframe"],
            "science_processing": {k: process[k] for k in ("use_biasimage", "use_overscan", "use_darkimage",
                                      "use_pixelflat", "use_illumflat", "use_specillum", "mask_cr")},
            "missing_wavelength_templates": sorted(missing_templates),
            "calibration_groups_assigned": False, "reduction_ready": False, "frames": rows}


# Compatibility name for existing integrations.
EPESSTOEFOSC2Spectrograph = EFOSpecEFOSC2Spectrograph
