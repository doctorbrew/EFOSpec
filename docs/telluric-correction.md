# EFOSpec standard-star telluric correction

Implemented as `efospec telluric`: PypeIt 3.0.0 atmospheric PCA, fitted on native
samples with a physical stellar reference, separate-exposure transfer tests,
and propagated uncertainty. This writes an explicit new revision. Add
`--attach-to-report` to retain both reductions in the final spectrum plots and
downloads. The original reduction remains the default scientific product.

## Configuration and method

[The EFOSC configuration](../configs/telluric_efosc.par) uses PypeIt's actual
`teltype = pca` and `resln_guess = 500.` keys. The attached ALFOSC file's `method`
and `resln` keys are rejected by the installed version. Resolving power means
lambda/FWHM: a 10 Angstrom FWHM at 7600 Angstrom corresponds to R about 760,
not R=10. Do not copy an ALFOSC instrumental resolution into EFOSC calibration.

- Model: `TellPCA_3000_26000_R10000.fits`, SHA256
  `10d56a6cf5774a352507a69c5cae9a11f158866e47e962ed682bb6e39e2901df`.
  PypeIt resolves/downloads this public model into its normal cache.
- The project wrapper uses PypeIt's radiative-transfer PCA and instrumental
  convolution. It does **not** run the `pypeit_tellfit` CLI. Observed flux is never
  upsampled to the finer atmospheric grid; convolved transmission is integrated
  over native pixel edges. Fitting uses vacuum Angstrom; exported products and
  band definitions retain the project's topocentric air-Angstrom convention.
- The standard's observed/reference ratio is fitted with atmospheric PCA,
  resolving power, wavelength displacement and a degree-three smooth continuum.
  Hydrogen/helium features are masked; telluric bands are retained. The physical
  reference must match the one used for its saved response. The smooth response
  is not mistaken for an atmospheric correction.
- Two PCA coefficients are used for all setups in this trial. An initial
  three-component VMa2 fit reached a coefficient bound and was rejected; the
  simpler two-component fits all passed the convergence/rank/bound checks.
  This is model selection on this night, not proof that two components suit
  every night. Formal covariance uses the full joint continuum/atmosphere fit,
  S/N capped at 30, and scales upward for excess reduced chi-square.
- A separate exposure with the **identical** night/grism/filter/slit/binning/
  readout tests each fitted model. Its continuum is estimated outside all
  tested atmospheric bands; no atmospheric parameters are fitted to it.
  Reciprocal transfers reuse exposures: 14 directed tests are not 14
  statistically independent datasets. Different-star and same-star repeats
  are identified separately. These are telluric checks, not independent
  absolute-flux checks against another flux-reference system.
- Optical depth is scaled by the target/standard airmass ratio **before**
  convolution. This does not assume water vapour is constant throughout the
  night. Temporal/humidity changes remain a transfer risk.

## Transfer gates and science outputs

Air-wavelength bands are O2 B 6820–7000, H2O 7120–7390, O2 A 7540–7790 and H2O
8090–8310 Angstrom. A test needs at least 12 usable native samples, 70% of its
band samples and 80% of the band's wavelength span. The engineering gates are
absolute median residual <=5%, RMS <=10%, and at least 20% RMS improvement
unless the final RMS is <=2%. These choices do not establish 5% absolute flux
accuracy. A band qualifies only if **every available test** of that model
passes; missing/error/failed tests do not silently disappear.

Science requires a passing saved independent sky-wavelength check and the
nearest successful standard in the identical setup; ambiguous ties fail.
It must be within two hours of the standard and inside the actual airmass
range spanned by the training and test standards. The two-hour cap is a conservative operational bound,
not a measured atmospheric stability time. The standard's raw-grid wavelength
offset is not copied to sky-corrected science. Unqualified bands and unstable
division (transmission below 0.2) are masked. Outside the four bands the source
product is retained unchanged; weaker absorption elsewhere is not corrected.

For transmission T, independent science variance V and model variance V_T:

```
corrected flux = F / T
statistical variance = V / T^2
telluric-model variance = F^2 V_T / T^4
```

V_T includes marginal fit covariance, the worst passing band's independent
transfer RMS as a fractional error envelope, and explicitly assumed science
transfer sensitivities: one native pixel of wavelength uncertainty and 20%
of fitted resolving power. These last two are conservative model assumptions,
not measured science centring/seeing errors. Reference/continuum, response,
slit-loss, second-order and absolute-scale errors are not fully characterized.
Adding the measured transfer RMS also includes some test photon noise; this
is a conservative envelope, not a pure estimate of atmospheric variability.

FITS products preserve the legacy basename in the **new** revision. The
primary optimal/boxcar fluxes are divided by T, primary sigma includes both
variance terms, and the diagnostic sky spectrum remains unchanged. Extensions:

