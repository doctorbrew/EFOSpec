# EFOSpec reduction and delivery review — 25 November 2026

Historical evidence: conclusions and commands describe the recorded run. For current operations, use the [reduction cookbook](../guides/reduction-cookbook.md).

Follow-up: the PypeIt CLI now implements reviewed delivery identity revisions and
strict archive checks; see [current delivery instructions](../guides/wiserep-delivery.md).
The findings below describe the state before that follow-up. Legacy limitations remain.

Original review status: calibration and archive packaging exist; consistent reviewed source-name
revision across both pipelines is **not delivered**. No science release or upload
was performed. This review covers current working trees, including pre-existing
uncommitted changes, rather than a branch diff.

## Findings

- **High: interactive legacy names can disagree with FITS headers.**
  `../pessto/trunk/bin/PESSTOWISE:203–214` accepts a replacement SN/AT name into
  `_object`; line 321 writes it to the upload table. That path does not update
  FITS `OBJECT` or rename associated files. Its separate `--correctobj` path
  calls `ntt.util.correctobject`, which edits the supplied FITS in place.
  Neither is a complete immutable identity-revision operation.
- **High: PypeIt has no delivery identity-revision operation.**
  `src/efospec/delivery.py:37` deliberately rejects a manifest object differing
  from FITS `OBJECT`. The optional `iau_name` in `wiserep.py` goes into the
  upload table; it does not rename the FITS or change `OBJECT`. The desktop
  typing metadata also preserves its original object/path/hash identity.
  Correcting only the JSON cannot satisfy the requested SN/AT workflow.
- **Medium: there is no common packager for both product formats.**
  `delivery.py:27` requires EFOSpec four-band FITS with a `VALID` extension.
  Legacy primary-only IRAF spectra are intentionally rejected. Continue using
  PESSTOWISE on disposable copies for legacy delivery, or implement an explicit
  legacy adapter with its own uncertainty and wavelength validation.
- **Scientific acceptance remains separate from execution.** The retained
  [PyRAF validation](../../../pessto/docs/pyraf-validation.md) reports suspect
  automatic apertures, wavelength-dependent Gr11 residuals and invalid Gr11
  uncertainties. The environment repair does not resolve those findings.
  PypeIt's archive bridge explicitly uses archived IRAF calibration products;
  only its raw calibration path is independent of those products.

## What is implemented

- Header-based inventory and calibration association; filenames alone do not
  decide whether an input is science, an arc or a flat.
- Legacy-compatible names:
  `tAT2024afzf_20261028_Gr13_Free_slit1.0_1_f.fits` for rapid products;
  full legacy products also include the processing MJD before the counter.
  `_ex`, `_f`, `_2df` distinguish extraction and calibrated products.
- Wavelength calibration and physical flux calibration in both engines.
  EFOSpec export records air/topocentric wavelengths, flux units, extraction
  bands, provenance, calibration source and quality. Rapid status does not
  imply ESO Phase 3 certification.
- Separate public/private PESSTOWISE-compatible TGZs in the EFOSpec CLI,
  plus optional ZIP with audit sidecars. Use TGZ for the supplied ingest format.
  See [delivery instructions](../guides/wiserep-delivery.md). Packaging is an explicit
  reviewed step, not an automatic consequence of completing a reduction.
- Four supplied reference TGZs, containing 15 spectra, pass the local validator.

## Required naming behavior

- Use the reviewed TNS identity: `SN2023ixf` for a confirmed supernova;
  `AT2023ixf` for a TNS transient without a supernova classification. Preserve
  the survey designation if it has no TNS identity. Never invent a TNS name
  from a classifier result. This is also the policy printed by PESSTOWISE.
- A future identity revision should bind the exact input hash to reviewer and
  identity evidence, preserve `ORIGOBJ` and provenance, update `OBJECT` and
  any corresponding target cards, and consistently rename associated copies.
- Keep arrays, wavelength convention, masks, units and calibration status
  unchanged; regenerate checksums, ASCII references and delivery manifests.
  Raw inputs and accepted products must remain immutable. Release authorization
  and public/private access remain separate from SN/AT classification.

## Environment repair

- `pessto` originally contained Intel Python 3.7 and failed with
  `Bad CPU type in executable` on this ARM Mac. Its local platform configuration
  selected `osx-64`. Rebuilt it with independent ARM Python 3.11, PyRAF 2.2.4,
  NumPy 1.26.4, Astropy 6.1.7, SciPy 1.14.1 and Matplotlib 3.9.4, using
  `../pessto/constraints-pyraf.txt` and editable `../pessto/trunk`.
- The intended backup command failed because unqualified `python` was absent;
  the following Conda command removed the old broken environment before failing.
  The old Conda environment was **not preserved**. The separate `.venv-pyraf`,
  original pipeline checkout and reduction data were retained.
- Re-creation used explicit `--platform osx-arm64`. The rebuilt environment's
  `.condarc` now pins `subdir: osx-arm64`. Environment activation hooks set
  lowercase `iraf=/usr/local/lib/iraf/` and restore its previous value on
  deactivation (see follow-up below). No global Conda settings were changed.
