# Tests and automatic badges

- Workflow: [build](https://github.com/sPaMFouR/epessto-plus/actions/workflows/build.yml).
- Runner: Ubuntu 22.04, Python 3.11; no IRAF/PyRAF installation.
- Dependencies: project extras plus tested numeric versions in `constraints-ci.txt`.
- Graphics: real LaTeX rendering; no font/backend substitutions.
- Checks: package build, dependency consistency, tests, and package line coverage.
- Fixtures: synthetic FITS; small legacy references remain comparison-test inputs.
- Native end-to-end calibration is **not** covered yet: [missing inputs and work](native-calibration.md).

## Run locally

```sh
python -m pip install -c constraints-ci.txt -e '.[rapid,plots,test]'
python -m pip check
python -m build --wheel --no-isolation
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m pytest -v --cov=epessto_plus --cov-report=term-missing
```

- Install the README's LaTeX dependencies first.
- Tests cover inventory, naming, associations, adapter metadata, calibration math, profiles, reports, and metrics.
- A synthetic exposure exercises all four PDF/JPG figure types and the HTML report.
- Native preflight tests reject archived substitutes and unsupported readiness claims.
- Coverage measures `src/epessto_plus/`; it excludes preserved legacy code and plotting scripts.
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
