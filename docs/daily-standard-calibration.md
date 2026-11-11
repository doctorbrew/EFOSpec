# EFOSpec daily standard calibration

> Historical diagnostics: superseded QC outputs cited below were removed in the
> authorized 11 November cleanup. Retained reductions and their dependencies remain.
> See the [cleanup inventory and policy](epoch-workflow.md#qc-cleanup-after-the-pypeit-3-reruns)
> for which generated paths were retired; these historical paths are not current deliveries.

Latest follow-up: the [9 November rescue record](rescue-2026-11-09.md) delivers
four additional **provisional** 28 October spectra. Two background failures are
resolved; the science wavelength checks still fail. The accepted nightly
reduction and its acceptance gates remain unchanged.

## Implemented

New `efospec night DATE` revisions default to **same-night** responses. The
`reduce-daily` worker builds native raw bias/flat/arc calibrations, extracts the
standards with PypeIt, fits physical references through the existing native
response code, and applies a selected response to native science extractions.
The existing two-anchor plus held-out 6363 Å science wavelength gate and bounded
two-sided background gate remain unchanged.

- Matching requires the same noon-to-noon observing night, grism, filter, slit,
  binning and readout. Select the nearest successful standard exposure in MJD;
  ties fail. Standard selection is independent of the science `--target` filter.
- No archived sensitivity fallback. Both standard and science use native raw
  processing; no native response is applied to the old unflattened bridge counts.
- Current nightly flux support: Gr11/Gr13 Free, 2x2, slit1.0/slit1.5.
  Filtered standards and Gr16 remain separate diagnostic workflows.
- Short standards retain arc-only wavelengths. Their wavelength status, observed
  raw exposure/hash, physical reference, response/hash and extinction/hash follow
  the delivered spectrum. Unsupported response bins stay masked.
- Retain standard counts even if response fitting fails. Save failed extraction
  diagnostics and logs. Every attempted exposure has an explicit outcome.
- Compare distinct standard exposures in identical setups when available; retain
  transfer diagnostics separately from training closure. Neither establishes an
  independent absolute flux scale.
- Outputs remain experimental cgs flux density per air Å, topocentric. Variance
  follows the squared conversion and bin overlap; no second gain division is
  applied to a response fitted from electrons. Slit losses, tellurics, second-order
  contamination, response uncertainty and resampling covariance remain uncorrected.
- The nightly Calibration section includes response FITS downloads and actual
  spectrum-to-observed-standard associations. Unvalidated statuses remain explicit.

## Commands and compatibility

```sh
# New dated revision; default is same-night.
python scripts/reduce_epoch.py 2026-10-29

# Explicit legacy bridge for a new revision.
python scripts/reduce_epoch.py 2026-10-29 --flux-calibration archive

# Isolated trial, preserving nightly/current.json and the selected report.
python -m efospec reduce-daily data/2026-10-29 --night 2026-10-29 \
  --target AT2026aevu --output runs/2026-10-29/QC/NEW-daily-standards
```

Run one date per invocation. Separate `log`, `reduce`, and `report` steps retain
that revision's recorded policy; a policy change requires a new revision.
Old revisions without this field retain archive replay.

New revisions inherit hash-verified operator selections from the preceding
revision unless explicitly replaced. Native reselection retains only unchanged
raw-detector coordinates and the recorded identity; it refits the background on
fresh native pixels, checks two-sided support and checks the fitted trace against
the requested anchor. This does not replay an archive background or assert that
the two processed images are identical. SN2026aadx retains its confirmed C3
identity; background-only reviews remain unverified identities. No archive
recovery command is run against native failures.

Optional repeated `--calibration-group PATH` arguments reuse completed native
masters only when setup, associated raw hashes and processed-file hashes match.
Science/standard processing, extraction and response fits are rerun.

## Initial integration trials: 29 October 2026 (superseded)

These isolated trials did **not** replace either existing nightly report.

- `runs/2026-10-29/QC/daily-standards-20261108-v1/`: selected AT2026aevu plus
  matching Free/slit1.5 standards. VMa2 extracted and produced a contemporary
  response and experimental self-calibrated standard spectrum. Its response
  support is restricted; this is not a broad-band calibration acceptance.
  L745a failed bounded background support (a detected broad neighbour excludes
  both sides). AT2026aevu failed the 5577 Å centroid-error gate. No science flux
  spectrum was delivered. No held-out transfer was possible with only one fitted
  standard. The trial report and house-style PDF/JPG figures are retained.
- `runs/2026-10-29/QC/daily-standards-20261108-v2/`: selected AT2026ahax plus its
  matching Free/slit1.0 VMa2 standard. The standard failed background support;
  the science response selection then failed explicitly. No archive substitution.

These first trials established integration and failure handling. The full reruns
below supersede their extraction and response failures; their files are retained.

## Initial integration verification (superseded by full rerun below)

- Synthetic photons traverse real PypeIt raw masters, standard extraction,
  response fitting and science export. Recovered flux agrees with the known
  independent photon-rate ratio within the existing 8% integration tolerance;
  supported errors are finite and positive. Archived calibration reads are
  forbidden by the test.
- **74 focused tests passed**, including offline report/browser checks. Tests cover
  cross-night/setup rejection, failed-standard propagation,
  ties, changed response/raw/extinction bytes, default policy, old revision replay,
  report downloads and response tampering, plus native/filtered/report regressions.
- `verification.json` in each trial records preserved inputs/reports/pointers and
  calibration/product checks. Existing source changes were retained; no commit
  or remote publication was made.

## Full reduction debugging: 8 November 2026

Four reproducible defects prevented contemporary nightly delivery:

- **Background/object finding:** detecting sources before subtracting the sky
  mistook a background pedestal for broad neighbours. A bounded preliminary
  background now precedes source finding; the final model is independently
  refitted with finite bands on both sides. Both image mask and inverse variance
  exclude pixels outside the constrained preliminary-background region.
  PypeIt 1.14's collapsed spatial profile does not exclude pixels solely because
  their inverse variance is zero. No full-slit extraction-background fallback.
- **Sky-line profile:** uniformly illuminated slit lines are poorly described
  by the previous Gaussian-only fit. Native science now fits a projected uniform
  slit convolved with Gaussian blur. All interior calibrated slit columns, with
  bad pixels and the target core masked and spatial outliers clipped, contribute
  to wavelength measurement. This wider sky measurement does not change the
  bounded source-background bands. The 5577/6300 agreement, centroid-error,
  shift-size, S/N and independent 6363 residual limits remain unchanged.
- **Gr11 arc sampling and IDs:** the restricted atlas omitted useful blue IDs;
  the full physical ESO/NIST He–Ar list is now used. PypeIt's default six-column
  arc extraction was unstable for weak blue lines. A fixed 30-pixel band about
  the same slit centre yields 16 IDs in the previously failing group, RMS
  0.107 pixel, held-out RMS 0.140 pixel and maximum 0.362 pixel. Measured spatial
  shear across this band is only 0.026 pixel. Physical bounds, competing-solution
  rejection and held-out limits were not relaxed.
- **Sensitivity boundaries:** PypeIt 1.14's standard-zeropoint wrapper filtered
  padded B-spline knots using the stellar/telluric mask. This truncated real Gr13
  response support to about 30%. The response now uses PypeIt's zeropoint and
  iterative B-spline fitter with intact mathematical boundary padding, masks the
  data, and restricts delivery to the accepted continuum bracket. Internal bad
  intervals stay masked; no physical extrapolation is enabled. Real Gr13
  supported flux fractions are now about 97.5% of the arc-supported output grid.

These choices follow the documented order of
[PypeIt object finding](https://pypeit.readthedocs.io/en/1.14.0/object_finding.html)
and [sky fitting](https://pypeit.readthedocs.io/en/1.14.0/skysub.html), with
[B-spline sky modelling on unrectified pixels (Kelson 2003)](https://arxiv.org/abs/astro-ph/0303507).
The projected slit profile is an instrument-model inference checked against
measured EFOSC2 lines, informed by
[ESO's grism specifications](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/Efosc2Grisms.html)
and [Casini & de Wijn's slit-spectrograph analysis](https://arxiv.org/abs/1409.0137).
The same-night reference and extinction workflow follows
[PypeIt flux calibration](https://pypeit.readthedocs.io/en/1.14.0/fluxing.html);
[PESSTO's reduction description](https://arxiv.org/html/1411.0299v2) provides the
instrument-specific context. Our numerical limits and sampling widths are
project choices, not claimed prescriptions from those papers.

All six 29 October Free-filter science exposures pass in retained trials:
AT2026ahax, AT2026twd, SN2026afqd, AT2026aguc, AT2026aevu and SN2026aadx.
`daily-debug-20261108-full-v4` contains the Gr13 evidence;
`daily-debug-20261108-gr11-v5` contains the successful Gr11 rerun.
Separate standard transfers give Gr11 overall ratios 0.988/1.009 and Gr13
1.103/0.898. These measure internal transfer repeatability, not absolute
photometric accuracy; individual continuum bands differ more.

All three filtered standards and all three red exposures from 29 October also
extract in `filtered-debug-20261108-v4` and `red-debug-20261108-v4`. Their
portable reports contain counts spectra, trace/background plots and downloads.
Gr16 exposure-specific flexure remains unvalidated; no red flux spectrum is
promoted on the basis of a correlation-only shift.

## Delivered nightly reruns

The selected reports now point to new reductions. Earlier accepted products and
the original reports are retained; these are no longer just isolated trials.

| Observing night | Selected revision | Free-filter science flux | Standard flux | Additional optical review counts |
| --- | --- | --- | --- | --- |
| [2026-10-28](../runs/2026-10-28/index.html) | `20261108T180751Z-003407` | 4 of 8 | 6 | 2 |
| [2026-10-29](../runs/2026-10-29/index.html) | `20261108T175125Z-3b2c1f` | 6 of 6 | 6 | 0 |

- All 22 delivered flux spectra use **2026 same-night responses** with exact
  setup matching. No archived 2014 response was substituted. The six standard
  spectra per night are calibration products, not additional science targets.
- 28 October science flux: AT2026agwm (Gr11), SN2026ayt, AT2024afzf and AT2026aeul
  (Gr13). SN2026ayt retains the user-confirmed C2 raw-coordinate selection.
- 29 October science flux: AT2026ahax and AT2026twd (Gr11); SN2026afqd,
  AT2026aguc, AT2026aevu and SN2026aadx (Gr13). SN2026aadx retains C3.
- The remaining automatically chosen sources retain their unverified acquisition
  association; passing extraction does not establish astrophysical identity.
- Each final revision reused the hash-verified native master groups built by
  that night's immediately preceding full raw rerun. Standard/science processing,
  extraction and contemporary responses were recomputed. Both revisions survive.
- Separate `QC/filtered-debug-20261108-v4/` runs contain all seven filtered-standard
  counts extractions and experimental response fits (four on 28 October, three
  on 29 October). `QC/red-debug-20261108-v4/` contains all five Gr16 counts
  extractions (two on 28 October, three on 29 October, including AT2026twd).
  These outputs have their own portable reports; filtered/red files remain counts.

| Counts reports | 28 October | 29 October |
| --- | --- | --- |
| Gr13 / GG495 standards | [4 extractions](../runs/2026-10-28/QC/filtered-debug-20261108-v4/index.html) | [3 extractions](../runs/2026-10-29/QC/filtered-debug-20261108-v4/index.html) |
| Gr16 / OG530 | [2 extractions](../runs/2026-10-28/QC/red-debug-20261108-v4/index.html) | [3 extractions](../runs/2026-10-29/QC/red-debug-20261108-v4/index.html) |

The main observing log's unsupported-setup entries refer to nightly flux delivery;
the separate counts reports above record those exposures' successful extractions.

### Additional background fixes established on 28 October

- A real VMa2 slit1.5 fit exhausted PypeIt's 100-iteration budget. With the same
  degree-2 spatial model, one-pixel B-spline spacing, 4-sigma rejection and
  10-rejection limit, a 500-iteration ceiling converged: reduced chi-square 1.786,
  accepted fraction 0.982 and at least 23 samples on each side. This changes the
  convergence budget, not fit order or acceptance thresholds. Evidence:
  `QC/background-convergence-20261108-v1/`.
- AT2024afzf had one detector row whose masked pixels removed usable samples
  from one background side. The fitter now excludes that entire row from both
  sides and from delivery before fitting. It requires at least 90% usable rows
  and never fits a one-sided background. Row 137 is excluded; the remaining fit
  has reduced chi-square 0.926 and at least eight samples per side. Evidence:
  `QC/bad-row-background-20261108-v1/`.

### Remaining failures and explicit diagnostic products

Four 28 October exposures still fail the unchanged science wavelength gates:

| Exposure | Reproduced failure | Current deliverable |
| --- | --- | --- |
| SN2026abgb | 6363-A centroid error 3.33 A exceeds 1.5 A | Failed wavelength and background diagnostics |
| AT2026agzp | Held-out 6363-A residual -4.24 A exceeds 3 A | Counts only, unshifted arc wavelengths |
| AT2026agvs | 5577/6300 shifts differ by 3.189 A, exceeding 3 A | Failed wavelength/background diagnostics; separate conditional counts trial |
| SN2026aebl | 6363-A centroid error 2.57 A exceeds 1.5 A | Counts only, unshifted arc wavelengths; identity unconfirmed |

The two delivered review-count spectra are under the selected 28 October
revision's `reduction/wavelength-review/` and appear in its nightly report. Their
FITS files contain electrons per spectral pixel, `FLUXCAL=NONE`, and explicit
unvalidated wavelength status. They are not included among flux products.

The sky investigation in `QC/sky-line-review-20261108-v1/` retains full/left/right
slit measurements, fit-window trials, processed arrays and PDF/JPG profiles.
Changing subsets, fixing the blur or moving continuum windows can change some
decisions, but the results are not stable enough to justify a correction. No
post-hoc successful variant was substituted for independent validation.

For SN2026abgb and AT2026agvs, wider 401-pixel crops, wider preliminary sky bands
and explicit raw-coordinate geometry were also tested. SN2026abgb's clean-band
trial still fails spline convergence at 500 iterations, including a diagnostic
two-pixel knot spacing. AT2026agvs can yield numerical counts with hand-chosen
bands, but its right band includes a detected shoulder near raw spatial pixel
565. That fit is **not validated host/neighbour subtraction** and is not adopted
in nightly delivery. Source identity and wavelength also remain unvalidated.
The trials, scripts and non-adoption reason are retained in
`QC/wider-counts-review-20261108-v1/`, `QC/wider-seed-review-20261108-v1/`, and
`QC/reviewed-counts-20261108-v1/` / `v2/`.

Resolving these four wavelength failures requires a justified independent
measurement, potentially additional isolated sky features; resolving the two
background failures requires clean exposure-specific geometry or a validated
host/source model. Neither is replaced by a looser quality threshold. Gr16 still
needs independently checked red flexure, and absolute flux calibration still
needs external photometric validation. Slit losses, tellurics, second-order
contamination and response-model uncertainty remain outside this delivery.

### Reproduce and audit one night

Use the `efospec` conda environment and a working LaTeX installation for plots.

```sh
python scripts/reduce_epoch.py 2026-10-28
python scripts/verify_daily_reduction.py \
  runs/2026-10-28/nightly/20261108T180751Z-003407/reduction
# Render the selected revision again without recomputing spectra:
python scripts/03_report_epoch.py 2026-10-28
```

The first command creates another retained revision; it does not overwrite the
listed reduction. Run a different date in a separate explicit invocation.
`verify_daily_reduction.py` audits saved response associations, input/master
hashes, supported flux/error samples, FITS checksums and wavelength conventions,
independent science sky validation, two-sided background support and complete
exposure accounting. It checks that review counts cannot masquerade as flux.

### Final verification

- **110 focused tests passed** on the final implementation, covering native
  processing, arc and sky validation, daily standard selection and flux scaling,
  reviewed-source inheritance, bounded backgrounds, extraction, nightly and
  filtered workflows, report generation and plotting integration. The complete
  test log is saved in each selected revision's `verification/focused-tests.log`.
- Saved-product audits passed: 28 October has 10 flux files, 45 associated raw
  files and five native calibration groups; 29 October has 12 flux files,
  48 associated raw files and six groups. `reduction/verification.json` retains
  per-spectrum evidence and the explicitly unvalidated review counts.
- Chromium opened both actual reports offline. All embedded images loaded
  (53 on 28 October, 48 on 29 October), figure enlargement worked, and a real
  downloaded FITS file matched the saved bytes. No external requests or page
  errors occurred. Each revision retains `offline-report-verification.json` and
  the verification script.
- All **466 raw-file paths** in the initial hash baseline remain unchanged.
  Original nightly HTML reports and selected-revision pointers were preserved
  byte-for-byte under each date's `archive/reports/20261108-before-daily-standards*`.
  `raw-preservation-verification.json` and the baseline retain that evidence.
- These checks establish numerical/provenance consistency, not independent
  absolute spectrophotometric accuracy. The four optical wavelength failures,
  two unresolved background cases and Gr16 limitations above remain explicit.

## Follow-up: AT2026agzp wavelength flag and broken profile curves

The Gr11/slit1.0 standard responses exist (VMa2 at 02:26 UTC and L745a at
08:16 UTC on 29 October). The selected lamp is the 11:27 UTC exposure; its
arc fit RMS is 0.168 pixel and held-out RMS 0.191 pixel. Missing calibration
files did not cause this failure. The 04:00 UTC science exposure's 5577 and
6300 sky features require shifts of -5.118 and -4.912 A. Their mean trial
correction, -5.015 A, leaves the independent 6363 feature at a -4.238 A
residual, exceeding the project's 3 A acceptance limit. That trial correction
was not applied to the delivered review counts. The flag establishes an
inconsistent sky check, not proof that the lamp solution is wrong. A biased
sky-line measurement versus a wavelength error still needs discrimination;
a further flux standard would not settle this.

The discontinuous review-profile curves were a separate diagnostic masking
problem: masked detector pixels became NaN, and `np.sum` propagated any NaN
to the whole spatial-column sum. Within raw x=516--579, only six of 64 columns
had every one of 855 rows unmasked, although every column retained at least
836 good pixels. The gaps were not physical discontinuities or failed extraction.

The diagnostic now sums the same common valid rows across the supported
spatial interval: 761/855 for the full AT2026agzp range, 194/214 for Q2 and
197/214 for Q3. It does not fill pixels, interpolate gaps, smooth the profile or
rescale incomplete sums. Entirely missing columns remain missing. Outside the
model's supported interval, no background-subtracted curve is drawn. The legend
records retained row counts; `profile-display.json` records the masking policy.
The two optical review-count profiles and 28 October report were regenerated;
extraction products and wavelength acceptance were unchanged. Previous figures,
the previous report and product hashes are retained under
`runs/2026-10-28/QC/profile-masking-20261108-v1/`.
All 21 focused profile/plot/filtered-workflow tests pass, including regressions
for isolated masked pixels, unsupported spatial regions, entirely missing columns
and absence of common good rows. Hash checks confirm the saved counts and
extraction arrays are unchanged.