- PypeIt uses the existing **`efospec`** environment, not `efosc`.
  Python 3.11, PypeIt 3.0.0, NumPy 2.4.6, SciPy 1.17.1 and Astropy 7.2.3
  import successfully. Its dependencies needed no repair.

```sh
# Legacy reduction (activate in a fresh shell, outside another virtualenv)
conda activate pessto
PESSTOFASTSPEC --version
PESSTOWISE --help

# PypeIt reduction, from EFOSpec
conda activate efospec
python scripts/reduce_epoch.py YYYY-MM-DD
```

## Verification

- Both environments: `python -m pip check` passes.
- EFOSpec: 106 focused tests pass across delivery, archive packaging, native
  calibration/wavelength/flux acceptance, extraction, naming/inventory and
  PypeIt 3 compatibility. Tests include synthetic data and real PypeIt calls;
  they do not constitute a fresh full-night raw-data reduction.
- PyRAF: all 11 existing tests pass, including real IRAF wavelength-cache and
  telluric sigma arithmetic regressions. CLI version and packaging help work.
- Saved 2026-10-28 PypeIt science spectra pass `inspect_product`; the count-only
  review spectrum is rejected. Older QC revisions were inspected separately,
  not selected together for delivery.
- Fresh rapid PyRAF reduction: AT2024afzf, observing night 2026-10-28,
  Gr13/Free/slit1.0. Exit zero, original raw SHA-256 unchanged, all four bands
  finite, sigma positive, ASCII wavelength and flux agree with FITS.
  Evidence: `runs/2026-10-28/pyraf/environment-check-20261125-fast/verification.json`.
- Fresh full PyRAF replay of the previously tested Gr13 case: 21 raw inputs
  through full 2D calibration, then two science/standard inputs through full
  1D extraction and flux calibration. Both exit zero and preserve input hashes.
  Final AT2024afzf telluric-corrected FITS has finite bands, positive sigma and
  matching ASCII wavelengths/flux. Evidence is in sibling
  `environment-check-20261125-full2d/` and `environment-check-20261125-full1d/`
  directories (`verification.json`, `reduction.log`, and full1d `output-check.json`).
  Runtime freezes are retained in the fast-check directory.
- GUI interaction, source identity, independent wavelength accuracy, absolute
  flux accuracy, Linux operation and remote ingest were not certified here.

Review anchors: EFOSpec HEAD `1a937fac2bc2185c706d9da0bb02c4ffbecabe2a`;
legacy HEAD `f3de549f050431d808e3037945cd267c6e2320a8`, plus working trees.
The ESO [PESSTO release description](https://cdn3.eso.org/sci/observing/phase3/data_releases/pessto_dr3.pdf)
also documents object/date/setup/processing-MJD/counter naming for released
products; those binary-table Phase 3 products are distinct from rapid ingest FITS.


## Follow-up: interactive startup and two science spectra

- Interactive `pyraf` reaches its prompt through both `conda run` and a fresh
  Zsh `conda activate pessto`; `noao`, `imred` and `specred` load. Tk 8.6 window
  creation/event processing also passes. The user's earlier startup error was
  not captured, so its exact cause is not established.
- Corrected a stale Conda executable path in local `.zshrc`, retaining backup
  `.zshrc.before-pessto-fix-20261125`. Its fallback had allowed activation during
  this check, so the typo alone does not explain the reported failure.
- Found Conda `envvars_force_uppercase=True` converting the configured `iraf`
  variable to `IRAF`. Replaced that entry with environment-specific activation
  and deactivation hooks. Verified lowercase `iraf` and restoration of an
  existing value after deactivation. Start a fresh terminal and activate
  `pessto` to load these changes.
- Replayed **AT2024afzf and AT2026aeul**, observing night **2026-10-28**, using
  22 raw science/standard/calibration inputs, Gr13/Free/slit1.0 and vma2.
  Full 2D and full 1D both return zero; all input hashes remain unchanged.
  Both final four-band spectra are finite, have positive statistical sigma,
  physical flux units, and matching FITS/ASCII wavelengths and flux.
- **Not release-approved:** AT2026aeul's automatic aperture is at spatial pixel
  80.18 while the strongest median spatial-profile peak is at pixel 453.
  The legacy `apall` automatic finder has no expected-central-position constraint
  in this path. This warrants source/trace review, not automatic substitution
  of the strongest peak. Both source identities remain unverified. Internal
  sky-line measurements are retained in JSON; absolute flux accuracy and
  physical cursor/DS9 interaction were not certified.
- Evidence: `runs/2026-10-28/pyraf/two-spectra-check-20261125-full2d/` and
  `two-spectra-check-20261125-full1d/`, each with `reduction.log` and
  `verification.json`; the latter also contains `output-check.json`.
  All 11 legacy regression tests and `pip check` pass after the startup changes.
