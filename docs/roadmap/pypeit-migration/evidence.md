# Inspection evidence — 2026-10-30

## 2024-11-14 rapid reduction demonstration

The user selected **2024-11-14 EFOSC2**, not the similarly dated NOT dataset.
The completed run is `runs/2024-11-14-pypeit-rapid`; the standard check is
`runs/2024-11-14-pypeit-standards`. Both are local ignored artifacts. The
reproduction commands are in [EFOSPEC.md](../../../EFOSPEC.md).

All **13 science exposures** (nine Gr13, four Gr11) produced native PypeIt
spec1d files, four-band flux FITS products and two-column ASCII spectra.
The saved native spectra were read back with `SpecObjs.from_fitsfile` and their
counts compared exactly. Names follow the historical rapid convention, e.g.
`tSN2023xxj_20241114_Gr13_Free_slit1.0_1_f.fits`. No IRAF or PyRAF executed.

This is an explicit archive bridge, not native calibration generation:

1. Fit a spatial-order-3/spectral-order-4 Legendre surface to the processed
   archive arc's IRAF line positions, in air Å. Gr13 fit RMS is 0.406 Å and
   held-out-line RMS 0.410 Å; Gr11 values are 0.224 Å and 0.269 Å. These tests
   validate conversion of historical IDs, not a new raw arc measurement.
2. Measure each science exposure's offset using sky lines 5577.338 and
   6300.304 Å. Shifts are +36.77 to +37.97 Å (Gr13) and +45.46 to +46.36 Å
   (Gr11). The independent 6363.776 Å line is measurable in 11 exposures;
   all residuals have magnitude ≤1.05 Å. AT2024zzu and AT2024aamn lack a
   sufficiently significant independent line and retain that failed check.
3. Apply the legacy rapid trim/no-bias/no-flat policy. Convert ADU to electrons
   with header gain 0.91 e-/ADU and read noise 7.8 e-. PypeIt performs source
   finding, tracing, B-spline sky subtraction and optimal/boxcar extraction in
   a 141-pixel spatial window. Other detected sources participate in the model.
4. Use vacuum wavelengths internally, then export topocentric air wavelengths.
   Convert the archived logarithmic response using gain, exposure, local
   dispersion and the same rapid `extinction_lasilla.dat`. The selected
   `sens_2DR` references match the eight legacy baseline products. Apply
   flux-conserving bin-overlap resampling and squared-weight variance; record
   invalid bins and the absence of stored covariance.

Eight target positions come from historical aperture geometry, without using
legacy flux during extraction. AT2024aawp, AT2024abbv, SN2024tvg, AT2024abek and
AT2024zzu use nominal acquisition positions and remain unverified associations.

| Science target | Grism | Median native S/N per pixel | New / legacy median flux |
| --- | --- | ---: | ---: |
| AT2024aawp | Gr13 | 6.48 | no baseline |
| AT2024abbv | Gr11 | 72.87 | no baseline |
| SN2024tvg | Gr13 | 27.96 | no baseline |
| AT2024abek | Gr13 | 19.03 | no baseline |
| AT2024zzu | Gr11 | 12.40 | no baseline |
| AT2024aamn | Gr11 | 14.08 | 1.110 |
| AT2024tvb | Gr13 | 5.35 | 0.812 |
| SN2024abbv | Gr11 | 81.89 | 1.071 |
| AT2024zcw | Gr13 | 3.47 | 1.206 |
| SN2024ztn | Gr13 | 47.92 | 1.046 |
| AT2024aatz | Gr13 | 9.79 | 1.077 |
| SN2023xxj | Gr13 | 17.80 | 1.125 |
| AT2024aatd | Gr13 | 18.06 | 1.134 |

S/N uses native good pixels in 4000–8500 Å, limited to each grism's coverage.
Flux ratios use 4300–6800 Å with positive legacy flux, excluding sky-line and
Halpha windows. No spectrum was renormalized to the legacy result. The ratios
range from 0.812 to 1.206, so numerical parity is **not** established. The two
largest differences involve low-S/N spectra and need extraction/background
review; they have not been tuned away.

Two L745a slit1.0 exposures pass the same reduction gates. Compared directly
with the archived `ml745a.dat` AB-magnitude reference (converted to physical
F_lambda), median extracted/reference ratios over 4300–6800 Å are **1.002
(Gr11)** and **0.943 (Gr13)**. The 16–84 percentile intervals are 0.958–1.039
and 0.909–0.977. This is a useful independent check of calibration units and
continuum scale, not a general absolute-flux certificate; narrow-slit losses
and nominal source association remain relevant. Four short standards fail the
two-line sky gate and are explicitly recorded as failures. The two Gr16
standard exposures are explicitly skipped because that grism is not supported
by this experiment. No missing check is silently replaced by a borrowed shift.

