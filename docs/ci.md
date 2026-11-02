# Tests and automatic badges

- Workflow: [build](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml).
- Runner: Ubuntu 22.04, Python 3.11; no IRAF/PyRAF installation.
- Dependencies: project extras plus shared runtime/CI numeric versions in `constraints.txt`.
- `constraints-ci.txt` remains a compatibility entry point to those same pins.
- Observer environment: `environment.yml` installs runtime extras without the `test` extra.
- Graphics: real LaTeX rendering; no font/backend substitutions.
- Checks: package build, dependency consistency, tests, and an **85% package line-coverage floor**.
- Fixtures: synthetic FITS; small legacy references remain comparison-test inputs.
- Synthetic raw photons exercise actual PypeIt masters, response fitting, native export and replay without legacy-file access.

## Run locally

```sh
# Keep development tools separate from the observer environment.
conda activate efospec
python -m venv --system-site-packages outputs/efospec-tests
source outputs/efospec-tests/bin/activate
python -m pip install -c constraints-ci.txt -e '.[rapid,plots,test,desktop,desktop-test]'
python -m pip check
python -m playwright install chromium
python -m build --wheel --no-isolation
QT_API=pyside6 QT_QPA_PLATFORM=offscreen MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m pytest -v --cov=efospec --cov-report=term-missing
```

- Install the README's LaTeX dependencies first.
- Tests cover inventory, naming, associations, adapter metadata, calibration math, profiles, reports, and metrics.
- A synthetic exposure exercises all four PDF/JPG figure types and the HTML report.
- Native preflight tests reject archived substitutes and unsupported readiness claims.
- Coverage measures Python in `src/efospec/`; it excludes preserved legacy code, plotting scripts, and JavaScript.
- Real Chromium tests separately exercise browser-prototype clicks, sky drags, recipe reload, two-source extraction, downloads, and replay.
- CI installs Chromium; local existing Chrome: set `EFOSPEC_TEST_CHROME` to its executable.
- Browser testing belongs to the `test` extra; observer environments need no Playwright.
- Separate pytest-qt tests exercise the desktop controls and real subprocess lifecycle. Linux CI uses Qt/XCB under Xvfb; macOS Cocoa is checked locally.
- Injected-source tests run actual PypeIt, with three noise/brightness cases and a 2% median-flux target.
- Both archived grism fits, whole-line holdouts, full-run sky shifts, sky-mask replay, and reference-flux checks are tested.
- Passing tests establish software contracts, not scientific calibration accuracy.

## Badge updates

- Python badge: declared package floor; full CI currently exercises 3.11.
- Build badge: real GitHub Actions result.
- Test count and coverage: parsed JUnit/coverage XML from each default-branch push.
- Metrics live on the repository's `badges` branch; `source.json` links their source commit/run.
- Failed/incomplete tests cannot publish green counts or complete coverage.
- Trusted default-branch pushes publish using a temporary GitHub token.
- Pull requests receive read-only permissions and never publish metrics.
- Badge errors cannot turn passing tests into a failed build.

## Merge repair — 2 November 2026

- Duplicate `desktop` extras made TOML parsing fail before installation or tests.
- Keep one PySide6 desktop extra and validate TOML before system dependency installation.
- Both editors use PySide6; mixing PyQt6 widgets with a PySide6 Matplotlib canvas raises `TypeError`.
- Native execution is implemented; preflight still reports `reduction_ready=False` until scientific validation.
- Coverage marked **unavailable** after the failed installation was correct. Fresh default-branch CI must pass before the badge republishes a percentage.

## Setup verification

- [First verified run](https://github.com/sPaMFouR/EFOSpec/actions/runs/41220735230): 31 October 2026, source `51a230e`.
- Step logs: package build passed; **74 tests passed**; **58.6%** package line coverage.
- Metrics were published successfully; JSON and all four rendered SVG badges were checked.
- README metrics update automatically; this dated record describes setup verification only.

## Native/desktop verification — 1 November 2026

- [Verified Linux run](https://github.com/sPaMFouR/EFOSpec/actions/runs/41262157980), tested source `bbd82c0`.
- **170 passed; 91.7% coverage**; wheel build and `pip check` passed.
- Real Qt/XCB startup, source/sky edits, workers, cancellation and replay passed under Xvfb.
- Synthetic raw-photon reduction passed without legacy calibration access.
- Initial Qt startup failure traced to three missing XCB libraries; runtime dependencies corrected.
- This branch generates metric artifacts; default-branch badges remain unchanged until integration.
