---
name: webpage-spectralog
description: "Build or refine a self-contained scientific daily log in the approved Fieldnotes design. Use for EFOSpec final nightly reports, dated reduction logs, or an explicit request to reuse this layout. Keep plots, QC and concise outcomes on one page. Not for extraction GUIs, generic websites or unrelated daily journals."
---

# webpage_spectralog

Displayed name: `webpage_spectralog`. Portable skill ID and explicit invocation: `$webpage-spectralog`.

Produce one portable HTML report for one named observing date. The user approved the EFOSpec 2026-10-28 page on 2026-11-02 as the final daily-log design; preserve its layout and make requested refinements incrementally. “Final” describes the report format, not scientific acceptance of its spectra.

## Use the existing workflow

Find the active EFOSpec checkout from workspace context and read its `AGENTS.md` and `docs/epoch-workflow.md`. Do not assume a particular user's absolute filesystem path.

- For a page rebuild or a design tweak, reuse saved data and figures with `python scripts/build_epoch_fieldnotes.py YYYY-MM-DD`.
- For an explicitly requested new reduction, use `python scripts/reduce_epoch.py YYYY-MM-DD`, or the existing separate log/reduction/report scripts. One invocation handles one observing date; the next epoch is a separate invocation with its own date.
- The final daily log is `runs/YYYY-MM-DD/index.html`. `nightly/current.json` selects the current processing revision; revision reports and archived products are supporting records.
- Reuse `src/efospec/epoch_report.py` and the CSS in `src/efospec/report.py`. Do not fork a second report engine or copy the scientific reduction code into this skill.
- When the checkout is unavailable, use supplied artifacts and [the design contract](references/fieldnotes-design.md). Implement presentation only. If measurements or figure files are absent, show their availability honestly and request only the inputs needed to complete the report; never substitute example observations as real results.

## Preserve the approved presentation

Read [the design contract](references/fieldnotes-design.md) when creating or editing the layout. Keep the Fieldnotes masthead, prominent observing date, compact outcome summary, opening observation table and the eight consecutive sections. Navigation tabs scroll within the document; they do not hide sections or open sibling pages.

Embed images, CSS, scripts and downloadable products/logs so the saved HTML works on its own, offline, without a local server. Enlarge figures in place. Keep prose brief: facts, status, uncertainties and actions that affect scientific interpretation. Keep the page read-only; extraction controls belong in the desktop GUI.

Reuse existing scientific figures. When generating or changing plots, use the available `plot-style` skill and the project's canonical `plot_style.py`; preserve SciencePlots, LaTeX, Hiroshige colours, inward ticks and PDF plus 300-dpi JPG outputs. If those style resources are unavailable, reuse supplied figures or obtain the required resource rather than inventing a replacement style. Small embedded web previews may be resized; original publication files remain unchanged.

## Preserve the evidence

- Derive counts, statuses, captions and downloads from the chosen revision's manifests. Match spectrum plots to product hashes; show missing or stale figures explicitly.
- Distinguish current results, retained experiments and archived runs. Calibration construction, candidate extraction and target identification are separate claims. Keep partial results, unsupported setups and failed checks visible.
- Explain unverified target identity as uncertainty that the extracted detector trace corresponds to the named object; it does not by itself mean extraction failed. A source-selection failure is a separate recorded outcome when the pipeline cannot uniquely choose a trace.
- For local background slope measurements, require usable bands on both sides of the aperture, outside the source wings and neighbouring contaminating traces. Fit the selected samples jointly at each spectral row; degree 1 measures a slope, higher orders allow curvature. Retain at least five valid samples per side after masking and rejection in the EFOSpec polynomial engine; mask unsupported rows rather than extrapolating from one side. Report the actual bands and model degree, not just the requested selection. A constant fit does not measure a slope.
- Bind recovery recipes to the exposure and input hashes. The C3 selection and raw-x background bands 520–535 and 555–575 were scoped to SN2026aebl, exposure ending `2026-10-29T05:12:40.988`; they are never defaults for a new target or epoch. Its identity and host separation remain provisional unless new evidence establishes them.
- Preserve raw data, numerical products, recipes and earlier revisions. A report-only request does not authorize another reduction or changed extraction settings.

## Finish and verify

Check the requested date and manifest totals; open a standalone copy offline and check embedded figures, section anchors, in-page enlargement, product downloads and narrow-screen layout. For code changes, run the relevant report/nightly tests. For a text-only tweak, use proportionate link and consistency checks.

Return the final daily-log path and the checks actually completed. Keep generated observing data out of version control according to the repository's rules. Commit or push only when the current task authorizes it. Describe local installation or portable packaging separately from installation in a ChatGPT workspace; a bundle alone does not establish the latter.
