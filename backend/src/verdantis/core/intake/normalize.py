"""Normalizes free-text Incoterms/payment-terms form input into the fixed
vocabularies Verdantis publishes (`Incoterm`, `PaymentTerms`).

Deterministic, not LLM-backed — Incoterms 2020 and standard payment-terms
phrasing are a small, fixed vocabulary, so a lookup table is both cheaper and
more auditable than a model call. Unrecognized input is not an error: the
raw string is preserved in the lead's `intake` payload regardless, and the
normalized field is left `None` (Incoterm) or `OTHER` (PaymentTerms, which
already has a catch-all member) for a human to resolve later.
"""

from __future__ import annotations

from verdantis.db.enums import Incoterm, PaymentTerms

_INCOTERM_PHRASES: dict[str, Incoterm] = {
    "ex works": Incoterm.EXW,
    "free carrier": Incoterm.FCA,
    "free alongside ship": Incoterm.FAS,
    "free on board": Incoterm.FOB,
    "cost and freight": Incoterm.CFR,
    "cost & freight": Incoterm.CFR,
    "cost, insurance and freight": Incoterm.CIF,
    "cost insurance and freight": Incoterm.CIF,
    "cost insurance freight": Incoterm.CIF,
    "carriage paid to": Incoterm.CPT,
    "carriage and insurance paid to": Incoterm.CIP,
    "delivered at place unloaded": Incoterm.DPU,
    "delivered at place": Incoterm.DAP,
    "delivered duty paid": Incoterm.DDP,
}

_PAYMENT_TERMS_PHRASES: dict[str, PaymentTerms] = {
    "letter of credit": PaymentTerms.LC,
    "l/c": PaymentTerms.LC,
    "lc": PaymentTerms.LC,
    "telegraphic transfer": PaymentTerms.TT,
    "wire transfer": PaymentTerms.TT,
    "bank transfer": PaymentTerms.TT,
    "t/t": PaymentTerms.TT,
    "tt": PaymentTerms.TT,
    "documents against payment": PaymentTerms.DP,
    "d/p": PaymentTerms.DP,
    "documents against acceptance": PaymentTerms.DA,
    "d/a": PaymentTerms.DA,
    "open account": PaymentTerms.OPEN_ACCOUNT,
    "cash in advance": PaymentTerms.ADVANCE,
    "advance payment": PaymentTerms.ADVANCE,
    "cia": PaymentTerms.ADVANCE,
}


def normalize_incoterm(raw: str | None) -> Incoterm | None:
    if not raw:
        return None
    cleaned = raw.strip().upper()
    try:
        return Incoterm(cleaned)
    except ValueError:
        pass
    # Handle values like "FOB Lagos" — take the leading code token.
    leading_token = cleaned.split()[0] if cleaned.split() else ""
    try:
        return Incoterm(leading_token)
    except ValueError:
        pass
    lowered = raw.strip().lower()
    for phrase, incoterm in _INCOTERM_PHRASES.items():
        if phrase in lowered:
            return incoterm
    return None


def normalize_payment_terms(raw: str | None) -> PaymentTerms:
    if not raw:
        return PaymentTerms.OTHER
    cleaned = raw.strip().upper().replace(" ", "_")
    try:
        return PaymentTerms(cleaned)
    except ValueError:
        pass
    lowered = raw.strip().lower()
    for phrase, terms in _PAYMENT_TERMS_PHRASES.items():
        if phrase in lowered:
            return terms
    return PaymentTerms.OTHER
