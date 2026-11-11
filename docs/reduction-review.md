# Failed-exposure review

Delivered 2026-11-11: nightly logs retain errors and unsupported exposures as source entries, with the exact reason in red, the saved error-log download, and an exposure-specific **Open in EFOSpec GUI** link. Detailed reasons appear below target headings in the source logs; the opening inventory retains concise outcome labels. The link identifies the immutable reduction directory and raw filename; it opens inspection only.

The native Source review tab includes failed and skipped exposures even without QC packets. It displays the failure record and original traceback. Available review-count plots remain explicitly wavelength-unvalidated. Compatible existing packets still open the manual background editor. Missing packets are explicitly inspection-only: the new handoff does not add native calibration recovery or unsupported grisms.

The macOS app declares the `efospec` URL scheme; Linux launchers declare `x-scheme-handler/efospec`. Existing launchers need that registration updated. Each report includes a CLI fallback (`efospec gui RUN --raw FILENAME`). Local launch links need the original run and runtime on the same machine; portable downloads remain available without the app. Linux native interaction is not certified by the macOS checks.

## Evidence and required scientific work

Inspected current revisions for observing dates 2026-10-28 and 2026-11-10. The latter includes UTC exposures from 11 November.

- **Trace/background consistency:** SN2026afrp, AT2026aivg and EP261105a host fail after extraction adjusts the trace by at most 0.316, 0.154 and 0.200 pixels respectively. The check tests both surviving side samples and overlap with the source guard. The recorded failure does not distinguish these two conditions. Inspect the saved masks, then implement a bounded retrace/reselect/refit cycle with explicit convergence and final-trace support checks. Retain both-sided sampling; do not remove the guard or suppress failed rows without propagating masks and uncertainties.
- **Crowded aperture:** AT2026airg fails before final extraction because both aperture wings cannot be measured without contamination. Select the intended trace using acquisition evidence, review neighbouring traces, and test an explicit finite aperture and clean background bands. An extended host may require a separately validated joint spatial model. A successful polynomial fit is not proof of host separation.
- **Background geometry:** SN2026abgb's saved error says no background converged, but isolated replay shows that every final band failed placement before the solver ran. Current code extracts a trial while losing a broader neighbour's guard; do not adopt that trial. See the [SN2026abgb diagnosis](diagnostics/SN2026abgb-2026-10-28.md). SN2026ayt instead fails the final-trace support check. Do not treat these as the same numerical failure.
- **Wavelength validation:** SN2026acxa has an independent 6363 Å residual of −4.79 Å; AT2026agzp has −4.22 Å. AT2026agvs has inconsistent sky-anchor offsets. Review arc matches, dispersion residuals, slit illumination, air/vacuum conventions and line-fitting contamination before changing the correction model. Reserve independent lines for validation. SN2026ahvu's centroid uncertainty is just over the 1.50 Å gate; inspect its unrounded measurement and fit, rather than relaxing the threshold to accept it. Saved review counts retain unshifted arc wavelengths.
- **Setup coverage:** the daily delivery route selects Gr11/Gr13 Free with supported slit/binning combinations. Gr16/OG530 and Gr13/GG495 have separate experimental paths; they are not automatically validated daily products. Gr18/Gr20 need appropriate calibration and extraction support. An aperture edit cannot fix routing or missing calibration validation.

## Remaining recovery interface

The same-night native workflow currently skips `recovery-qc`, while `FailedExposure` reconstructs archive-based calibration records. Extend the shared recovery engine to preserve and verify native processed pixels, variance/masks, calibration identities, wavelength state and trace diagnostics. Then connect its exposure-bound recipes and workers to the existing desktop controls. Save each attempt in a new revision, carry the original failure log forward, and update accepted status only after extraction, wavelength and flux checks pass.

IRAF `apall` permits interactive aperture, trace and background adjustment. Getting a spectrum from that workflow does not establish that it passes EFOSpec's independent wavelength checks. References: [IRAF apall](https://iraf.readthedocs.io/en/doc-autoupdate/tasks/noao/imred/specred/apall.html), [IRAF aperture background](https://iraf.readthedocs.io/en/latest/tasks/noao/twodspec/apextract/apbackground.html), [PypeIt flexure](https://pypeit.readthedocs.io/en/state/calibrations/flexure.html).

## Launch and display correction, 2026-11-11

Detailed reduction errors appear in the individual source logs, not in the opening inventory table. Source entries have separator rules and recorded exposure durations. The desktop button uses an isolated launch frame so a rejected custom protocol cannot replace the report; it reveals a Terminal fallback without claiming that the app opened.

A real macOS URL launch exposed an uncaught PypeIt data-model exception while reopening an older remembered reduction. The GUI now catches that loading error, disables extraction for the incompatible product, and registers its native URL receiver before opening a remembered night. No data-model compatibility checks are bypassed.

Redshift measurement remains a separate post-reduction script. The 28 October saved measurements refer to an earlier reduction revision and are labelled “Previous revision”; 10 November has no saved redshift run. Earlier values are not silently assigned to new spectra.
