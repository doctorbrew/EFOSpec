# Native calibration, desktop extraction, and SN/host work

- Work branch: `feature/native-desktop`; separate worktree and development environment.
- Main checkout: another thread is debugging the October nightly reductions; preserve its work.
- Confirmed platform: **PySide6/Qt**, targeting macOS and Linux with separate acceptance tests.
- Keep Fieldnotes read-only; desktop controls edit recipes and run Python workers.
- No proprietary exposures, plots, or raw identifiers in Git.

## Native raw calibration

- Use PypeIt bias combination, slit tracing, raw-arc handling, tilts, flats, and extraction.
- Identify raw lamp lines against independent physical references; never import IRAF pixel IDs.
- Reject nonphysical wavelength ranges even if formal RMS is small.
- Check held-out lines and contemporary sky residuals; record failed configurations.
- Match observed standards to independent physical flux references; derive new sensitivity.
- Acceptance: raw-to-product run with the legacy calibration library inaccessible.

## Joint extraction

- Inspect wavelength-binned spatial scatter to locate structured residuals.
- Distinguish host light from sky-line residuals, fringing, and defects.
- Fit point-source and extended spatial components with a constant/linear/quadratic sky.
- Choose background order using held-out background pixels, never source pixels.
- Retain alternative plausible background orders and their effect on extracted flux.
- Preserve cross-source covariance; label uncertainty conditional on fixed spatial profiles.
- Reject degenerate profiles; no positivity clipping or hidden regularization.
- Validate synthetic injections before real-data trials; real SN/host identity remains operator-selected.

## Desktop acceptance

- Open a night/run using a native file picker; inspect spectrum, 2D image, and spatial profiles.
- Edit trace anchors, aperture widths, sky regions, and an optional companion.
- Save/reload validated recipes; run/cancel workers; preserve original products.
- Show calibration mode, unresolved source identities, and scientific limitations.
- Match CLI and desktop replay arrays; test interactions on every claimed platform.

## Current evidence

- A first unbounded PypeIt lamp fit returned a negative central wavelength despite a small RMS; rejected.
- A constrained raw-line experiment using the [ESO physical He–Ar atlas](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/doc/manual/EFOSC2manual_v4.2.pdf) finds a physically plausible Gr13 solution.
- Arc-only experiments were followed by the bounded end-to-end result below.

## Current result

- Raw-only Gr13 science/standard pair reaches FITS/ASCII and Fieldnotes.
- Qt desktop controls, worker lifecycle and recipe replay pass local tests.
- Synthetic/raw-background injections and an SN2023xxj candidate pair are exercised.
- [Measured results and limits](../../native-desktop-validation.md).
- Keep this branch separate until reconciling the other thread's native-calibration implementation.
