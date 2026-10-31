"""Conservative FITS inventory, not a calibration selector or setup generator."""

from collections import Counter
import hashlib
import math
from pathlib import Path

from astropy.io import fits

from .naming import legacy_token, observing_night


HEADER_KEYS = (
    "INSTRUME", "OBJECT", "DATE-OBS", "MJD-OBS", "EXPTIME", "ARCFILE",
    "RA", "DEC", "ESO OBS ID", "ESO OBS PROG ID",
    "ESO DPR CATG", "ESO DPR TECH", "ESO DPR TYPE",
    "ESO INS GRIS1 NAME", "ESO INS FILT1 NAME", "ESO INS SLIT1 NAME",
    "ESO DET WIN1 BINX", "ESO DET WIN1 BINY", "ESO DET READ SPEED",
    "ESO DET OUT1 GAIN", "ESO DET OUT1 RON", "ESO TEL AIRM START",
    "NAXIS", "NAXIS1", "NAXIS2", "CDELT1", "CDELT2", "CTYPE1", "CTYPE2",
    "FILETYPE", "PRODCATG", "PROV1", "TRACE1", "BUNIT",
)
# Evidence: PypeIt tag 2.0.1, ntt_efosc2.config_specific_par.
# A bundled template is NOT certification of ePESSTO reduction readiness.
PYPEIT_TEMPLATE_GRISMS = {"Gr4", "Gr5", "Gr6"}


def classify(header) -> str:
    """Exclude known derivatives and non-spectroscopy before frame typing.

Unknown geometry is held for review. Only the legacy 1030x1030 detector mode
has been inspected; transformed frames can retain all raw ESO header cards.
"""
    if str(header.get("INSTRUME", "")).strip().upper() != "EFOSC":
        return "other_instrument"
    if (any(key in header for key in ("FILETYPE", "PRODCATG", "PROV1", "TRACE1"))
        or any(str(header.get(key, "")).upper() in {"LINEAR", "MULTISPE", "WAVE", "AWAV"}
               for key in ("CTYPE1", "CTYPE2"))):
        return "processed"
    if (header.get("NAXIS"), header.get("NAXIS1"), header.get("NAXIS2")) != (2, 1030, 1030):
        return "review_geometry"
    kind = str(header.get("ESO DPR TYPE", "")).strip().upper()
    category = str(header.get("ESO DPR CATG", "")).strip().upper()
    tech = str(header.get("ESO DPR TECH", "")).strip().upper()
    if kind == "BIAS" and category == "CALIB":
        return "bias"
    if kind == "DARK" and category == "CALIB":
        return "dark"
    if tech != "SPECTRUM":
        return "non_spectroscopic" if tech else "review_type"
    if kind == "WAVE" and category == "CALIB":
        return "arc"
    if kind in {"FLAT", "LAMP,FLAT", "DOME,FLAT", "SKY,FLAT"} and category == "CALIB":
        return "flat"
    if kind in {"STD", "STD,FLUX"} and category in {"SCIENCE", "CALIB"}:
        return "standard_candidate"
    if kind == "OBJECT" and category == "SCIENCE":
        return "science"
    return "review_type"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_file(path: Path) -> dict:
    with fits.open(path, mode="readonly", memmap=False) as hdus:
        header = hdus[0].header.copy()
    metadata = {}
    for key in HEADER_KEYS:
        value = header.get(key)
        metadata[key] = None if isinstance(value, float) and not math.isfinite(value) else value
    role = classify(header)
    issues = []
    night = None
    if metadata["DATE-OBS"]:
        try:
            night = observing_night(metadata["DATE-OBS"])
        except (ValueError, TypeError):
            issues.append("invalid DATE-OBS")
    selected = role in {"science", "standard_candidate", "arc", "flat", "bias", "dark"}
    if selected:
        required = ["DATE-OBS", "MJD-OBS", "EXPTIME", "ESO DET WIN1 BINX",
                    "ESO DET WIN1 BINY", "ESO DET READ SPEED",
                    "ESO DET OUT1 GAIN", "ESO DET OUT1 RON"]
        if role not in {"bias", "dark"}:
            required += ["ESO INS GRIS1 NAME", "ESO INS FILT1 NAME", "ESO INS SLIT1 NAME"]
        if role in {"science", "standard_candidate"}:
            required += ["OBJECT", "RA", "DEC", "ESO TEL AIRM START"]
        issues.extend(f"missing {key}" for key in required if metadata[key] in (None, ""))
        for axis, card in (("X", "CDELT1"), ("Y", "CDELT2")):
            if metadata[card] != metadata[f"ESO DET WIN1 BIN{axis}"]:
                issues.append(f"{card} disagrees with detector binning")
    setup = {
        "grism": legacy_token(str(metadata["ESO INS GRIS1 NAME"] or "")),
        "filter": legacy_token(str(metadata["ESO INS FILT1 NAME"] or "")),
        "slit": legacy_token(str(metadata["ESO INS SLIT1 NAME"] or "")),
        "binx": metadata["ESO DET WIN1 BINX"],
        "biny": metadata["ESO DET WIN1 BINY"],
        "readout": metadata["ESO DET READ SPEED"],
        "shape_yx": [metadata["NAXIS2"], metadata["NAXIS1"]],
    }
    return {"path": str(path), "sha256": sha256(path), "role": role,
            "night": night, "setup": setup, "metadata": metadata, "issues": issues}


