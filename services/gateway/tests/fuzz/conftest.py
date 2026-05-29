"""Tell pytest to ignore the atheris harness modules.

The fuzz harnesses are designed to be invoked by ``python -m atheris …`` and
have side-effects (long-running infinite loop) when imported as tests.
"""
collect_ignore = ["fuzz_regex_detectors.py"]
