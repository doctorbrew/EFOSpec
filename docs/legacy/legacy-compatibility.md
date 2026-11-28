# Legacy IRAF / Python 3.11 check

**Result: not verified end to end; not self-contained.**

## Local checks — 2026-10-31

| Check | Result |
| --- | --- |
| Interpreter in the `pypeit` environment | Python 3.11.9 |
| Python 3.11 syntax scan | Passed: 25 legacy modules and entrypoints |
| Import this checkout's `trunk/src/ntt` | Passed |
| Import `pyraf` in that environment | Failed: module not installed |
| Existing `pessto` environment | Python 3.7.12, x86_64 (metadata); launch fails: bad CPU type |
| IRAF commands on the current PATH | `cl`, `irafcl`, `mkiraf` found |
| Display commands on the current PATH | `ds9`, `xgterm` found |
| Legacy science reduction under Python 3.11 | Not run / not validated |

- Imports ran from a temporary directory; no science files were modified.
- Executables on PATH do not establish working IRAF packages or graphics.
- The old environment's launch failure is an architecture issue, not proof of Python 3.11 incompatibility.
- No environment upgrades, installations, or legacy-code patches were performed.

## External requirements

- Python dependencies: PyRAF, NumPy, Astropy, Matplotlib, and legacy `ntt`.
- IRAF runtime: configured installation and its reduction packages.
- Interactive operation: working display/graphics support, such as DS9 and X11/Tk.
- Scientific inputs: appropriate calibration frames or archived references.
- Some legacy options require human aperture, background, or line-identification choices.

[PyRAF's installation guide](https://github.com/iraf-community/pyraf#installation)
requires IRAF and Python separately. Modern Python support in PyRAF does not
certify this entire legacy pipeline.

## What the code actually calls

- `trunk/src/ntt/efoscfastspecdef.py`: imports PyRAF; calls IRAF reduction tasks.
- `trunk/src/ntt/util.py`: interactive `apall` tracing/background/extraction.
- `trunk/src/ntt/efoscspec2Ddef.py`: full-profile bias/flat and wavelength steps.
- `trunk/setup.py`: checks for dependencies; does not bundle IRAF.
- `PESSTOFASTSPEC -i`: requests interactive reduction; unattended operation is a separate claim.

## Gate for claiming Python 3.11 support

1. Build a separate, architecture-compatible legacy environment.
2. Verify IRAF task loading and graphics/cursor interaction.
3. Run a copied template dataset in a fresh scratch directory.
4. Compare wavelengths, flux, uncertainty, aperture choices, and output headers.
5. Record exact versions and external prerequisites.

Keep this separate from the validated PypeIt environment.
