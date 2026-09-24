# Contributing

## The one rule that matters

**A number without a source does not go in.** Every correlation, factor, price
and default in teakit carries a citation in the docstring or the data record
beside it. If you add a value, add where it came from and what year it is on.
"I have seen this used" is not a source; a document with a URL is.

If a value is judgement rather than data — location factors, utility prices,
wage burdens — say so explicitly in the docstring and mark it as a starting
point to be replaced. Users are entitled to know which of teakit's numbers they
can defend in a review and which they cannot.

## Tests

Pin behaviour to published values, not to yesterday's output.

```python
def test_loh_appendix_a_installed_cost(self):
    """DOE/NETL-2002/1169 Appendix A: $62,000 bare -> $150,245 installed."""
    r = tea.installed_cost_loh(62_000, "gas_gt400F_lt150psig", "heat exchanger")
    assert round(r["installed_cost"]) == 150_245
```

catches a methodology regression. This:

```python
def test_installed_cost(self):
    assert round(installed_cost_loh(62_000, ...)["installed_cost"]) == 150_245  # noqa
```

with no docstring and no source catches the same regression but tells the next
person nothing about whether the expected value is right.

Invariant tests are the other half: cost monotone in size, the capital ladder
monotone, escalation reversible, `simple` below `dcf`. They catch whole classes
of error that reference values miss.

```bash
python -m pytest tests -q                       # acceptance + application
python -m pytest --doctest-modules src/teakit -q  # 225 doctests
ruff check src tests
```

## Zero runtime dependencies

This is a hard constraint, not a preference. teakit runs on a stock Python in a
plant office with no network, and every dependency is a future portability
problem. CI fails the build if `teakit` grows a runtime requirement.

If you need a third-party library for something optional, put it behind an
extra and an `ImportError` with a clear message — see
`ChartSpec.to_matplotlib()` for the pattern.

## Docstrings

Every public function needs: what it computes, the source, the parameters with
units, and a doctest. Units are not optional. A cost estimating library that
does not say whether a figure is per hour or per year is a hazard.

Say what the function is *for* and when it is the wrong choice. The docstring
for `simple_levelized_cost` says it will understate by 30-50%; that sentence is
more useful than the formula.

## Adding an equipment correlation

Correlations live in `equipment_data.py`, regressed from tabulated data, and
must carry: exponent, base size, base cost, cost basis year, validity range,
R², relative RMSE, point count, a `reliable` flag and a `caution` string. A fit
outside 0.2–1.3 on the exponent, or over a narrow size span, must be flagged
unreliable with the reason — the tests check that the flag reaches the user.

Do not widen a validity range to make a correlation cover your case. Extrapolate
explicitly at the call site instead, where it is recorded.

## The application

`teakit/app/api.py` is pure `dict` in, `dict` out — no HTTP, no I/O, no globals.
Logic goes there so it can be tested with plain function calls. `server.py` is a
thin shim and should stay thin. `static/` uses no framework, no build step and
no external resource; the tests fail if an off-origin URL appears.

The frontend/backend contract is checked in `tests/test_app.py`: every
`data-path` in the HTML must resolve against a real project field, and every
endpoint the JavaScript calls must exist. Rename on one side and the tests tell
you about the other.

## Licensing of contributions

teakit is under the PolyForm Noncommercial License 1.0.0: free for
noncommercial use, with commercial use licensed separately by the author.
For that to keep working there has to be a single rights holder who can grant
those commercial licences, so by opening a pull request you agree that your
contribution is licensed under the same terms and that the author may also
license it commercially. If that does not suit you, open an issue instead and
we can work out the change without a code contribution.

## Style

`ruff check src tests`. 92 columns. Prefer a clear name to a comment, and a
comment that explains *why* to one that restates the code.
