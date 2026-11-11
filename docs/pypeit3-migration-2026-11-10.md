# EFOSpec / PypeIt 3 migration and 28 October benchmark

User-authorized scope: upgrade the existing `efospec` conda environment to
PypeIt 3.0.0; adapt its EFOSpec integration; rebuild raw calibrations and test
native spectral flexure on 28 October, starting with SN2026aebl and AT2026agvs.
No current science product or pointer is promoted by this benchmark.

## Implementation plan

- [x] Snapshot source/tests/dependency declarations, uncommitted diff, environment
  exports and 1,114 selected product/report/pointer hashes in
  `runs/2026-10-28/QC/pypeit3-migration-20261110T131246Z`.
- [x] Clone the old runtime to `efospec-pypeit114-preserved-20261110` before mutation.
- [x] Upgrade PypeIt, NumPy, SciPy, Astropy and Matplotlib together; verify imports
  and `pip check`; update `pyproject.toml`, constraints and installer assertions.
- [x] Exercise real calibration, extraction, local-sky, recipe and correlation
  boundaries with existing tests first; adapt only demonstrated API changes.
  Add regression coverage for correlation sign/units, fixed-support injected
  shifts and incompatible calibration/recipe version rejection.
- [x] Retain historical 1.14 recipes as historical inputs; new recipes record the
  executing engine. Never claim an old recipe was replayed by the same engine
  under 3.0. Never load old Slits/Flat calibrations into the new engine.
- [x] Rebuild the selected raw calibration groups into a fresh 28 October
  revision. Preserve source-selection/background policy and propagated planes.
- [x] Extract at the object location, run PypeIt's native boxcar flexure, compare
  reference models and wavelength intervals, measure actual line width, inspect
  QA and detector stamps, and test positive/negative fixed-support injections.
  Retain rejected/unmeasurable trials and uncertainty limits explicitly.
- [x] Compare held-out sky information; distinguish a diagnostic shift from an
  independently justified correction. Do not force the 6363 line to the fitted shift.
- [x] Run appropriate numerical/integration checks, verify protected hashes and
  document measured results, compatibility changes and unresolved limitations.

## Execution decisions

Work stays in the user-selected EFOSpec checkout, with its extensive uncommitted
work backed up; neither legacy baseline is edited. The implementation initially excluded commits and pushes; the user subsequently authorized a GitHub push.
The user explicitly selected the in-place environment upgrade over the previously
suggested separate test environment; the preserved clone supplies rollback and
historical-engine access. No new approval gate is added to this accepted scope.

PypeIt 3.0 requires NumPy >=2.4.1 and Astropy >=7; existing NumPy-1 declarations
must change. Versions will be pinned to the resolved, verified Python-3.11 stack.
Focus checks on observable science/serialization behavior, not version-string
text alone. The three-line acceptance thresholds remain project policy.

## Installed runtime and compatibility

The existing `efospec` environment now imports PypeIt **3.0.0**, NumPy **2.4.6**,
SciPy **1.17.1**, Astropy **7.2.3** and Matplotlib **3.11.2** under Python 3.11.
`pip check` reports no broken requirements. The original engine and stack still
import in `efospec-pypeit114-preserved-20261110` (PypeIt 1.14.0 / NumPy 1.26.4).
The clone's editable EFOSpec entry still points at the working checkout; use the
saved source snapshot when reproducing historical code, not the clone alone.

Demonstrated API changes were adapted: calibration construction and success
initialization; `dispersion` in wavelength fitting; the extra background sky
plane in `Extract.run`; `BOX_R_PIX`; required Spec2D background model; iterative
B-spline basis/mask/knots; `AtmosphericExtinction`; and archive-standard `Spectrum`
objects with an explicit empirical archive list. Half-pixel spectral slit bounds
preserve first/last detector rows. Old extraction-calibration groups and native reidentification templates are
rejected before FITS load; the separate master-validation entry point also
requires the calibration run's engine version;
old recipes and sky-mask replay require their recorded engine. Historical records
were not relabeled as 3.0 products.

