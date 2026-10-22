# Thompson regex engine

A regex matcher that compiles patterns to a Thompson NFA and simulates it with state sets, so it never backtracks. There's also an optional subset construction that turns the NFA into a DFA.

Supported syntax: literals, `.`, concatenation, `|`, `*`, `+`, `?`, parentheses, and character classes like `[a-z]`, `[^abc]`. A backslash makes the next character literal (`\.`, `\*`), so `\d` and friends aren't supported. Matching is `fullmatch` only.

[Setup](#setup) · [Run](#run) · [Benchmark](#benchmark) · [Tests](#test)

## Setup

Python 3.10+ and nothing else. You only need `pytest` if you want to run the tests.

## Run

```bash
python regex_engine.py                  # benchmark
python regex_engine.py "a(b|c)*d" abcbd # match one string, prints True/False
```

## Benchmark

The benchmark matches `(a?){n}a{n}` (written out as `a?a?...aaa`) against `a{n}`. Python's `re` backtracks through roughly 2^n ways to split the input, so each `re` timing runs in a child process that gets killed after 3 seconds. Once it times out, the larger n values are skipped. One run on my laptop:

```text
   n     NFA sim   DFA build+run       python re
   5     1.12 ms         0.30 ms         0.04 ms
  10     0.28 ms         0.44 ms         0.10 ms
  15     0.57 ms         0.82 ms         1.83 ms
  20     0.72 ms         1.30 ms        70.46 ms
  22     0.82 ms         1.60 ms       273.58 ms
  24     0.94 ms         1.78 ms          1.23 s
  26     1.06 ms         2.37 ms           > 3 s
  30     1.29 ms         2.46 ms           > 3 s
 100    12.13 ms        25.43 ms           > 3 s
```

For small n, `re` wins because it's C. By n=26 it can't finish in 3 seconds, and the NFA handles n=100 in about 12 ms.

## Test

Install the test dependency:

```bash
pip install pytest
```

```bash
python -m pytest -q
```

Along with hand-written cases and parse errors, the tests generate 800 random patterns over a small alphabet and check the NFA and the DFA against `re.fullmatch` on 20,000 random strings.
