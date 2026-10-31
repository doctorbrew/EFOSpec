# Recent-night validation

- Scope: two most recent complete EFOSC2 nights returned for the programme.
- Authenticated ESO downloads succeeded, including proprietary science frames.
- Raw data, target metadata, logs, plots, and products remain Git-ignored.
- Public record: aggregate outcomes and reproducible commands only.

| Observing night | Verified files | Products | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-28 | 193 | 7 | 11 | 2 |
| 2026-10-29 | 203 | 5 | 10 | 3 |

- Files include acquisitions and associated raw calibrations from other dates.
- Reduction counts include science and standard exposures.
- Products: **7 science spectra and 5 standards**, all experimental.
- Stops: 11 sky-flexure failures, 3 source-selection failures, 7 unsupported-filter failures.
- Skips: 5 Gr16 exposures; the archive bridge enables Gr11/Gr13 Free only.
- The independent 6363 Å check passes for 8/12 products; 4 lack a passing check.
- Nominal-position target identities remain unverified.
- No scientific thresholds or target-selection rules were relaxed.

## Fixes and checks

- Inventory now records initial dome-flat template exposures as `flat_test`.
- These exposures no longer block preflight and cannot fill a master-flat group.
- Classification requires `DOME`, `CALIB`, `SPECTRUM`, the exact flat-template ID, and exposure number 1.
- Basis: observed template sequencing and the [ESO flat-template description](https://www.hq.eso.org/sci/facilities/lasilla/instruments/efosc/inst/CalSpecLongSlitFlats.html).
- Plot metadata now preserves decimal slit widths; repeated-target records remain distinct.
- Both regressions reproduced before their fixes; the updated suite passes **133 tests** locally.
- Local Python coverage: **90.41%**; remote badge metrics may differ.
- Both nightly reports contain all expected spectrum, trace, and spatial-profile figures.
- Download hashes/FITS checksums, product units/masks, raw immutability, and report links were checked.

## Reproduce locally

```sh
python -m efospec download 2026-10-28 --programme 117.29T8.002 --with-calibrations
python -m efospec download 2026-10-29 --programme 117.29T8.002 --with-calibrations
python -m efospec native-readiness data/2026-10-28
python -m efospec native-readiness data/2026-10-29
```

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec reduce-rapid data/2026-10-28 \
  --output runs/2026-10-28 --include-standards
```

- Repeat with `2026-10-29`; use a fresh output directory for reruns.
- Reports: `runs/<date>/index.html`; current report status: `runs/<date>/report.json`.
- Private detailed checks: `runs/latest-nights-validation.json`.
- A failed exposure returns a nonzero run status while retaining completed products.
- `native-readiness` still returns nonzero: raw candidates exist, native execution does not.

## Remaining acceptance work

- Implement masters, wavelength fitting, and observed-standard sensitivity from raw data.
- Validate weak-sky/short-standard exposures against contemporary raw arcs.
- Add explicit source selection for exposures that cannot be associated automatically.
- Validate additional grisms/filters before enabling them.
- The current successful runs execute no IRAF/PyRAF, but still import archived IRAF calibrations.
