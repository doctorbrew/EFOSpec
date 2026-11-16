"""Copy one night's raw frames and list helper into a new IRAF work directory."""
import argparse
from datetime import date
from pathlib import Path
import shlex
import shutil


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("night", help="Observing date: YYYY-MM-DD")
    parser.add_argument("--source", type=Path, help="Override EFOSpec/data/DATE")
    parser.add_argument("--runs", type=Path, help="Override EFOSpec/runs")
    args = parser.parse_args()
    try:
        if date.fromisoformat(args.night).isoformat() != args.night:
            raise ValueError
    except ValueError:
        parser.error("Use a valid observing date in YYYY-MM-DD format")
    source = (args.source or root / "data" / args.night).resolve()
    frames = sorted(source.glob("EFOSC*.fits"))
    if not frames:
        parser.error(f"No uncompressed EFOSC*.fits in {source}")
    helper = Path(__file__).with_name("list_raw_frames.py")
    if not helper.is_file():
        parser.error(f"Missing list helper: {helper}")
    parent = (args.runs or root / "runs").resolve() / args.night / "pessto"
    parent.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        work = parent / f"iraf-full-{number:02d}"
        try:
            work.mkdir()
            break
        except FileExistsError:
            number += 1
    for frame in frames:
        shutil.copy2(frame, work / frame.name)
    shutil.copy2(helper, work / helper.name)
    print(f"Prepared {len(frames)} raw copies; no reduction started.")
    print("Next, enter the new directory:")
    print("cd " + shlex.quote(str(work)))


if __name__ == "__main__":
    main()
