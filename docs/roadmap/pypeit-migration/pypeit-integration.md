# Existing-environment integration

**Update:** the metadata-only results below are now supplemented by an actual
experimental rapid reduction of all 13 science exposures from 2024-11-14.
`rapid.py` calls native PypeIt finding, sky subtraction and extraction, while
`archive_calibration.py` explicitly converts the historical references. The
new products, calibration checks, 47 passing tests and remaining limitations
are recorded in [the run evidence](evidence.md#2024-11-14-rapid-reduction-demonstration).
The historical sections below describe the earlier metadata milestone, not
the current absence of a runner.

The user confirmed that the existing Conda `pypeit` environment should be used
for testing. This supersedes the earlier proposal to require a new 2.0.1
environment before starting instrument work.

## Runtime and entry points

Tested interpreter:
`/Users/avinash/Softwares/miniconda3/envs/pypeit/bin/python`.
Actual imports report Python 3.11.9, PypeIt 1.14.0, Astropy 6.1.1 and NumPy 2.1.3.
No packages were installed/upgraded and no site-packages files were modified.
The earlier environment inventory recorded NumPy distribution metadata as
1.26.4; current setup reports record the version actually imported at execution.

```sh
conda activate pypeit
mkdir -p outputs
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m efospec plan ../pessto_test ../2024-11-14 > outputs/calibration-plan-full.json
PYTHONPATH=src python -m efospec inspect-pypeit ../pessto_test ../2024-11-14 > outputs/pypeit-setup-full.json
PYTHONPATH=src python -m efospec inspect-pypeit --profile rapid ../pessto_test ../2024-11-14 > outputs/pypeit-setup-rapid.json
```

Logs go to stderr and the report to stdout. The reports include the interpreter,
imported versions, profile, effective science-processing switches and input
SHA-256 values. A successful inspection exit code does not imply readiness.

## Implemented planning

`src/efospec/planning.py` creates deterministic raw associations:

- Positional matches within 100 arcsec of the preserved legacy standard
  catalogue. Header candidate status alone is insufficient; a science-labelled
  observation at a catalogue standard is also recognized, as in the legacy flow.
- Compatible detector geometry/binning/readout; grism/filter/slit as appropriate
  to each calibration. Biases are independent of the optical setup. Wide-slit
  arcs retain the slit5.0 → slit1.0 exception.
- Explicit raw arc selection takes precedence and never silently falls back
  to an incompatible/different arc. Off-night raw arcs require this explicit
  selection; their time separation is reported without inventing an age limit.
- Bias combination groups require at least three raw frames from one night.
  Flat groups require at least three from one OBID/night; lamp flats are
  preferred over dome flats, then matching OBID and time. Incomplete lamp-flat
  groups do not silently turn into dome-flat selections.
- Full-profile standard association is same-night and identical setup. This is
  the raw-standard step, not the broader grism/filter-only matching of an already
  derived archived sensitivity function.
- Rapid disables bias/flat correction. Its archive sensitivity and arc fallback
  remain unimplemented, so missing selections are reported rather than silently
  adopting the full-profile policy.
- Catalogue/extinction hashes, selected raw hashes, selection policies, rejected
  candidates, exact-time ambiguities and invalid inputs are explicit in JSON.

This is an initial raw-calibration planner. It does not build masters, ingest
IRAF archive products, apply calibrations, implement every explicit override,
or allocate persistent delivery names. Same-night restrictions and deterministic
ambiguity handling are stated constraints, not claims of complete legacy parity.

## Native PypeIt integration

`EFOSpecEFOSC2Spectrograph` subclasses the installed EFOSC2 driver. The
`PypeItMetaData` constructor accepts a spectrograph instance, so metadata
inspection needs no global registry patch or edited PypeIt installation.

The adapter:

- Separates raw spectroscopy, standards, arcs, flats, biases and darks; excludes
  imaging and processed products. Setup inspection supplies catalogue-verified
  types explicitly, avoiding substitution of PypeIt's different standard list.
- Adds filter and readout to native configuration identity and includes readout
  in configuration-independent bias/dark matching.
- Cross-checks detector and raw CDELT binning; currently enables only the
  inspected 2×2 geometry. Uses raw gain/read noise, including the measured-header
  value 7.8 e- rather than the stock driver's fixed 10 e-.
- Sets `refframe=observed` to preserve the topocentric velocity frame.
  This does not change PypeIt's vacuum wavelength convention or settle the
  legacy air/vacuum export question.
- Explicitly disables overscan/dark/cosmic-ray masking for these initial
  profiles. Rapid also disables bias/pixel-flat/illumination-flat correction;
  full enables bias and flat processing. These are provisional native settings,
  not proof that PypeIt flat processing reproduces legacy `apflatten`.
- Closes metadata-read FITS handles that the inherited filename reader leaves
  open in this version, without taking ownership of caller-supplied HDULists.
- Checks input hashes before engine access and joins returned metadata by
  filename. PypeIt reorders rows by MJD, so zipping returned rows with the input
  list incorrectly associates targets and exposures; regression coverage guards
  this discovered failure mode.

Both profiles successfully exercised native metadata construction, grouping,
detector parameter construction, raw pixel reading and data/overscan masks on
all 22 spectroscopic raw inputs. PypeIt formed four configurations, with 14
science spectra and eight standards. Every returned target was checked against
its source header and every SHA-256 remained unchanged after inspection.

The eight catalogue identifications are Feige110 and L745a; matches lie within
the existing 100-arcsec criterion. The 2012 spectrum has no same-night standard
and is explicitly left without that association. Imaging frames and rectified/
calibrated legacy products are excluded from PypeIt raw input.

Native data masks contain 1024×1024 science pixels within the 1030×1030 raw
images. This establishes reader behaviour, not parity with the narrower legacy
grism-dependent trim sections or validation of slit tracing/BPM placement.

## Tests and remaining scientific gates

All **41 tests passed** in the existing PypeIt environment, including seven
native-engine integration tests. Python 3.9 without PypeIt passed the other
34 tests and skipped those seven explicitly. Full and rapid real-data reports
were regenerated, and file identities/hashes were checked after native reading.

The suite covers naming, inventory, calibration selection, insufficient groups,
ambiguity, incompatible overrides, catalogue identity, changed inputs, effective
parameters, native filter/readout groups, raw reading and metadata row identity.
Native tests require PypeIt 1.14.0; environments without it skip those tests.
They must be run in `conda activate pypeit` to validate the engine integration.

The installed driver provides no configured Gr11/13/16 wavelength templates;
native inspection confirms these remain absent. Raw arcs, biases and flats
are still missing from the supplied input trees. No calibration groups are
assigned to a runnable reduction, no `.pypeit` run file is emitted, and no
rectification, extraction, flux calibration or compatibility export is claimed.
`associations_complete` and `reduction_ready` are distinct; even a synthetic
complete raw plan cannot assert scientific readiness.

Next: obtain raw Gr13 calibration inputs; verify legacy trim/slit/BPM geometry;
build and independently check the wavelength solution; then test native
calibration/reduction execution using this environment. Evaluate a newer engine
only when a demonstrated API or scientific requirement calls for it.
