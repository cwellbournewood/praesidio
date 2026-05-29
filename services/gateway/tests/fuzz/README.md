# Praesidio fuzz harnesses

Coverage-guided fuzzers built on [Atheris](https://github.com/google/atheris).
Targets: the regex / secrets detectors that parse arbitrary user content.

## Install

```bash
pip install -e '.[fuzz]'
```

Atheris is an optional dependency and is **not** required for the normal test
suite or production deploys.

## Run

```bash
python -m atheris tests/fuzz/fuzz_regex_detectors.py
```

With a seed corpus (recommended for long runs):

```bash
mkdir -p corpus
python -m atheris tests/fuzz/fuzz_regex_detectors.py corpus/ -atheris_runs=1000000
```

## What it does

Each harness defines ``TestOneInput(data: bytes) -> None``: the Atheris
runtime invokes it with mutated byte buffers and records any uncaught
exception as a fuzz finding (with a reproducer file dropped next to the
harness).

The detectors are expected to handle arbitrary input gracefully — any crash
on UTF-8-decodable bytes is a bug.

## Excluded from pytest

The harness modules import asyncio and are intended to be driven by
Atheris, not pytest. ``conftest.py`` in this directory adds them to
``collect_ignore`` so a normal ``pytest -q`` skips them.
