# One observing epoch at a time

Always name the observing date. One invocation processes one date only. For the next epoch, change the date; there is no automatic multi-night loop.

Activate the existing EFOSpec Python environment and run from the EFOSpec checkout:

```sh
python scripts/reduce_epoch.py 2026-10-28
```

This executes the following three scripts' shared stages in order. To inspect each stage before continuing, run them separately instead:

```sh
python scripts/01_log_epoch.py 2026-10-28
python scripts/02_reduce_epoch.py 2026-10-28
python scripts/03_report_epoch.py 2026-10-28
```

The next epoch is a separate invocation:

```sh
python scripts/reduce_epoch.py 2026-10-29
```

Equivalent installed entry point: `efospec night 2026-10-28`. Add `--stage log`, `--stage reduce` or `--stage report` for an individual stage. The numbered scripts default to the checkout as their project root, even when invoked from another directory; the CLI defaults to the current directory. `--project-root PATH` overrides either. The selected project contains `data/` and `runs/`; the engine and reference files come from the code checkout.

## Stages and dated outputs

1. **Observing log:** inventory `data/YYYY-MM-DD/`; save a CSV observing log and full JSON provenance before reduction. Include acquisition and calibration frames with their roles and actual dates. Science/standard frames from a different observing night stop the workflow. An epoch spans noon UTC on the requested date to noon the following day.
2. **Reduction:** verify that the logged raw-file set and hashes have not changed; reduce all science and standard exposures in that epoch through the existing archive-calibration path. Capture complete worker output in a log whose filename and header include the date.
3. **Final report:** generate the existing house-style plots and candidate QC images for source-selection failures. Assemble the observing table, outcomes, spectra, QC and retained diagnostics in the date's single Fieldnotes page, with embedded product and log downloads. Partial science results still get a final report.

The stable entry page for an epoch is:

```text
runs/2026-10-28/index.html
```

Each observing-log/all-stages invocation creates a fresh processing revision:

```text
runs/2026-10-28/nightly/<processing-UTC>-<unique-id>/
  observing-log.csv
  observing-log.json
  night.json
  index.html
  logs/2026-10-28-workflow.log
  logs/2026-10-28-reduction.log
  logs/2026-10-28-report.log
  reduction/                 # run.json, spectra, plots, Fieldnotes report
  QC/<raw-exposure>/         # candidate images and recipes, when required
```

The date's entry page is a single Fieldnotes document with consecutive sections for the observing log, spectra, issues, source QC, saved background experiments, native calibrations, archive and run record. Navigation stays within the page. Images and product/log downloads are embedded, so the HTML also works when copied by itself; clicking a figure enlarges it in place. Web previews reuse the existing house-style figures; original PDF/JPG files remain unchanged.

Rebuild this page from saved evidence without reducing data or regenerating plots:

```sh
python scripts/build_epoch_fieldnotes.py 2026-10-28
```

The processing timestamp identifies a revision; the parent folder and every report/log identify the **observing date**. `current.json` points to the revision used by the separate reduction/report steps. Previous revisions, raw files and accepted products are preserved. Repeating the reduction stage on an existing revision is rejected; start with the log step for a new reduction. The report stage can be rerun without re-extraction. The older `nightly/index.html` remains an entry to revision-specific records.

## Keeping an epoch readable

Use `runs/YYYY-MM-DD/index.html` as the date's entry page when present, or `nightly/index.html` for the current workflow. For **2026-10-28**, the local `runs/2026-10-28/README.md` folder guide routes the retained products:

- `nightly/`: the current workflow and its complete processing revisions.
- `QC/`: retained reviewed-source experiments, including the original SN2026aebl C3 selection.
- `calibrations/`: validated masters and group selections.
- `archive/`: superseded reductions, earlier calibration attempts, inventories, diagnostic runs and loose logs.

New workflow files stay inside their dated revision. Older path names may be compatibility links: they preserve immutable recipes/manifests and must not be used as new output destinations. Archive relocation does not delete raw data or rewrite scientific provenance.

## Status and limits

- Exit `0`: requested stage succeeded; a full successful run has all three stages complete. Exit `1`: partial results or report/QC failures. Exit `2`: an operational/input error. The all-stages wrapper continues to reporting after a partial science reduction. When stepping manually, run the report even when the reduction returned `1`; do not connect these commands with `&&` if partial results must be reported.
- `night.json` records each stage. Missing workers/manifests do not become successful reductions. A fatal input error retains its dated error log and an entry page when a revision was created.
- A per-date lock prevents overlapping operations on the same epoch. If a process is killed and leaves `.running`, check that its recorded PID is no longer active before removing that lock.
- This orchestrates the existing experimental archive-calibration pipeline. It does not enable unsupported setups or finish native flux-calibrated extraction. Native calibration construction/diagnostics remain separate commands.
- Candidate QC prepares inspection images and recipes; it does not automatically extract every candidate or identify a supernova. Manual recovery recipes remain bound to their exposure and input hashes. The SN2026aebl C3 bands are not a global or next-epoch default; previous C3 recovery products remain in their original QC folders.
- Downloads remain explicit: `efospec download YYYY-MM-DD --with-calibrations`. The nightly scripts require downloaded inputs and do not silently select a different date.

## Verification

The complete dated workflow was exercised on **2026-10-28**: observing log and final report complete, reduction explicitly partial because existing scientific failures/skips remain. Candidate QC was generated for that date only; the next epoch was not started. All 193 downloaded raw hashes for this night were unchanged, all report links resolved, and the generated PDF/JPG pairs passed the 300-dpi check. Full suite: **174 passed, 90.69% coverage**; wheel build passed. Evidence: `runs/2026-10-28/nightly/current.json`, its revision's `verification.json`, and `runs/epoch-workflow-full-tests.log`.
