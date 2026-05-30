"""IBAN tolerance for spaces and hyphens between groups (Task 1.2)."""
from __future__ import annotations

import pytest

from section_gateway.dlp.detectors import regex as det_regex


@pytest.mark.asyncio
async def test_iban_tight_form_still_matches():
    """Existing tight tests must keep passing — regression guard."""
    f = await det_regex.detect("IBAN: GB82WEST12345698765432")
    assert any(x.label == "financial.iban" for x in f)


@pytest.mark.asyncio
async def test_iban_with_spaces():
    f = await det_regex.detect("IBAN: DE89 3704 0044 0532 0130 00")
    assert any(x.label == "financial.iban" for x in f)


@pytest.mark.asyncio
async def test_iban_with_hyphens():
    f = await det_regex.detect("IBAN: DE89-3704-0044-0532-0130-00")
    assert any(x.label == "financial.iban" for x in f)


@pytest.mark.asyncio
async def test_iban_mixed_separators():
    f = await det_regex.detect("Wire: DE89 3704-0044 0532-0130 00 today.")
    assert any(x.label == "financial.iban" for x in f)


@pytest.mark.asyncio
async def test_iban_too_short_rejected():
    """Two-letter country + check + 5 chars is below IBAN min length."""
    f = await det_regex.detect("not an iban: DE89 1234")
    assert not any(x.label == "financial.iban" for x in f)
