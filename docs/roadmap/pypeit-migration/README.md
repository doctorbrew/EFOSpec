# EFOSC2 spectroscopy migration to PypeIt

- [Pipeline comparison](../../pipeline-stages.md)
- [Desktop extraction GUI and two-source roadmap](gui.md)
- [Legacy compatibility check](../../legacy-compatibility.md)
- [Native calibration inputs and current blockers](../../native-calibration.md)
- [Package identity, dedicated environment, and observer migration](adoption.md)

## Outcome and scope

Replace the IRAF/PyRAF reduction engine while retaining the observer-facing
ePESSTO product naming, calibration policy, scientific conventions, and delivery
formats. The current scope is **EFOSC2 optical spectroscopy only**.
Start with Gr13/Free/slit1.0, then Gr11 and Gr16/OG530. Other configurations,
including Gr18/20 and wide-slit standards, require their own validation.
Imaging and automatic external uploads are outside this migration.

Preserving calibration means preserving identifiable input observations,
reference standards, extinction curves, configuration matching, and explicit
fallback policy. It cannot mean feeding IRAF master products into PypeIt as
though their formats and processing histories were interchangeable. PypeIt
masters and numerical results will change. Retain legacy masters as comparison
artifacts. The native path must rebuild calibrations from raw data without
IRAF-derived line identifications, response arrays, or master products.

Completed in this checkout: public upstream fork, separate `EFOSpec` repository,
source/data audit, pure naming functions, conservative read-only inventory,
raw-calibration planning, catalogue-based standard matching and a native PypeIt
metadata/raw-reader adapter. A dedicated runtime is defined in `environment.yml`;
earlier integration evidence used the existing `pypeit` environment. An experimental archived-calibration bridge
now demonstrates native PypeIt extraction and legacy-named flux products for all
13 science exposures from 2024-11-14. See the updated [run evidence](evidence.md).
This is a bounded transition experiment; native calibration generation and
full-profile equivalence remain pending.

The 2.0.1 research below remains a source comparison, not the selected runtime.
The installed 1.14.0 has now been exercised directly on the supplied inputs.
See [the integration evidence](pypeit-integration.md) for the tested scope.

## Desktop extraction and nightly log

- Required extraction interface: desktop application; Swift/SwiftUI or a suitable macOS/Linux desktop toolkit.
- Platform/toolkit selection remains open; no desktop app is delivered yet.
- The existing browser editor is a prototype for the shared backend and recipe workflow.
- Fieldnotes is the read-only log of reduced spectra for a night: opening table, per-source plots, status, and downloads.
- Do not replace the desktop requirement with a browser editor or add extraction controls to the nightly report.
- [Desktop tasks and acceptance gates](gui.md) · [Repository rules](../../../AGENTS.md).

## Evidence that changes the approach