def inventory(roots) -> dict:
    """Report all FITS inputs, byte duplicates, and archive-identity conflicts.

Never silently select among different files with the same ARCFILE. Counts
describe unique byte content, and duplicate paths remain in the manifest.
"""
    paths = set()
    for root in roots:
        root = Path(root).resolve()
        if not root.exists():
            raise FileNotFoundError(root)
        candidates = [root] if root.is_file() else root.rglob("*")
        paths.update(p.resolve() for p in candidates if p.is_file() and
                     p.name.lower().endswith((".fits", ".fit", ".fts", ".fits.gz", ".fits.fz")))
    if not paths:
        raise ValueError("no FITS files found")
    frames, errors, seen, identities = [], [], {}, {}
    for path in sorted(paths):
        try:
            frame = inspect_file(path)
        except (OSError, ValueError, TypeError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        digest = frame["sha256"]
        if digest in seen:
            frame["duplicate_of"] = seen[digest]
        else:
            seen[digest] = str(path)
        archive_id = frame["metadata"]["ARCFILE"]
        if archive_id and frame["role"] in {"science", "standard_candidate", "arc", "flat", "bias", "dark"}:
            identities.setdefault(archive_id, {}).setdefault(digest, []).append(str(path))
        frames.append(frame)
    unique = [f for f in frames if "duplicate_of" not in f]
    counts = dict(sorted(Counter(f["role"] for f in unique).items()))
    conflicts = {key: groups for key, groups in identities.items() if len(groups) > 1}
    blockers = ["Full native PypeIt calibration and production validation are not complete; inventory does not authorize reduction."]
    grisms = sorted({f["setup"]["grism"] for f in unique if f["role"] in {"science", "standard_candidate"}})
    missing_templates = sorted(set(grisms) - PYPEIT_TEMPLATE_GRISMS)
    if missing_templates:
        blockers.append("No bundled PypeIt 2.0.1 EFOSC2 template for: " + ", ".join(missing_templates))
    for role in ("arc", "bias", "flat", "standard_candidate"):
        if not counts.get(role):
            blockers.append(f"No raw {role} found; full calibration completeness is not established.")
    if conflicts:
        blockers.append("Conflicting raw files share ARCFILE identities; resolve before planning.")
    if errors or any(f["issues"] or f["role"].startswith("review_") for f in unique):
        blockers.append("Unreadable files or metadata/geometry need review.")
    return {"schema_version": 1, "purpose": "migration_inventory_only",
            "pypeit_reference_version": "2.0.1", "reduction_ready": False,
            "counts_unique_content": counts, "duplicate_count": len(frames) - len(unique),
            "identity_conflicts": conflicts, "blockers": blockers,
            "errors": errors, "frames": frames}
