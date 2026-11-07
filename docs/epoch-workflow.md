# One observing epoch at a time

Always name the observing date. One invocation processes one date only. For the next epoch, change the date; there is no automatic multi-night loop.

The user-approved **2026-10-29** page is the final daily-log template for both October nights and future epochs. Keep its Fieldnotes structure and use the masthead **ePESSTO+ / EFOSpec**. Calibration checks appear in AT, SN, then other-source order; failed or unvalidated checks are red. The optional `$webpage-spectralatlas` coding-agent skill is installed in the user's agent configuration, outside this repository. The pipeline does not require a skill installation to generate its report.

Activate the existing EFOSpec Python environment and run from the EFOSpec checkout:

```sh
efospec night 2026-10-28
# Equivalent checkout script:
python scripts/reduce_epoch.py 2026-10-28
```

To inspect each stage separately:

```sh
python scripts/01_log_epoch.py 2026-10-28
python scripts/02_reduce_epoch.py 2026-10-28
python scripts/03_report_epoch.py 2026-10-28
```

- CLI equivalents: `efospec night DATE --stage log`, `reduce`, or `report`.
- Numbered scripts use the checkout as project root; the CLI uses the current directory.
- `--project-root PATH` selects another project containing `data/` and `runs/`.
- The engine and reference files always come from the code checkout.
- Downloads remain explicit: `efospec download DATE --with-calibrations`.

## Stages

| Stage | Work |
| --- | --- |
| Observing log | Inventory `data/DATE/`; record FITS roles, dates and hashes in CSV/JSON |
| Reduction | Verify unchanged inputs; reduce science/standards using archived calibrations |
| Final report | Build the nightly log, plots and candidate QC; retain partial results |

- Observing date spans noon UTC to noon the next day.
- Science/standard exposures from another night stop the workflow.
- Calibration/acquisition frames retain their actual dates and roles.
- Complete worker output goes into dated logs.

## Dated outputs

Open **`runs/2026-10-28/index.html`**.

```text
runs/2026-10-28/nightly/<processing-UTC>-<unique-id>/
  observing-log.csv
  observing-log.json
  night.json
  index.html
  logs/2026-10-28-workflow.log
  logs/2026-10-28-reduction.log
  logs/2026-10-28-report.log
  reduction/                 # run.json, spectra, plots, nightly report
  QC/<raw-exposure>/         # candidate images and recipes
```

- Every log/all-stages invocation creates a new processing revision.
- `current.json` selects the revision used by separate reduction/report steps.
- Repeating extraction in an existing revision is rejected; start with `log` again.
- The report can be regenerated without re-extraction.
- Raw files and accepted products remain unchanged.

## Portable nightly log

- The date's `index.html` contains observations, spectra, issues, source/background QC, calibrations and archive summaries.
- The final section is **Reduction Archive**: retained reductions, folder locations,
  then **Download logs** (log files only). There is no separate Run record section
  or archive-calibration/status/revision caption beneath the date. Manifests and
  provenance remain saved on disk.
- Figures and product/log downloads are embedded; a copied HTML file works offline.
- Figure enlargement and navigation stay within the page; existing PDF/JPG exports are preserved.
- `nightly/index.html` remains an entry to revision-specific records.
- Rebuild from saved results without re-extraction or new plots:

```sh
python scripts/build_epoch_fieldnotes.py 2026-10-28
```

For explicitly selected targets, [bounded PypeIt background trials](local-pypeit-background.md)
save their geometry checks, candidate recipes and new extraction revisions inside
the date's `QC/` folder. These trials do not replace `nightly/current.json`.

[Acquisition catalogue QC](acquisition-catalogues.md) optionally solves acquisition
images locally and adds NED/SDSS/AllWISE overlays to Source QC. Its dated command
is separate from reduction; rebuilding the report uses only saved results.

## Retained results

| Folder under `runs/DATE/` | Contents |
| --- | --- |
| `nightly/` | Current workflow and processing revisions |
| `QC/` | Retained manual source/background experiments |
| `calibrations/` | Retained masters and group selections |
| `archive/` | Earlier reductions, diagnostics, inventories and logs |

- Use the date's `index.html`/`README.md` when available, or `nightly/index.html`.
- Write new results inside dated revisions.
- Older compatibility links are read-only destinations for existing recipes/records.

## Status and limits

- [Integrated reduction checks](reduction-checks.md) now save sky-line fits,
  PypeIt correlation comparisons, calibration readiness and native 2D diagnostics.
  `--native-calibrations RUN` adds contemporary raw-master checks to the same
  dated invocation, with their own status and report section.

| Exit | Meaning |
| --- | --- |
| `0` | Requested stage complete; all three stages complete for a successful full run |
| `1` | Partial reduction or report/QC failures |
| `2` | Operational/input error |

- Reporting continues after partial reduction. For separate steps, run `report` even after exit `1`.
- `night.json` records stage outcomes; missing/incomplete workers cannot become successes.
- A per-date lock prevents concurrent operations. Inspect its PID before removing a stale `.running` lock.
- This workflow uses the experimental archive-calibration path; native calibration remains separate.
- Candidate QC prepares inspection materials; it does not identify or extract a target automatically.
- Recovery recipes remain bound to exposure/input hashes. A previous source's bands are never global defaults.

## Reviewed targets and targeted reruns

- `--target SN2026ayt` restricts a new dated revision to that exact FITS `OBJECT`.
  The nightly log states this scope; other exposures remain visible as outside
  the selection. Earlier full-night reductions remain in the archive.
- `--reviewed-sources FILE.json` records explicit visual identifications and
  exposure-specific bounded PypeIt recipes. The selection file is copied and
  hashed inside the revision. Each entry identifies the raw basename/hash,
  object, parent run, recipe path/hash, candidate number and operator evidence.
- The recipe's original input hashes are verified. Fresh raw electrons, detector
  window and wavelength map must match the reviewed parent exactly before the
  source geometry can be reused. The sky fit and extraction are recomputed.
  A mismatch fails explicitly; identification is never transferred by name alone.
- Successful reviewed targets retain their original candidate IDs in Source QC,
  with new residual images and summed background-subtracted profiles. Visual
  identification remains distinct from automatic astrometric identification.
- Confirmed choices take precedence: SN2026ayt C2 and SN2026aadx C3. Otherwise
  choose the strongest positive PypeIt peak with detection S/N >=5 inside the
  existing +/-15-pixel central window; ties or missing detections remain explicit
  failures. This geometry rule alone does not confirm target identity.
- An `operator_background` review permits an exposure-specific bounded recipe
  without promoting its nominal source identity to visually confirmed status.
  Local fits allow up to 100 rejection iterations while retaining the same
  clipping, convergence and two-sided support gates.
- AT/SN targets appear first in observation tables and spectrum/QC sections,
  grouped by target and time. Sorting never changes header-based frame roles.

## Recorded verification

- Night **2026-10-28**: observing log/report complete; reduction explicitly partial.
- Candidate QC generated for that date; the next epoch was not started.
- All **193** raw hashes unchanged; report links and 300-dpi PDF/JPG pairs checked.
- Original workflow validation: **174 tests passed, 90.69% coverage**; wheel build passed.
- Evidence: the dated `nightly/current.json`, its revision's `verification.json`, and `runs/epoch-workflow-full-tests.log`.
- [Current desktop validation](validation-desktop-2026-11.md) · [Desktop guide](desktop.md).
