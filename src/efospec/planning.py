"""Deterministic raw-calibration plans. No masters are built or substituted."""

from collections import defaultdict
from pathlib import Path
import math

from astropy.coordinates import SkyCoord
import astropy.units as u

from .inventory import sha256


RAW_ROLES = {"science", "standard_candidate", "arc", "flat", "bias", "dark"}


def load_standards(path):
    rows = [line.split() for line in Path(path).read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    # The legacy catalogue includes +36:07:60.0: carry seconds explicitly.
    def degrees(value, hours=False):
        a, b, c = map(float, value.lstrip("+-").split(":"))
        return (-1 if value.startswith("-") else 1) * (a + b/60 + c/3600) * (15 if hours else 1)
    coords = SkyCoord([degrees(r[1], True) for r in rows] * u.deg,
                      [degrees(r[2]) for r in rows] * u.deg)
    return [r[0] for r in rows], coords


def standard_match(frame, catalogue):
    names, coordinates = catalogue
    h = frame["metadata"]
    position = SkyCoord(float(h["RA"]) * u.deg, float(h["DEC"]) * u.deg)
    separation = position.separation(coordinates).arcsec
    matches = [i for i, distance in enumerate(separation) if distance < 100]
    if len(matches) > 1:
        raise ValueError(f"ambiguous standard identity: {frame['path']}")
    if not matches:
        return None
    index = matches[0]
    return {"name": names[index], "separation_arcsec": float(separation[index])}


def validate_frame(frame):
    """Reject unusable raw metadata before comparing or ranking candidates."""
    errors = list(frame["issues"])
    h, s = frame["metadata"], frame["setup"]
    for key in ("MJD-OBS", "EXPTIME", "ESO DET OUT1 GAIN", "ESO DET OUT1 RON"):
        try:
            value = float(h[key])
            if not math.isfinite(value) or value < 0 or (key == "ESO DET OUT1 GAIN" and value == 0):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid {key}")
    if not frame["night"]:
        errors.append("missing observing night")
    for key in ("binx", "biny"):
        if type(s[key]) is not int or s[key] < 1:
            errors.append(f"invalid {key}")
    if frame["role"] in {"science", "standard_candidate"}:
        try:
            ra, dec, airmass = (float(h[k]) for k in ("RA", "DEC", "ESO TEL AIRM START"))
            if not (0 <= ra < 360 and -90 <= dec <= 90 and math.isfinite(airmass) and airmass >= 1):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            errors.append("invalid coordinates or airmass")
    return sorted(set(errors))


def compatibility(target, candidate, role):
    """Physical eligibility, with the historical wide-slit arc exception."""
    a, b = target["setup"], candidate["setup"]
    keys = ["binx", "biny", "readout", "shape_yx"]
    if role != "bias":
        keys += ["grism", "filter"]
    reasons = [f"different {key}" for key in keys if a[key] != b[key]]
    if role in {"arc", "flat", "standard"}:
        slit = "slit1.0" if role == "arc" and a["slit"] == "slit5.0" else a["slit"]
        if slit != b["slit"]:
            reasons.append("different slit")
    return reasons


def _distance(target, candidates):
    mjd = float(target["metadata"]["MJD-OBS"])
    return abs(sum(float(c["metadata"]["MJD-OBS"]) for c in candidates)/len(candidates) - mjd)


def _select(target, pool, role, explicit=()):
    """Select one arc/standard or a raw bias/flat combination group.

Only supplied raw files participate. 'missing' never invokes a hidden archive.
Equally ranked groups are ambiguous, not resolved by filename order.
"""
    rejected, eligible = [], []
    for c in pool:
        reasons = compatibility(target, c, role)
        if role in {"arc", "flat", "standard"} and c["night"] != target["night"] and c["path"] not in explicit:
            reasons.append("not from observing night (explicit arc override required for off-night arcs)")
        if reasons:
            rejected.append({"path": c["path"], "reasons": reasons})
        else:
            eligible.append(c)
    if role == "arc" and explicit:
        # Overrides are selections, not hints: never fall through to a different arc.
        eligible = [c for c in eligible if c["path"] in explicit]
    if role == "flat":
        # Legacy chooses the lamp-flat list before testing group size; it does
        # not silently substitute dome flats when a lamp group is too small.
        kind = "flat" if any(str(c["metadata"].get("OBJECT", "")).lower() == "flat" for c in eligible) else "dome"
        retained = []
        for c in eligible:
            if str(c["metadata"].get("OBJECT", "")).lower() == kind:
                retained.append(c)
            else:
                rejected.append({"path": c["path"], "reasons": [f"legacy flat list requires OBJECT={kind}"]})
        eligible = retained
    if role in {"arc", "standard"}:
        groups = [[c] for c in eligible]
    else:
        grouped = defaultdict(list)
        for c in eligible:
            key = (c["night"],) if role == "bias" else (
                c["night"], c["metadata"].get("ESO OBS ID"),
                str(c["metadata"].get("OBJECT", "")).lower())
            if role == "flat" and key[1] is None:
                rejected.append({"path": c["path"], "reasons": ["missing flat OBID"]})
                continue
            grouped[key].append(c)
        groups = []
        for group in grouped.values():
            if len(group) >= 3:
                groups.append(group)
            else:
                rejected.extend({"path": c["path"], "reasons": ["fewer than three frames in group"]} for c in group)
    def rank(group):
        c = group[0]
        if role == "flat":
            # Preserve preference for lamp 'flat', then dome; OBID within that class.
            kind = str(c["metadata"].get("OBJECT", "")).lower()
            flat_rank = 0 if kind == "flat" else 1 if kind == "dome" else 2
            return (flat_rank, 0 if c["metadata"].get("ESO OBS ID") == target["metadata"].get("ESO OBS ID") else 1,
                    _distance(target, group))
        return (_distance(target, group),)
    groups.sort(key=rank)
    status = "missing" if not groups else "ambiguous" if len(groups) > 1 and rank(groups[0]) == rank(groups[1]) else "selected"
    selected = groups[0] if status == "selected" else []
    return {"status": status, "files": [c["path"] for c in selected],
            "sha256": [c["sha256"] for c in selected],
            "time_separation_days": _distance(target, selected) if selected else None,
            "source": "explicit_raw" if role == "arc" and explicit else "supplied_raw",
            "policy": {"arc": "nearest compatible arc; slit5.0 uses slit1.0",
                       "bias": "nearest compatible nightly group of at least three",
                       "flat": "lamp-flat preference, same OBID then time; at least three",
                       "standard": "nearest same-night catalogue standard in identical setup"}[role],
            "rejected": rejected}


def build_plan(report, reference_root, profile="full", explicit_arcs=()):
    """Plan raw associations; processed archive masters remain unsupported."""
    if profile not in {"rapid", "full"}:
        raise ValueError("profile must be rapid or full")
    root = Path(reference_root).resolve()
    catalogue_path = root / "standard/stdlist/standard_efosc_mab.txt"
    extinction = root / "standard/extinction" / ("lasilla2.txt" if profile == "full" else "extinction_lasilla.dat")
    catalogue = load_standards(catalogue_path)
    references = {"catalogue": {"path": str(catalogue_path), "sha256": sha256(catalogue_path)},
                  "extinction_1d": {"path": str(extinction), "sha256": sha256(extinction)}}
    raw = sorted((f for f in report["frames"] if f["role"] in RAW_ROLES and "duplicate_of" not in f),
                 key=lambda f: f["path"])
    invalid = [{"path": f["path"], "issues": validate_frame(f)} for f in raw if validate_frame(f)]
    blockers = []
    if report["errors"] or report["identity_conflicts"] or invalid:
        blockers.append("Resolve unreadable inputs, conflicting identities or invalid raw metadata before planning.")
    arcs = {str(Path(p).resolve()) for p in explicit_arcs}
    available_arcs = {f["path"] for f in raw if f["role"] == "arc"}
    if not arcs <= available_arcs:
        raise ValueError("every explicit arc must be an inventoried raw arc, not a processed master")
    if blockers:
        return {"schema_version": 1, "profile": profile, "references": references, "exposures": [],
                "invalid_inputs": invalid, "blockers": blockers, "associations_complete": False,
                "reduction_ready": False}
    targets, standards = [], []
    for f in raw:
        if f["role"] not in {"science", "standard_candidate"}:
            continue
        match = standard_match(f, catalogue)
        entry = dict(f, standard=match, planned_role="standard" if match else f["role"])
        targets.append(entry)
        if match:
            standards.append(entry)
    exposures = []
    for f in targets:
        selections = {}
        if f["role"] == "standard_candidate" and not f["standard"]:
            blockers.append(f"Unmatched standard candidate: {f['path']}")
        for role in ("arc", "bias", "flat"):
            if profile == "rapid" and role in {"bias", "flat"}:
                selections[role] = {"status": "disabled_by_profile", "files": []}
            elif profile == "rapid" and role == "arc" and not arcs:
                selections[role] = {"status": "missing", "files": [],
                    "policy": "rapid requires explicit arc or a validated archive adapter (not yet implemented)"}
            else:
                selections[role] = _select(f, [c for c in raw if c["role"] == role], role, arcs if role == "arc" else ())
        if not f["standard"]:
            if profile == "full":
                selections["standard"] = _select(f, standards, "standard")
            else:
                selections["standard"] = {"status": "missing", "files": [],
                    "policy": "rapid sensitivity selection/import is not implemented"}
        for role, selection in selections.items():
            if selection["status"] in {"missing", "ambiguous"}:
                blockers.append(f"{role} {selection['status']}: {f['path']}")
        exposures.append({"path": f["path"], "sha256": f["sha256"], "role": f["planned_role"],
                          "standard": f["standard"], "setup": f["setup"], "calibrations": selections})
    if not exposures:
        blockers.append("No raw science or standard exposures.")
    complete = not blockers
    blockers.append("Wavelength templates, calibration execution and delivery export remain unvalidated.")
    return {"schema_version": 1, "profile": profile, "references": references,
            "explicit_arcs": sorted(arcs), "exposures": exposures, "invalid_inputs": invalid,
            "blockers": blockers, "associations_complete": complete, "reduction_ready": False}
