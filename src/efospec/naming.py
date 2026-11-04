"""Legacy science-product naming without importing ntt or PyRAF.

The caller owns the run's processing date and existing-product registry.
These functions neither read nor overwrite products.
"""

from datetime import date, datetime, timedelta, timezone
import re
from typing import Mapping, Optional


def legacy_token(value: str) -> str:
    """Match readkey3's removal of '#' from string metadata."""
    return value.replace("#", "")


def source_order(record):
    """Display AT/SN targets first, grouped by name and then exposure time.

    This is presentation order only; FITS headers continue to define frame roles.
    Accept inventory frames, reduction results and QC records.
    """
    header = record.get('metadata', {})
    name = str(header.get('OBJECT') or record.get('object', ''))
    transient = bool(re.match(r'^(?:AT|SN)\s*\d{4}[a-z]+$', name.strip(), re.I))
    return (not transient, name.casefold(),
            str(header.get('DATE-OBS') or record.get('date_obs', '')),
            str(record.get('raw', record.get('path', record.get('raw_name', '')))))


def observing_night(date_obs: str) -> str:
    instant = datetime.fromisoformat(date_obs.replace("Z", "+00:00"))
    if instant.tzinfo is not None:
        instant = instant.astimezone(timezone.utc).replace(tzinfo=None)
    return (instant - timedelta(hours=12)).strftime("%Y%m%d")


def processing_mjd(processing_date: date) -> int:
    return (processing_date - date(1858, 11, 17)).days


def science_stem(object_name: str, date_obs: str, grism: str, filter_name: str,
                 slit: str, *, profile: str = "rapid",
                 run_mjd: Optional[int] = None) -> str:
    """Rectified 2D science stem, before collision number and suffix.

Full reductions require the stored run MJD, never an implicit current date.
Path separators in OBJECT receive the historical normalization. Unexpected
path/control characters in other tokens are rejected rather than renamed.
"""
    if profile not in {"rapid", "full"}:
        raise ValueError("profile must be rapid or full")
    if profile == "full" and (type(run_mjd) is not int or run_mjd < 0):
        raise ValueError("full naming requires a nonnegative integer run_mjd")
    if profile == "rapid" and run_mjd is not None:
        raise ValueError("rapid naming does not use run_mjd")
    target = legacy_token(object_name).replace(" ", "").replace("/", "_")
    tokens = [target, observing_night(date_obs), legacy_token(grism),
              legacy_token(filter_name), legacy_token(slit)]
    if any(not t or any(c in t for c in "/\\") or
           any(ord(c) < 32 for c in t) for t in tokens):
        raise ValueError("empty or unsafe filename token")
    if profile == "full":
        tokens.append(str(run_mjd))
    return "t" + "_".join(tokens)


def product_name(stem: str, date_obs: str, existing: Mapping[str, str],
                 suffix: str = "") -> str:
    """Reuse exact DATE-OBS; otherwise allocate the lowest unused number.

existing maps basenames to original DATE-OBS strings. Unlike legacy globbing,
numbers above 99 are handled. Ambiguous identity is an error. A persistent
run manifest must later reserve names atomically for concurrent reductions.
"""
    if suffix not in {"", "_ex", "_f", "_2df", "_e"}:
        raise ValueError("unknown product suffix")
    if not stem or any(c in stem for c in "/\\") or any(ord(c) < 32 for c in stem):
        raise ValueError("unsafe product stem")
    pattern = re.compile(re.escape(stem) + r"_([1-9][0-9]*)" + re.escape(suffix) + r"\.fits")
    matches = {name: obs for name, obs in existing.items() if pattern.fullmatch(name)}
    same = [name for name, obs in matches.items() if obs == date_obs]
    if len(same) > 1:
        raise ValueError("multiple products have the same DATE-OBS")
    if same:
        return same[0]
    number = 1
    while f"{stem}_{number}{suffix}.fits" in matches:
        number += 1
    return f"{stem}_{number}{suffix}.fits"