PypeIt 3 always renders source-finding QA, including a literal `#` in its slit
title. A scoped LaTeX preamble permits that character while preserving mandatory
LaTeX and restoring the caller's rcParams. No site-packages were edited.

Ruling: preserve the previous B-spline-continuum comparison as an explicitly named
EFOSpec diagnostic, with `continuum_method='native'` selecting unmodified PypeIt 3.
The native percentile-clipped algorithm is biased on our sparse noiseless optical
fixture; silently treating it as the previous algorithm would change the numerical
contract. Both backends record their method and always return `applied=False`.
This does not establish the old red-window diagnostic's absolute accuracy.

## Fresh calibration and four-exposure benchmark

All evidence is additive under
`runs/2026-10-28/QC/pypeit3-migration-20261110T131246Z/`.
The raw associations use the existing selected bias frames (26 October), and
28 October observing-night flats/arcs; they are not all same-night biases.

- Gr13 slit1.5: `calibration-gr13-v3/`; 17 identified lamp lines; fit RMS
  **0.520 A**, held-out RMS **0.387 A** (fit RMS 0.0945 pixel).
- Gr11 slit1.0: `benchmark-v1/calibration-gr11/`; 18 lines; fit RMS
  **0.1676 pixel**, held-out RMS **0.1914 pixel**, maximum held-out residual
  **0.4171 pixel**. These are arc checks, not science-flexure validation.
- `benchmark-v1/benchmark.json`: fresh object-local boxcar extractions, native
  `spec_flexure_slit(method='boxcar')`, measured-sky-width comparisons, Paranal
  and generated-model templates, optical/red subwindows, and fixed-support
  coordinate injections at -10, -5, 0, +5 and +10 A. All 130 requested comparisons returned measurements; 20 candidates exceed the
  project's 20 A limit and 11 differential injection errors exceed 3 A. These
  counts pool templates, windows and deliberate injections, not a success rate.
  Unmeasurable windows and rejected candidates are retained.
- The four new exports are **unvalidated counts with unshifted arc wavelengths**.
  They do not replace accepted or provisional flux deliveries.

Full supported-range Paranal comparisons using the measured sky FWHM:

| Exposure | Grism | Candidate additive air correction (A) | Maximum differential injection error (A) |
| --- | --- | ---: | ---: |
| SN2026aebl | Gr13 | -4.46 | 0.53 |
| AT2026agvs | Gr13 | -4.34 | 1.14 |
| SN2026abgb | Gr13 | -4.06 | 0.66 |
| AT2026agzp | Gr11 | -4.06 | 0.60 |

Here the differential error is `C(delta)-C(0)+delta`: the expected response to an
added coordinate offset is the opposite change in correction. It tests sensitivity,
not absolute zero point. The native object-local stage uses the arc-derived FWHM
and returns respectively -0.8627, -0.9197, -0.6325 and -0.9512 pixels; these are
separate measurements, not conversions of the table above. PypeIt's search limit
is in pixels: 20 pixels is not the project's 20 A correction limit.

Some narrow windows fail badly: for AT2026agvs the 6800-7400 A zero-injection
candidate is about +94 A, and the disjoint 6800-8000 A +10 A injection aliases to
about -119 A. Blue disjoint windows can also give a biased zero point despite
responding to injections. Neither template choice nor injection response alone
justifies adopting a correction. The generated model is a near-IR reference;
its failure does not establish an optical wavelength error.

## Native pixels, line profiles and held-out information

`validation-v1/validation.json` fits unresampled detector pixels with propagated
raw inverse variance and masks, excluding primary/neighbour traces. It compares
Gaussian and uniform-slit-convolved Gaussian profiles with pixel integration,
free oxygen centroids/amplitudes, and separate left/right sky regions. The two
profile families give similar discrepancies, so interpolation is not a sufficient
explanation. The PESSTO setup-template comparison is retained with an explicit
legacy air-wavelength assumption; it is not an independently certified reference.

