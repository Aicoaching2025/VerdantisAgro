from __future__ import annotations

import pytest

from verdantis.core.intake.normalize import normalize_incoterm, normalize_payment_terms
from verdantis.db.enums import Incoterm, PaymentTerms


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FOB", Incoterm.FOB),
        ("fob", Incoterm.FOB),
        ("  ddp ", Incoterm.DDP),
        ("FOB Lagos", Incoterm.FOB),
        ("Free on Board", Incoterm.FOB),
        ("Cost, Insurance and Freight", Incoterm.CIF),
        (None, None),
        ("", None),
        ("nonsense", None),
    ],
)
def test_normalize_incoterm(raw: str | None, expected: Incoterm | None) -> None:
    assert normalize_incoterm(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LC", PaymentTerms.LC),
        ("letter of credit", PaymentTerms.LC),
        ("Wire Transfer", PaymentTerms.TT),
        ("D/P", PaymentTerms.DP),
        ("open account", PaymentTerms.OPEN_ACCOUNT),
        ("cash in advance", PaymentTerms.ADVANCE),
        (None, PaymentTerms.OTHER),
        ("", PaymentTerms.OTHER),
        ("nonsense", PaymentTerms.OTHER),
    ],
)
def test_normalize_payment_terms(raw: str | None, expected: PaymentTerms) -> None:
    assert normalize_payment_terms(raw) == expected
