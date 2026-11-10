# EFOSpec reduction debugging — 8 November 2026

Latest status: see the [9 November rescue record](rescue-2026-11-09.md) for two
resolved background failures and four provisional same-night flux spectra.
Their science wavelength checks remain unresolved; the dated account below
records the earlier debugging state.

## Latest delivery

The full reruns now use native raw calibrations and **same-night 2026 standard
responses**. The [28 October report](../runs/2026-10-28/index.html) contains four
science flux spectra, six standard flux spectra and two additional optical
review-count spectra. The [29 October report](../runs/2026-10-29/index.html)
contains all six Free-filter science flux spectra and six standard flux spectra.
All seven filtered-standard and five Gr16 exposures also extract into separate
counts products. Original raw files, accepted revisions and archived reports
are retained.

Four 28 October science wavelength checks still fail: SN2026abgb, AT2026agzp,
AT2026agvs and SN2026aebl. The first and third also retain unresolved background
failures. Numerical manual trials are preserved with their limitations and were
not promoted through relaxed thresholds. See the
[final revisions, measured failures and reproduction commands](daily-standard-calibration.md#delivered-nightly-reruns).
The earlier sections below retain the debugging history rather than the current
delivery status. Absolute flux accuracy and Gr16 flexure remain unvalidated.

## Historical baseline before the contemporary-response reruns

At the start of this investigation the selected revisions used the archive-calibration bridge:
`20261105T003458Z-8d3f58` (28 October) and
`20261105T003942Z-333cad` (29 October). PypeIt extracts electrons, but
`archive_calibration.sensitivity_factor` applies imported IRAF sensitivities.
Both nights select L745a response observations from **23 January 2014**:
`sens_2DR_Gr11_Free_slit1.0_1.fits` and
`sens_2DR_Gr13_Free_slit1.0.fits`.

Selection matches grism/filter and nearest archived MJD; it ignores slit width
as the legacy implementation did. It does not use a newly fitted response from
the 2026 standards. The reported physical flux scale remains experimental.

For extracted electrons C, gain g in electrons/ADU, exposure t, air-wavelength
bin width Δλ, archived sensitivity S, extinction k and airmass X:

`F_lambda = C / (g * t * Δλ) * 10**(-0.4*S) * 10**(0.4*k*X)`

Here the IRAF convention is `S = 2.5*log10((ADU/s/Angstrom)/F_lambda)`.
Products use erg/s/cm²/air-Angstrom, topocentric wavelengths. Variance scales
by the square of the conversion factor. Bin-overlap resampling propagates
diagonal variance; spectral covariance and response uncertainty are absent.
No telluric, slit-loss or second-order correction is applied. The archive
bridge also omits bias/flat correction. The curve's age alone does not measure
its error, but we have not established its validity for these 2026 spectra.

The separate native route builds bias/flat/arc calibrations from raw frames,
extracts with PypeIt, fits `pypeit.core.flux_calib.sensfunc` to a physical
standard reference, and applies La Silla extinction consistently. It converts
PypeIt's vacuum-density response to the delivered air-density convention.
See [PypeIt 1.14 flux calibration](https://pypeit.readthedocs.io/en/1.14.0/fluxing.html).
The subsequent daily integration and full rerun supersede that default; see
[daily standard calibration](daily-standard-calibration.md).

## Executed investigations and changes

- **Background recovery:** the trial command wrongly rejected
  `background_support_required`. Reproduced the failure, added a regression,
  and admitted those cases through the existing hash-verified recovery loader.
  Failures now record source/neighbor FWHM, exclusion radii and the failing
  sides. Added an explicit 70–200-pixel archive half-window diagnostic option.
- **Actual background trials:** the fixed command extracts SN2026aebl C2 as
  an unverified candidate. C1/C3 and AT2026agzp trials fail fitted-trace support.
  Automatic 241-pixel windows still fail: broad detected neighbours occupy the
  usable background. Widening alone is not a demonstrated fix. No source
  identity or accepted extraction was changed.
- **Gr16/OG530:** connected the already implemented physical red He/Ar fitter
  to native bias/flat/tilt processing and counts export. `reduce-red` is an
  explicit diagnostic route; it never promotes arc-only counts to validated
  science or applies a correlation-derived shift. Existing arc coverage,
  residual, raw-hash, variance and two-sided background gates remain active.
- **Actual Gr16 results:** both 28 October standards extract. On 29 October,
  AT2026twd and VMa2/slit1.0 extract. VMa2/slit1.5 remains blocked even in a
  401-pixel window: a detected neighbour has FWHM 73.3 pixels and a 109.9-pixel
  guard overlapping the target/background region. Whether this broad feature
  is a source or a background/detector structure needs review; it was not
  silently discarded. These are four distinct new review-count exposures.
- **AT2026twd evidence:** 15 arc IDs; RMS 0.086 pixel; held-out RMS 0.123 pixel;
  valid reference bracket 6679.995–9787.186 vacuum Å. Two 30-pixel background
  bands converge with at least 20 accepted samples per side. Red-sky
  correlation suggests −3.52 Å but is not a validated correction or applied.
- **Flexure:** replayed the five 28 October failures in full, left, central and
  right slit windows. Weak 6300 Å measurements dominate the short VMa2 cases.
  SN2026abgb retains a 3–4 Å anchor disagreement across the slit. AT2026agvs
  remains close to the 3 Å gate; one spatial subset passes but lacks a strong
  held-out 6363 Å check. Selecting that subset after seeing its result would
  not establish a trustworthy correction. Existing native-calibration checks
  also retain the science-target discrepancies. No thresholds were relaxed.
- **VMa2 physical reference:** registered the externally published
  [ING/Oke 1974 mJy table](https://www.ing.iac.es/Astronomy/observing/manuals/html_manuals/tech_notes/tn065-100/small/vma2.tab),
  pinned by SHA256. Coordinates and proper motion follow
  [PESSTO Table 2](https://arxiv.org/html/1411.0299v2#S3.T2), propagated to the
  observation epoch; OBJECT alone never selects the reference. Verified its
  mJy values against ING's AB table: maximum difference 0.000126 mag over
  398 samples. The table has 10–80 Å sampling and no explicit wavelength-medium
  card; the air interpretation is recorded as an assumption. This is an
  experimental alternative, not a newly certified absolute scale.
- **Filtered responses:** all four 28 October and all three 29 October saved
  filtered-standard extractions now yield response fits. Six held-out transfers
  on the first night and two on the second compare distinct raw exposures with
  identical grism/filter/slit/binning/readout. Continuum-band ratios range
  0.912–1.099 and 0.851–1.112, respectively. This is internal transfer evidence;
  different slit losses/transparency and reference spectra can contribute.
  Filtered delivered FITS files remain counts, and no Free/GG495 correction
  or science response was automatically selected.

## Reproduction and saved evidence

Run one explicitly named night per invocation. Use fresh output directories.

```sh
python -m efospec reduce-red data/2026-10-29 --night 2026-10-29 \
  --target AT2026twd --output runs/2026-10-29/QC/NEW-red-revision
python scripts/debug_background_windows.py 2026-10-28 \
  --target AT2026agzp --target SN2026aebl --half-width 120 \
  --output runs/2026-10-28/QC/NEW-background-revision
python scripts/debug_standard_responses.py 2026-10-28 \
  --parent runs/2026-10-28/filtered/20261105-native-v2 \
  --output runs/2026-10-28/QC/NEW-response-revision
```

New results live under `runs/DATE/QC/`:

| Date | Directory | Evidence |
| --- | --- | --- |
| 28 October | `local-background-20261108T000153Z-4d7e2a/` | Candidate trials, C2 extraction, figures and logs |
| 28 October | `debug-20261108-background-v2/` | Wider automatic-window failures |
| 28 October | `debug-20261108-flexure-v1/` | Spatial sky-line probes |
| 28 October | `debug-20261108-gr16-v1/` | Two Gr16 standard counts and raw masters |
| 29 October | `debug-20261108-gr16-v1/` | AT2026twd counts, 2D spectrum, masters and red-sky check |
| 29 October | `debug-20261108-gr16-standards-v1/` and `v2/` | Standard extraction and wider-window retry |
| Both | `debug-20261108-responses-v1/` | Responses, reference hashes, held-out ratios and logs |

These dated diagnostics preserve raw inputs, accepted products, nightly pointers
and both existing HTML reports. They are not a new full-night delivery.

Verification: 45 focused native/filtered/rapid/recovery regressions passed,
plus 12 background/reference checks (overlapping reference coverage). New red
trials verified 49 distinct raw inputs, 40 calibration files and 25 product
files, including the retained retry. Both existing nightly HTML SHA256 values
are unchanged. `verification.json` in each response-trial folder records the
checks; PDF/JPG figures accompany the held-out response diagnostics.

## Next acceptance steps

1. Resolve the broad background features and trace motion with exposure-specific
   geometry; review the SN2026aebl target identity before promoting any candidate.
2. Fit/check additional sky features, with separate held-out features, to resolve
   wavelength-dependent residuals. Implement an independently checked red-sky
   correction for Gr16. Arc-only short-standard counts must retain that status.
3. Build and compare contemporary **Free-filter** responses as well as filtered
   responses, then connect accepted native results to nightly reporting. Never
   substitute a filtered response for Free or vice versa.
4. Define supported red wavelengths and quantify fringing/telluric effects.
   Assess absolute calibration with external data when available; the user has
   supplied no additional validation data. Response-fit closure is not enough.

Second-order correction and 2D host subtraction remain deferred.


## Follow-up: nightly contemporary-response integration

The new [daily calibration workflow](daily-standard-calibration.md) connects
native same-night standard responses to new nightly revisions. Archived replay
is explicit; existing report pointers were preserved. Two 29 October trials
exercise a fitted VMa2 Free response and failures from background/wavelength
checks. No new real science spectrum passed all gates in those trials; the
synthetic end-to-end flux test provides the numerical integration check.


## Full rerun and corrected causes

The [daily calibration record](daily-standard-calibration.md#full-reduction-debugging-8-november-2026)
contains the reproduced causes, numerical evidence, literature and implementation
changes. The broad background neighbours were largely detections on an
unsubtracted pedestal or on extrapolated background pixels. Native sky lines
needed the slit illumination profile and adequate spatial sampling. Gr11 needed
more stable arc sampling and a fuller physical atlas. Sensitivity fits needed
intact spline boundary padding. The original numerical acceptance thresholds
remain active. The earlier “next acceptance steps” above describe the initial
state; they do not describe the completed Free-filter rerun.
