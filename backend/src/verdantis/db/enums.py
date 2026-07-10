"""Enumerations used across the persistence layer.

Values are explicit uppercase strings so the PostgreSQL enum labels are stable
and readable. Adding a value later requires an ALTER TYPE migration — plan enum
sets to be additive.
"""

from enum import StrEnum


class ProvenanceMethod(StrEnum):
    """How a derived signal or verdict was obtained."""

    API = "API"  # direct provider API call
    DERIVED = "DERIVED"  # computed by us from source data
    ENRICHMENT = "ENRICHMENT"  # third-party enrichment provider
    MANUAL = "MANUAL"  # human-entered / human-confirmed


class SignalType(StrEnum):
    """Kind of derived trade signal held on a company dossier.

    NOTE: values are DERIVED intelligence, never verbatim licensed records.
    """

    COMMODITY_MATCH = "COMMODITY_MATCH"  # imports a commodity Verdantis sells
    SHIPMENT_VOLUME = "SHIPMENT_VOLUME"  # volume band over a window
    SHIPMENT_FREQUENCY = "SHIPMENT_FREQUENCY"  # shipment-count band over a window
    RECENCY = "RECENCY"  # how recent the last relevant activity is
    TREND = "TREND"  # direction of activity over time


class SignalBand(StrEnum):
    """Coarse band for a derived signal (avoids storing precise licensed figures)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class CheckType(StrEnum):
    """Category of verification check."""

    CORPORATE_EXISTENCE = "CORPORATE_EXISTENCE"  # registry / VAT / EORI / D-U-N-S
    SANCTIONS_AML = "SANCTIONS_AML"  # OFAC / EU / UN screening
    TRADE_ACTIVITY = "TRADE_ACTIVITY"  # proof of genuine import activity


class Verdict(StrEnum):
    """Outcome of a verification check. For SANCTIONS_AML, FAIL == a hit (blocking)."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class LeadSource(StrEnum):
    OUTBOUND_DISCOVERY = "OUTBOUND_DISCOVERY"
    INBOUND_FORM = "INBOUND_FORM"


class LeadStatus(StrEnum):
    NEW = "NEW"
    VERIFYING = "VERIFYING"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"  # outbound draft awaiting human approval
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ROUTED = "ROUTED"
    DISCARDED = "DISCARDED"  # e.g. sanctions hit -> hard stop


class RoutingTarget(StrEnum):
    SALES = "SALES"
    ORGANICA = "ORGANICA"  # Verdantis Organica: trade / documentation
    SUPPORT = "SUPPORT"
    TRIAGE = "TRIAGE"  # low-confidence -> human triage lane


class Incoterm(StrEnum):
    """Incoterms 2020."""

    EXW = "EXW"
    FCA = "FCA"
    FAS = "FAS"
    FOB = "FOB"
    CFR = "CFR"
    CIF = "CIF"
    CPT = "CPT"
    CIP = "CIP"
    DAP = "DAP"
    DPU = "DPU"
    DDP = "DDP"


class PaymentTerms(StrEnum):
    LC = "LC"  # letter of credit
    TT = "TT"  # telegraphic transfer
    DP = "DP"  # documents against payment
    DA = "DA"  # documents against acceptance
    OPEN_ACCOUNT = "OPEN_ACCOUNT"
    ADVANCE = "ADVANCE"
    OTHER = "OTHER"