1. **Instrument support is configuration-specific.** PypeIt 2.0.1 supplies
   EFOSC2 arc templates for Gr4/5/6; inspected data use Gr11/13/16. The generic
   `ntt_efosc2` supported flag is insufficient. Both the official
   [instrument documentation](https://pypeit.readthedocs.io/en/2.0.1/spectrographs/ntt_efosc2.html)
   and [tagged source](https://github.com/pypeit/PypeIt/blob/2.0.1/pypeit/spectrographs/ntt_efosc2.py)
   establish this gap.
2. **Frame typing needs an ePESSTO adapter.** Local standards have
   `OBJECT=Feige110` or `L745a`, `DPR TYPE=STD`, and `DPR CATG=SCIENCE`.
   The tagged PypeIt driver identifies standards by target strings `STD` or
   `STD,FLUX`; category SCIENCE also selects science frames. Its setup keys
   omit the order-sorting filter. Override typing and setup grouping explicitly.
3. **The available data cannot establish full reduction parity.** The installation
   sample is one raw Gr13 spectrum plus one imaging frame, an archived processed
   arc, and a rectified spectrum. The November directory adds raw science and
   standards and legacy products, but no raw arcs, biases, or flats. Do not claim
   that an archived processed arc supplies a raw calibration night.
4. **Rapid and full reductions are different scientific profiles.** Rapid omits
   bias/flat corrections; extinction files, naming, trimming, and some fitting
   settings differ. A single implicit PypeIt default would erase these choices.
5. **A format change can become a scientific error.** PypeIt wavelengths are
   vacuum; the legacy line list appears to use air wavelengths and requires
   confirmation. PypeIt FLAM uses a 1e-17 scale while legacy 1D uses physical
   cgs values. Inverse variance is not an error column. See
   [wavelength calibration](https://pypeit.readthedocs.io/en/2.0.1/calibrations/wave_calib.html)
   and [flux calibration](https://pypeit.readthedocs.io/en/2.0.1/fluxing.html).

See [evidence](evidence.md) for repository versions and reproducible inspection.

## Architecture options

### A. Replace IRAF calls inside `ntt`

Keep current entry points and substitute operations individually. Familiar
control flow is the benefit. However, extraction, rectification, calibration
files, interactive state, and source details are intertwined across large functions.
IRAF and PypeIt do not expose equivalent stages or data models. This creates a
long-lived hybrid with repeated conversions and difficult failure recovery.
Suitable only for small independent utilities, not the reduction engine.

### B. A separate ePESSTO policy layer around PypeIt — recommended

Keep `trunk/` as a reproducible baseline. A new `efospec` package owns
metadata normalization, calibration decisions, the run manifest, and export.
Use PypeIt's public reduction interfaces and native calibration/spec1d/spec2d
products internally. Export to historical filenames and formats only after
validation. This isolates the scientific changes and makes parallel baseline
runs possible. The cost is building a real exporter and a tested instrument
extension rather than relying on file renaming.

### C. A standalone PypeIt-only workflow with new delivery formats

Use stock setup/reduction/flux/coadd tools and ask observers/downstream tools
to adopt their outputs. This is simpler but fails the requirement to preserve
names and delivery behaviour. Keep it as a development reference run, not the
collaboration-facing solution.

## Interfaces and ownership

The proposed flow is:

```text
immutable raw files + independent physical reference catalogues
    -> inventory and normalized exposure records
    -> explicit calibration plan and human overrides
    -> versioned EFOSC2 PypeIt configuration + native products
    -> standard/sensitivity, flux, optional telluric and coaddition stages
    -> scientific QA + selected target extraction
    -> legacy products and source details links
```

The following are **planned interfaces**, not currently available commands:

- `plan(inventory, profile, overrides) -> RunManifest`: choose each calibration
  with its eligibility and selection reason. Missing inputs or ambiguous target
  associations produce a reviewable blocked plan, never an implicit fallback.
- `reduce(manifest, work_directory) -> NativeProducts`: run the pinned engine,
  preserve parameters and logs, and return verified output paths and object IDs.
- `validate(native_products, baseline, policy) -> QAReport`: evaluate independent
  wavelength/flux/error evidence; distinguish absent evidence from a passed test.
- `export(products, manifest, compatibility_profile) -> DeliveryProducts`:
  translate units, sampling, headers and bands; allocate names from a persisted
  registry. An absent calibrated band must not be replaced by plausible zeros.

The manifest records schema version, raw hashes/ARCFILEs, original header values,
normalized setup, observing night, frozen processing date, selected calibrations,
reference-file hashes, software versions, full parameters, extraction IDs,
wavelength medium/frame, extinction/telluric steps, fallback reasons, QA status,
and mapping of native products to delivered files. Overrides are versioned data.

Store each run separately. Preserve native products, immutable raw inputs and
the precise generated `.pypeit`/flux/sensfunc/coadd files. Use argument-list
subprocesses with checked exit codes or a pinned public Python API. Verify
outputs before marking a stage complete. Cache reuse must depend on input hashes,
configuration, processing parameters and engine version, not filenames alone.

No distributed task framework is needed initially. A single-night command and
restartable stages are enough. Introduce legacy CLI backend selection only once
the new path passes compatibility and scientific gates; switching backend must
remain explicit until collaboration acceptance.

## Calibration policy and instrument work

Keep `rapid` and `full` named profiles. Their historical behaviour is documented
in [the compatibility contract](../../legacy-spectroscopy-contract.md). Record
each intentional difference from legacy, including safety improvements, rather
than claiming bitwise parity or reproducing known uncertainty mistakes.

Calibration association has two layers:

1. Reproduce the historical priorities: explicit selections, same-night inputs
   where used, then archived fallback. Preserve the wide-slit arc exception and
   grism/filter sensitivity matching. Retain a reason and time separation.
2. Check physical compatibility: detector geometry/binning/readout, grism,
   order-sorting filter and calibration-specific slit rules. Biases do not need
   a grism match. Sensitivity functions may transfer between slits but need an
   explicit flux/slit-loss policy and wavelength coverage. Never let nearest-MJD
   selection silently override incompatible setup or missing source details.

No maximum calibration age is invented here: establish permitted ages and
exceptions from the collaboration's practice. An initially stricter planner
should flag historical selections that lack required compatibility evidence;
resolve and record them rather than silently selecting another calibration.

For Gr13, first validate raw orientation, binning and trim coordinates. The
existing driver hard-codes read noise 10 e- while inspected headers contain
7.8 e-; use the recorded detector mode/header after verifying their meaning.
The order-sorting filter must participate in configuration identity. Audit
overscan and flat defaults from the actual parameter object; documentation and
commented code are not sufficient to determine effective processing.

Build a PypeIt Gr13 wavelength template using verified raw arcs and the correct
lamp species. Legacy uses Hg/Cd/He/Ne/Ar references; the generic driver defaults
to He/Ar. IRAF identification databases can guide line identification, but their
coefficients are not portable PypeIt wavelength solutions. Convert reference
wavelengths only after establishing air/vacuum conventions; retain original
values and the conversion method. Validate on independent arcs and night-sky
features, not solely the arc used to construct the template.

Prefer an upstream PypeIt instrument contribution for generic EFOSC2 fixes and
new grism templates. Keep ePESSTO-specific policy and exporters here. During
development use a small explicit driver extension or a pinned PypeIt fork;
avoid runtime monkey-patching. Establish a supported loading path for the
chosen engine version before exposing a reduction command.

## Flux calibration and output semantics

Reduce standards through the same detector/wavelength configuration as science,
identify them against the legacy catalogue, and derive **new PypeIt sensitivity
functions from the same reference spectra**. IRAF sensitivity images are not
PypeIt sensitivity files. Validate standard units, sampling and wavelength
coverage. Use the exact profile-specific La Silla curve with a tested conversion
to the engine's expected format. Extinction is applied at standard calibration
and science calibration at their respective airmasses; avoid duplicate treatment.

Gr13 second-order contamination is a separate calibration task. The historical
Free/GG495 sensitivity splice near 5500 Å is evidence of policy, not a formula
that can be copied across response representations without testing. Validate
blue/red standard behaviour before releasing a Gr13 red flux scale. Telluric
correction is another explicit stage; UVIS extinction alone does not remove
telluric bands. Keep uncorrected and corrected products and propagate errors
through the correction, including the adopted treatment of model uncertainty.

PypeIt native arrays may have nonuniform wavelength sampling. A legacy linear
WCS requires a deliberately selected output grid and flux-conserving resampling,
with masks, variance propagation, and an explicit covariance limitation.
For a linear transform R, propagate independent input variances with
`Var(out_i) = sum_j R_ij**2 * Var(in_j)`; interpolating sigma or inverse variance
as if it were flux is wrong. Resampling can correlate neighbouring pixels.

Preserve the topocentric frame for the initial compatibility profile. Air/vacuum
and velocity reference are separate decisions. Do not apply barycentric
correction and then simply label the output topocentric. An air/vacuum change
also requires an explicit convention for flux-density coordinates/Jacobian
when conserving integrated flux. Keep the native wavelength array as source details.

Export physical cgs 1D flux: PypeIt FLAM times 1e-17. For positive, finite
inverse variance and valid masks, sigma is `1e-17 / sqrt(FLAM_IVAR)`; invalid
pixels must remain distinguishable from valid measurements. Verify multispec
band ordering and WCS with real consumers. Preserve the historical two-column
`.asci` file; put mask/error information in a separate explicitly documented
product rather than silently adding columns.

Keep filename and header-key contracts, but record the actual processing
software and measured QA. Do not copy legacy `Final`, fixed error estimates,
or `ABSOLUTE` flux claims into experimental products. Treat ESO Phase 3 delivery
as its own tested export contract; legacy-looking filenames do not establish
archive compliance.

## Validation strategy

Exact checks cover names, observing nights, raw identities, calibration
selection reasons, file shapes/band meanings, units, header semantics, output
associations, idempotence and raw immutability. These are not approximate.

Scientific comparison should use both legacy products and independent evidence.
Compare both engines on the same raw exposure/calibration selections and common
wavelength convention/grid; retain their native outputs. Reconstruct the legacy
run options from logs and extraction databases. An existing reduced file with
unknown choices is an observational reference, not a complete golden run.

Proposed investigation thresholds below are **starting gates for discussion,
not measured performance or accepted collaboration requirements**:

- Arc RMS below 0.2 binned spectral pixel, with enough independently identified
  lines across the band; verify held-out sky centroids within 0.2 pixel. Inspect
  wavelength-dependent residuals rather than accepting a low global RMS alone.
- Repeat/held-out standard flux ratios: initially investigate deviations above
  5% in clean wavelength intervals after separating transparency and slit losses.
  Report absolute scale and spectral-shape residuals separately. A fit to the
  same standard used to derive sensitivity is not independent validation.
- Blank-sky normalized residuals: inspect median and scatter, with 0.8–1.2
  scatter as an initial diagnostic band only after accounting for resampling
  and correlations. Assess sky-line regions separately from continuum.
- Extraction: repeatability and injection/recovery for faint transients beside
  hosts; no automatic brightest-object or fixed-detector-pixel selection.
- Masking: injected cosmic rays, bad columns and saturated pixels remain masked
  through extraction and export; no invalid samples become high-S/N detections.

Build a validation matrix spanning bright/faint targets, host contamination,
different slit widths and binning/readout, short/long exposures, multiple nights,
fringing, missing calibrations, and all relevant grism/filter pairs. First-pass
Gr13 success only authorizes that tested configuration. The schedule and final
tolerances depend on obtaining complete calibration nights and operator review.

## Delivery order

1. Freeze baseline and contracts; inventory inputs (foundation delivered).
2. Obtain a complete Gr13 night and implement explicit calibration planning.
3. Validate detector geometry and a Gr13 arc template; obtain native spec1d/spec2d.
4. Match standards/extinction, flux and second-order treatment; validate errors.
5. Export legacy products, compare both reductions, and introduce optional CLI dispatch.
6. Extend Gr11/16, other EFOSC2 configurations, and operator QA as separate gates.

Concrete tasks and unresolved decisions are in [tasks.md](tasks.md).