**47 tests pass** in the existing environment: the earlier 41 tests plus six
physical tests for response units, response coverage, flexure sign, rejection
of inadequate sky, flux conservation and propagated variance/masks. Every
successful extraction verifies its input SHA-256 afterward. Run manifests
include source snapshots/hashes and actual Python/PypeIt/NumPy/Astropy/SciPy
versions. `trunk/` and the original night remain unchanged.

Remaining scientific limits: no contemporary bias/flat/raw arc processing,
no telluric correction, residual red fringing, unvalidated second-order
correction, five target associations requiring review, no native spec2d or
spectral-resolution image, and no ESO Phase 3 validation. Outputs therefore
remain `EXPERIMENTAL` and `QUALITY=Rapid`. The next migration step is to supply
raw calibrations and implement/validate native calibration generation while
retaining these explicit reference and export contracts.

The logarithmic response convention is also described in the upstream
[IRAF sensfunc documentation](https://iraf.readthedocs.io/en/doc-autoupdate/tasks/noao/imred/kpnocoude/sensfunc.html).

## Initial audit

This document records the initial audit. Subsequent implementation and native
tests in the user's existing Conda environment are recorded in
[Existing-environment integration](pypeit-integration.md); those results
supersede the initial inventory-only status and proposed environment upgrade.

## Repository history

- Public fork: https://github.com/sPaMFouR/EFOSpec ; API verified
  `fork=true`, `private=false`, parent `svalenti/pessto`, default branch `master`.
- Local independent checkout: `/Users/avinash/Work/Reduction/EFOSpec` (renamed from `epessto+`).
  Repository contents are at that root, with no extra `pessto/` level.
- `origin` points to the public fork; `upstream` points to
  https://github.com/svalenti/pessto . Upstream MIT licence and history retained.
- Fork base: `2b4b28dca7b2360b1b6259bd46920aaa47054e63`.
- Existing parent checkout: `75eb12d9e1323bc7b34a6070f2fb7523b793f50d`.
  Changes between these commits are README/instruction files, not spectroscopy
  source. The parent's pre-existing deleted `Ptkplot.py` and untracked data are
  untouched. No migration changes have been committed or pushed.

The clone used the parent's object store as a transfer reference and dissociated
it; the child repository is independent, not a submodule or a linked worktree.
Do not add it to the parent with a broad `git add .`.

## Data inspection

The read-only inventory found 92 FITS files across `../pessto/pessto_test` and
`../pessto/2024-11-14`, recursively: 14 raw science spectra, 8 raw standard candidates,
36 non-spectroscopic images, and 34 processed products. No byte duplicates,
raw archive-identity conflicts, unreadable files or reported metadata issues
were found. This does not establish complete validity of all headers/pixels.

The installation sample contributes one raw Gr13 spectrum of LSQ12btn,
one imaging frame (`snunt121`, despite `DPR TYPE=STD`), one processed archived
arc, and one rectified LSQ12btn spectrum. The November tree contributes 13 raw
science spectra: nine Gr13 and four Gr11. Its eight standards cover Gr11/Free,
Gr16/OG530, Gr13/Free/slit1.0 and Gr13/Free/slit1.5 (two each).

All inspected raw images are 1030×1030 with 2×2 binning, `fastL`, gain
0.91 e-/ADU and read noise 7.8 e- in the headers. The inventory does not infer
that other detector modes work. Some processed frames retain raw-like ESO
headers; classification checks product markers and transformed WCS first.

No raw arcs, biases or flats were found in these two input trees. The bundled
upstream calibration library remains useful reference material, but was not
included as raw input in this count. Archive/master source details and conversion
need their own audit. No data were downloaded from ESO or published.
The two November ZIP archives contain reduced FITS products with no EFOSC raw
filenames; the installation TAR contains the same two raw files listed above.

Full local paths and file SHA-256 values are in ignored
`outputs/local-inventory.json`, regenerable using the command in
[EFOSPEC.md](../../../EFOSPEC.md). The repository contains no copied
raw science inputs.

## PypeIt evidence

GitHub's latest-release API reported PypeIt **2.0.1**, published 2026-03-24.
Inspected the source at that exact tag as well as the current release branch
(`826bad5cea8701ed58ad78ba913358e635bdf575`). Findings relevant to this migration:

- Gr4/5/6 arc templates only in `config_specific_par`.
- Setup identity lacks filter; standard typing depends on target strings.
- Binning is derived from CDELT1/2, so never feed rectified legacy products to
  raw setup as if those cards still describe binning.
- Read noise hard-coded at 10 e-, unlike the inspected raw header value.
- HeI/ArI default lamps need reconciliation with legacy HgCdHeNeAr references.
- Overscan documentation says disabled, but the driver's disabling line is
  commented out. Inspect effective parameter values in the pinned runtime.

Primary sources:

- [Release 2.0.1](https://github.com/pypeit/PypeIt/releases/tag/2.0.1)
- [Tagged EFOSC2 driver](https://github.com/pypeit/PypeIt/blob/2.0.1/pypeit/spectrographs/ntt_efosc2.py)
- [Instrument documentation](https://pypeit.readthedocs.io/en/2.0.1/spectrographs/ntt_efosc2.html)
- [Wavelength calibration](https://pypeit.readthedocs.io/en/2.0.1/calibrations/wave_calib.html)
- [Flux calibration](https://pypeit.readthedocs.io/en/2.0.1/fluxing.html)
- [Published package metadata](https://pypi.org/pypi/pypeit/2.0.1/json)

The existing `pypeit` Conda environment has Python 3.11.9, PypeIt 1.14.0,
Astropy 6.1.1 and NumPy 1.26.4. It was not upgraded. Published 2.0.1 metadata
requires Python >=3.11,<3.14, NumPy >=2.4.1 and Astropy >=7.0. A future separate
Python 3.12 environment is the proposed starting point; a working dependency
lock or actual PypeIt reduction has not yet been demonstrated.

## Lessons from the NOT–ALFOSC pipeline

Reviewed scripts/configurations under
`/Users/avinash/Work/Reduction/notreduce/base`, without modifying them or
opening upload notebooks. Reuse the stage separation and inspectable PypeIt
input files. Do not transplant these instrument-specific or unsafe assumptions:

- `scripts/create_datasets.py:32,43,74,86–111,130`: fixed binning, one setup per
  target, calibration sky-distance matching without sufficient setup constraints,
  and last-frame metadata. EFOSC2 needs its own explicit metadata/selection policy.
- `scripts/apply_fluxcal.py:10–19,28–34`: nearest-time sensitivity matching needs
  configuration, validity-range and missing-library checks.
- `scripts/combine_spectra.py:38–46`: trace nearest pixel 250 is not a general
  target association rule; extraction choice must be explicit and inspectable.
- `scripts/convert_spec1d.py:178–191`: inverse variance is written as `err` /
  `FLUX_ERR` while inverse-square-root conversion is commented out. Correct
  this in the new exporter; the NOT file itself is unchanged.
- `scripts/combinenew_spectra.py:157–189`: a custom wavelength/flux/ivar FITS
  table omits native masks and metadata; it is not automatically a valid PypeIt
  spec1d product.
- `scripts/convert_spec1d.py:39–58,133–161`: first-file header selection and broad
  extraction fallback can misidentify source details or objects. Use the manifest.
- `etc/sensfunc.par` and `telluric_ALFOSC.par`: reference observatory/extinction,
  fitting parameters and resolution conventions need EFOSC2-specific validation.

These are source-level observations, not a new numerical assessment of the NOT
reductions. Its staged workflow is valuable; its outputs are not an EFOSC2
calibration reference.

## Verification performed

`PYTHONPATH=src python3 -m unittest discover -s tests -v` passed **17 tests**
using both Python 3.9.6 / Astropy 6.0.1 and Python 3.11.9 / Astropy 6.1.1.
Tests include noon/year-boundary night naming,
real template filename, explicit full processing date, suffix collision handling
including >99, direct agreement with isolated legacy `util.readkey3`, rejection
of imaging standards/processed arcs, byte preservation, duplicate hashing,
archive-ID conflicts, corrupted FITS handling and missing/binning metadata.

A wheel built successfully with Python 3.11 / pip 24.0 and its packaged CLI
help ran directly from the wheel. The wheel contains the new modules and
upstream licence, without raw science data. The older system pip 21.2.4 build
incorrectly produced `UNKNOWN-0.0.0` using the local older build tooling; that
artifact was not used. Use a current pip in a separate environment for
installation. Neither existing Conda environment was upgraded.

Local documentation links resolve, `git diff --check` passes, and `trunk/` has
no tracked changes relative to the fork base.

The real inventory ran successfully on both supplied input trees. No scientific
reduction, flux/error comparison, legacy export, PypeIt instrument loading,
or calibration-quality benchmark has been run. Those remain explicit tasks.