- `UNCORRECTED`: original four-band cube; `ORIGINAL_VALID` in the `TELLURIC` table
  preserves its mask. The current `VALID` mask rejects unqualified bands.
- `STAT_SIGMA`, `TELL_MODEL_VAR`: separate statistical sigma and model variance.
- `TELLURIC`: air wavelength, T, V_T and actual correction mask `APPLIED`.
- `TELL_PARAMS`, `TELL_PARAM_COV`, `TELL_JACOBIAN`: applied atmospheric parameters,
  covariance and derivatives, in coefficient/R/vacuum-Angstrom-offset order.
  Parameter-driven spectral covariance is J C J-transpose; the empirical
  envelope is additional. These errors are not independent between pixels.
- `TELVALID=TRANSFER` means the bounded standard-transfer gates passed;
  `TELVALID=REVIEW` means an explicit, unvalidated airmass extrapolation.
  Both are partial, experimental corrections, not absolute-flux certification.

`--review-extrapolation` permits separate review products outside the tested
airmass range or beyond two hours, retaining the same-night setup, wavelength
and per-band gates. Every exceeded condition is recorded separately. Their
extra transfer error has **not** been calibrated. Without this option these
copies are withheld. Attaching them changes presentation, not scientific selection.

## Measured result: observing night 2026-10-28

Evidence: `runs/2026-10-28/QC/telluric-20261112-v3/` contains the source snapshot,
model/config/reference provenance, 12 standard fits, native fit/transfer arrays,
14 directed exposure transfers, plots, two review spectra and input hashes.
Ten of the O2 A tests are across different stars; two are repeated VMa2
exposures. Standard sequences are approximately six hours apart.

| Band | Passing / evaluable tests | RMS before | RMS after | Outcome |
|---|---:|---:|---:|---|
| O2 A | 12 / 12 | 21.0–24.6% | 3.2–5.6% | Pass; Gr11 has no coverage |
| H2O 7200 | 14 / 14 | 4.6–8.2% | 1.6–3.8% | Pass |
| O2 B | 9 / 14 | 4.3–6.9% | 2.0–5.3% | Setup/model dependent; five failures retained |
| H2O 8200 | 0 / 0 | — | — | Insufficient usable coverage after masks; withheld |

The nearest L745a Gr13/Free/slit1.0 model passes O2 B, H2O 7200 and O2 A in
the distinct VMa2 exposure. AT2024afzf and AT2026aeul receive review copies
using those bands: 128 corrected samples and 40 masked atmospheric samples
each. Their standard ages are 1.16 h and 0.51 h, respectively, but airmass
differences 0.157 and 0.238 exceed the tested 0.134. They are **review products**,
not validated science deliveries. The default v2 run correctly withheld both.

The atmospheric fit is now implemented and tested; the remaining gap is
validation of these science transfers and unusable bands. Nearer-in-airmass
standard observations, science-side atmospheric constraints with withheld-band
checks, or additional independent transfers can close that gap. Simply
allowing extrapolation cannot. No new slit-loss or second-order correction is
included. No accepted nightly spectrum, pointer or legacy data was changed.

## Run and verify

Use the EFOSpec/PypeIt 3.0.0 environment; one named observing date per invocation.
Outputs must be fresh directories. The run's night must match the requested date.

```sh
python -m efospec telluric 2026-10-28 \
  --run runs/2026-10-28/QC/nightly-integration-20261112/reduction/run.json \
  --output runs/2026-10-28/QC/telluric-NEW \
  --config configs/telluric_efosc.par --apply-science

# Add --review-extrapolation only to produce explicitly unvalidated review copies.
python scripts/plot_telluric_validation.py runs/2026-10-28/QC/telluric-NEW/run.json
python -m pytest -q tests/test_telluric.py tests/test_native_acceptance.py \
  tests/test_flux_validation.py tests/test_daily_reduction.py
```

For the selected nightly reduction, fit and retain the before/after versions,
then regenerate its final spectrum plots and dated log in one command:

```sh
python -m efospec telluric 2026-10-28 \
  --run runs/2026-10-28/nightly/20261110T170405Z-b97078/reduction/run.json \
  --output runs/2026-10-28/QC/telluric-NEW \
  --config configs/telluric_efosc.par --apply-science \
  --review-extrapolation --attach-to-report
```

The concrete `20261110T170405Z-b97078` revision is this night's selected run;
use the actual dated selection for another invocation. No multi-night loop is implied.

## Critical review and paired delivery

The initial implementation proved that the atmospheric model can improve
separate standard exposures. It did not yet provide a complete transient
delivery or certify every science transfer. The review identified and fixed:

- **Missing integration:** before/after FITS and ASCII are now retained under
  `uncorrected/` and `products/` in the correction revision. Original FITS copies
  are byte-identical. The original embedded cube remains available too.
- **Wrong-revision risk:** the final plot and download selection requires the
  exact parent manifest, raw identity, both product hashes and figure hashes.
  The earlier twelve-standard trial cannot be attached to a different extraction
  merely because a filename matches. Stale associations fail explicitly.
- **Airmass gate:** an absolute difference could wrongly admit science on the
  untested side of a standard. The gate now checks the actual observed range.
  Review copies remain possible, with the reason written in FITS, ASCII and HTML.
- **Wavelength-grid handling:** correction now honours `CRPIX1`, and pairing
  rejects different grids/units. Already corrected products cannot be divided again.
- **Presentation:** solid red before and dashed blue after curves share the
  original flux scale. Both errors contribute to display limits; the enlarged
  legend sits outside the data. Withheld bands are shaded and corrected gaps
  stay gaps. Download names include before/after suffixes to prevent collisions;
  disk basenames retain the legacy convention. Standalone and spectrum/trace
  figures include both curves. The report also retains the trace/profile panels.

`QC/telluric-20261112-v4` uses the selected 28 October reduction: six fitted
standards and four transient pairs, AT2026agwm, SN2026aebl, AT2024afzf and
AT2026aeul. All four science airmasses lie outside their tested ranges;
SN2026aebl is also 2.60 hours from its nearest standard. **All four corrected
versions are review products.** Extraction, wavelength and per-band failures
are not waived. The final `runs/2026-10-28/index.html` displays the pairs; the
selected reduction manifest, original scientific files and nightly pointer
are unchanged. Previous HTML is retained inside the telluric revision.

The `telluric-selection.json` sidecar selects presentation only. Rebuilding
`efospec report RUN` or the dated epoch page honours that exact selection.
Fresh fits require an explicit telluric command; report-only rendering never
fits an atmosphere. No classification or redshift measurement automatically
switches to a review correction.

Remaining scientific limitations are substantive: reciprocal checks reuse
the same exposures, two PCA components were selected on this night's data,
and the one-pixel/20% transfer uncertainties are assumptions. Airmass scaling
does not measure time-varying water vapour or science slit centring. A convincing
next validation needs independent standards near the science airmass/time or
a constrained science atmospheric fit tested on withheld features. Fitting a
free continuum through SN features and declaring the result flat would not
provide that evidence. Retaining both reductions enables inspection without
confusing model application with validation.

Paired-delivery verification: 62 checks passed (44 science/presentation tests,
17 report/asset tests and one additional reference-pixel regression);
71 protected inputs (including the selected manifest and pointer) stayed
unchanged. All 16 before/after FITS/ASCII downloads matched the source bytes
from a standalone offline report. Layout and enlargement/Close/Escape passed
at 1440 and 390 pixels. A rapid automated download batch timed out on download
11; all downloads passed with 350 ms between user-like clicks. Evidence is
saved as `verification.json`, `presentation-verification.json` and
`focused-tests.log` in the v4 revision.

The telluric regressions exercise the actual cached PypeIt atmosphere on
injected native samples, fixed-model held-out failure, wavelength covariance
replacement, negative flux, deep-absorption masking, airmass gates, raw-input
tampering, and a FITS round trip with variance/mask/provenance preservation.
The integration test is explicitly skipped when its model is not cached;
it ran and passed here. That initial verification did not rerun the complete repository suite.
The focused run passed **31 tests**. All **104 protected inputs** retained their
SHA256 hashes. Both real science FITS products passed checksum, original-data,
unaffected-wavelength, mask and variance-formula checks; see `verification.json`
and `focused-tests.log` in the v3 revision.

References: [PypeIt telluric correction](https://pypeit.readthedocs.io/en/latest/telluric.html)
and [the atmospheric-model implementation](https://pypeit.readthedocs.io/en/stable/api/pypeit.core.telluric.html).

Pre-push verification on 2026-11-12: the complete suite passed **547 tests** with
**85.08% coverage**, including the real atmospheric model, and the wheel build
passed. GitHub CI now installs that model before testing. The suite also caught
a legacy sky-mask replay mismatch: replay now uses the recorded trace polynomial
degree and still rejects a different fit without weakening its position tolerance.

## Explicit two-anchor wavelength acceptance

Native manual replays may explicitly select the 5577/6300 acceptance policy.
Telluric application checks the recorded anchor measurements and policy; a failed
6363 diagnostic alone no longer blocks these explicitly selected products. Legacy
failed checks remain failures. Background, per-band transfer, time and airmass
gates are unchanged, and each new spectrum requires a fresh hash-bound transfer.