An exploratory blend hypothesis is recorded in `blend-hypothesis-v2/` and tested
more strictly in `heldout-blends-v1/heldout.json`: excise oxygen from the high-resolution
Paranal template, convolve the other sky components to the slit/5577 profile,
train their amplitude with 6300 on **6240-6332 A**, then freeze it before fitting
6363 on **6332-6425 A**. The oxygen centroids and amplitudes remain free; no
separation or 3:1 intensity constraint forces agreement.

For AT2026agzp the all-region corrections are **-5.22 / -4.75 / -6.20 A** at
5577/6300/6363. Both spatial sides also meet the existing 3 A consistency limits;
reduced chi-square is about 1. Conditional synthetic controls (20 noise realizations
per spatial sample) recover an injected common offset under this same model.
This supports unresolved sky blending as a contributor for this exposure.
It does not independently calibrate the template or include flat/profile/line-ratio
systematics, and it is not yet a production estimator.

The Gr13 results remain inconsistent: SN2026aebl fails the held-out comparison
on the left; AT2026agvs fails anchor consistency in the combined/left samples;
SN2026abgb fails the held-out comparison and has substantial spatial/model
residuals. No target is promoted on this exploratory analysis.

Ruling: retain all four current provisional deliveries and all existing acceptance
limits. The upgrade succeeds as an engine migration and diagnostic benchmark;
the general wavelength-calibration issue remains unresolved. Next scientific
work is to constrain neighboring sky-line ratios/shape from uncontaminated
intervals and inspect spatial contamination/flat residuals, then validate the
held-out line across spatial samples before introducing a production estimator.
A manual `pypeit_identify` arc review remains available if lamp identifications
are questioned; these arc residuals do not currently identify it as the primary
failure.

## Evidence and verification

- `tests-old-engine-baseline.log`: 45 pre-migration focused tests passed.
- `tests-adaptation-5.log`: 55 focused compatibility checks passed.
- `tests-correlation-bspline.log`: 11 correlation/sign/injection checks passed.
- `tests-final-boundaries-2.log`: 5 tests passed for mandatory-LaTeX native QA,
  physical response closure, exact sky-mask replay/version rejection and joint
  revision export/replay.
- Fresh independent review found no actionable migration regression; its focused
  run passed **46 tests** across migration, local-sky, native-processing, recipe
  and saved-diagnostic tests. Review did not independently validate the real-data
  scientific conclusions.
- `tests-template-version-after.log`: **15 passed**, including the final separate
  native-template version gate (new records explicitly save the engine version).
- A final audit added the corresponding engine gate to the separate native
  master-validation loader; `tests-final-version-guards.log` covers both paths.
- CLI help and actual desktop-runtime import probe succeed under the new
  environment. This is not a new desktop-platform interaction acceptance run.
- Added-line whitespace/conflict checks are clean. `git diff --check` still flags
  the pre-existing final blank line in `tests/test_local_sky.py`; it was preserved.
- Broad full-suite result: **399 passed, 1 pre-existing failure** in 906.86 s
  (`tests-full-2.log`). The later final version-gate checks passed **16 tests**
  in 3.47 s (`tests-final-version-guards.log`).
- A report test already fails on the pre-migration source and preserved runtime:
  it requires inline JPEG while the existing compact bundle uses WebP. Reproduced
  in `tests-preexisting-report-2.log`; unrelated report behavior is preserved.
- `preservation-verified.json`: **1,114 protected files and 28 unique raw inputs
  checked; zero changes**. This includes current pointers, accepted/provisional
  science deliveries, and selected reports for 28/29 October. Only 28 October
  science processing was invoked.
- `figures-v1/`: inspected PDF + 300-dpi JPG injection, line-consistency,
  native-pixel grayscale and arc QA, plus a separate static comparison page.
