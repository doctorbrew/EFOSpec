"""Create reviewable EFOSC raw lists, or combine reviewed lists into raw.list."""
import argparse
import csv
import os
from pathlib import Path
from astropy.io import fits


def combine(output):
    names = []
    for role in ("science", "standard", "bias", "flat", "arc"):
        path = Path(role + ".list")
        lines = path.read_text().splitlines()
        if not lines or any(not line.strip() for line in lines):
            raise SystemExit(f"Empty list or blank line: {path}")
        for name in lines:
            if name != name.strip() or Path(name).name != name:
                raise SystemExit(f"Use one raw basename per line: {name!r}")
            if not Path(name).is_file():
                raise SystemExit(f"Missing input: {name}")
            h = fits.getheader(name)
            if "FILETYPE" in h or "PRODCATG" in h:
                raise SystemExit(f"Reduced product in input list: {name}")
            if name not in names:
                names.append(name)
    if output.exists():
        raise SystemExit(f"{output} exists; choose --raw-list raw-v2.list to retain it.")
    with output.open("x") as stream:
        stream.writelines(name + "\n" for name in names)
    print(f"Wrote {output}: {len(names)} unique inputs. Calibration/source review remains required.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("."))
    parser.add_argument("--grism", default="Gr#13")
    parser.add_argument("--filter", nargs="+", default=["Free"], dest="filters")
    parser.add_argument("--slit", default="slit#1.0")
    parser.add_argument("--binning", nargs=2, type=int, default=[2, 2])
    parser.add_argument("--read-speed", default="fastL")
    parser.add_argument("--read-mode", default="normal")
    parser.add_argument("--combine", action="store_true", help="Validate and combine the five reviewed role lists")
    parser.add_argument("--raw-list", type=Path, default=Path("raw.list"))
    args = parser.parse_args()
    os.chdir(args.directory.resolve())
    if args.combine:
        combine(args.raw_list)
        return
    GRISM, FILTERS, SLIT = args.grism, set(args.filters), args.slit
    BINNING, READ_SPEED, READ_MODE = tuple(args.binning), args.read_speed, args.read_mode
    roles = ("bias", "arc", "flat", "science", "standard")
    lists = {role: [] for role in roles}
    columns = ["filename", "role", "selected", "object", "exptime", "date_obs",
               "category", "type", "technique", "grism", "filter", "slit",
               "binx", "biny", "read_speed", "read_mode", "ob_id", "shape"]
    outputs = [Path("inventory.csv")] + [Path(role + ".list") for role in roles]
    if any(path.exists() for path in outputs):
        raise SystemExit("Lists already exist: use a fresh directory to regenerate them.")
    paths = sorted(Path(".").glob("EFOSC*.fits"))
    if not paths:
        raise SystemExit("No EFOSC*.fits found. Copy the uncompressed raw FITS files here first.")
    rows = []
    for path in paths:
        h = fits.getheader(path)
        obj = str(h.get("OBJECT", "")).strip()
        exp = h.get("EXPTIME")
        tech = h.get("ESO DPR TECH", "")
        typ = str(h.get("ESO DPR TYPE", "")).upper()
        role = "review"
        if h.get("FILETYPE") is not None or h.get("PRODCATG") is not None:
            role = "reduced:exclude"
        elif str(h.get("INSTRUME", "")).upper() != "EFOSC":
            role = "other:exclude"
        elif exp == 0:
            role = "bias"  # ESO can label zero-second EFOSC biases as DARK.
        elif tech != "SPECTRUM":
            role = "image:exclude"  # Includes acquisition and imaging sky flats.
        elif obj.upper() in {"FLAT", "DOME"}:
            role = "flat"
        elif obj.upper() == "WAVE":
            role = "arc"
        elif typ == "STD":
            role = "standard"
        elif typ == "OBJECT":
            role = "science"
        grism, filt, slit = (h.get("ESO INS " + key + " NAME", "")
                             for key in ("GRIS1", "FILT1", "SLIT1"))
        bx, by = h.get("ESO DET WIN1 BINX"), h.get("ESO DET WIN1 BINY")
        speed, mode = h.get("ESO DET READ SPEED", ""), h.get("ESO DET READ MODE", "")
        detector_ok = (bx, by) == BINNING and speed == READ_SPEED and mode == READ_MODE
        setup_ok = grism == GRISM and filt in FILTERS and slit == SLIT
        selected = role in roles and detector_ok and (role == "bias" or setup_ok)
        if selected:
            lists[role].append(path.name)
        rows.append([path.name, role, selected, obj, exp, h.get("DATE-OBS", ""),
                     h.get("ESO DPR CATG", ""), typ, tech, grism, filt, slit,
                     bx, by, speed, mode, h.get("ESO OBS ID", ""),
                     str(h.get("NAXIS1")) + "x" + str(h.get("NAXIS2"))])
    with Path("inventory.csv").open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)
    for role, names in lists.items():
        with Path(role + ".list").open("x") as stream:
            stream.writelines(name + "\n" for name in names)
        print(f"{role:8s}: {len(names):3d} candidate(s)")
    print("Inspect inventory.csv and the actual images before accepting these lists.")


if __name__ == "__main__":
    main()