- Source/test snapshots, environment exports, failed attempts and generation
  scripts remain in the evidence directory. No commit or push was made during the initial benchmark; publication is recorded below.

## Upstream references

- [PypeIt 3.0.0 release](https://github.com/pypeit/PypeIt/releases/tag/3.0.0).
- [Versioned flexure implementation](https://github.com/pypeit/PypeIt/blob/3.0.0/pypeit/core/flexure.py).
- [Versioned flexure documentation](https://github.com/pypeit/PypeIt/blob/3.0.0/doc/calibrations/flexure.rst).
- [Wavelength calibration / manual identification](https://pypeit.readthedocs.io/en/release/calibrations/wave_calib.html).


## GitHub publication scope

The migration commit contains the PypeIt 3 compatibility changes, the response
spline needed by that port, tests and migration documentation. Earlier uncommitted
nightly-report, background-selection, redshift and rescue work was initially kept local.
The 399-test full-suite result and observed-data benchmark above describe the
complete working checkout saved in the evidence snapshot; they are not a claim
that its other pending changes are included in the migration commit. The scoped
publication passed **99 tests** in a separate exported checkout: 56 migration/
extraction/response/replay checks, 35 adapter/recipe/desktop/rapid checks and
8 raw-calibration/end-to-end checks. `git diff --cached --check` is clean. Observed data,
calibration products, environment clones and local `runs/` evidence are not
published to GitHub.

## Full nightly reductions and follow-up publication

Fresh PypeIt 3.0.0 raw calibrations, extraction and same-night standard responses
were subsequently run in separate dated invocations:

| Observing date | Selected revision | Science flux exports | Reduction errors |
| --- | --- | ---: | ---: |
| 2026-10-28 | `20261110T170405Z-b97078` | 4 | 4 |
| 2026-10-29 | `20261110T171353Z-aa76fb` | 6 | 0 |

Both reports are complete; both reduction manifests remain explicitly partial
because six filtered/red exposures per night are unsupported by this flux route.
On 28 October, SN2026ayt C2 additionally fails fitted-trace background support;
its preserved 1.14 spectrum is shown alone in the comparison. The other failures
remain background convergence or sky-line consistency failures. An exported
SN2026aebl spectrum still carries the independent wavelength uncertainty discussed
above. Successful execution does not resolve that scientific concern.

The reproducible plotter is `scripts/compare_pypeit_reductions.py`. It takes one
date, explicit old/new reduction directories and a fresh output directory. It
matches raw-exposure hashes, plots the delivered air-wavelength grids without
extra shifts or normalization, uses actual exposure time and median SNR in each
title, and reduces horizontal panel spacing by 10%. Final PDF/JPG pairs and
provenance are retained in each date's `QC/pypeit3-overlay-20261110-v1/`.
All 881 files in the two comparison baseline revisions were unchanged after
the new reductions.

The follow-up package publication includes the same-night workflow, bounded
background selection, report assets, redshift evidence, provisional rescue route,
comparison plotter and their tests. Scientific rejection checks remain active.
The authorized cleanup concerns superseded generated QC outputs, not those
checks or accepted spectra; see the dated cleanup record in
[the epoch workflow](epoch-workflow.md#qc-cleanup-after-the-pypeit-3-reruns).

Publication verification on 11 November: wheel and source archive builds succeed,
`pip check` is clean, and added-line whitespace and changed documentation links
pass. The full suite completed with **402 passed and one failed** in 718 s:
the macOS launcher subprocess crashed in Qt's native directory dialog. That test
passed alone; all **15 desktop/CLI/launcher tests** then passed together with the
documented `MPLBACKEND=Agg` test environment. The crash was not reproduced, and
this is not a claim that the initial full-suite run was clean. A first subset
invocation without the required plotting backend hit Tk/Qt fixture-setup errors;
the corrected invocation above passed. No launcher implementation was changed.
Logs are retained in each date's `archive/qc-cleanup-20261111/`.
