import { z } from "zod";

// Mirrors verdantis.db.enums (backend/src/verdantis/db/enums.py). Kept as a
// single source of truth here since the frontend has no code-generation
// pipeline from the backend's Pydantic models yet.
export const leadSourceSchema = z.enum(["OUTBOUND_DISCOVERY", "INBOUND_FORM"]);
export type LeadSource = z.infer<typeof leadSourceSchema>;

export const leadStatusSchema = z.enum([
  "NEW",
  "VERIFYING",
  "QUALIFIED",
  "DISQUALIFIED",
  "PENDING_APPROVAL",
  "APPROVED",
  "REJECTED",
  "ROUTED",
  "DISCARDED",
]);
export type LeadStatus = z.infer<typeof leadStatusSchema>;

export const routingTargetSchema = z.enum(["SALES", "ORGANICA", "SUPPORT", "TRIAGE"]);
export type RoutingTarget = z.infer<typeof routingTargetSchema>;

export const incotermSchema = z.enum([
  "EXW",
  "FCA",
  "FAS",
  "FOB",
  "CFR",
  "CIF",
  "CPT",
  "CIP",
  "DAP",
  "DPU",
  "DDP",
]);
export type Incoterm = z.infer<typeof incotermSchema>;

export const paymentTermsSchema = z.enum([
  "LC",
  "TT",
  "DP",
  "DA",
  "OPEN_ACCOUNT",
  "ADVANCE",
  "OTHER",
]);
export type PaymentTerms = z.infer<typeof paymentTermsSchema>;

export const signalTypeSchema = z.enum([
  "COMMODITY_MATCH",
  "SHIPMENT_VOLUME",
  "SHIPMENT_FREQUENCY",
  "RECENCY",
  "TREND",
]);
export type SignalType = z.infer<typeof signalTypeSchema>;

export const signalBandSchema = z.enum(["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]);
export type SignalBand = z.infer<typeof signalBandSchema>;

export const checkTypeSchema = z.enum([
  "CORPORATE_EXISTENCE",
  "SANCTIONS_AML",
  "TRADE_ACTIVITY",
]);
export type CheckType = z.infer<typeof checkTypeSchema>;

export const verdictSchema = z.enum(["PASS", "FAIL", "INCONCLUSIVE"]);
export type Verdict = z.infer<typeof verdictSchema>;

// api/schemas/leads.py::LeadSummary
export const leadSummarySchema = z.object({
  id: z.uuid(),
  company_id: z.uuid().nullable(),
  company_legal_name: z.string().nullable(),
  source: leadSourceSchema,
  status: leadStatusSchema,
  fit_score: z.number().nullable(),
  routed_to: routingTargetSchema.nullable(),
  requested_commodity: z.string().nullable(),
  created_at: z.iso.datetime({ offset: true }),
});
export type LeadSummary = z.infer<typeof leadSummarySchema>;

// api/routers/leads.py::list_leads
export const leadListResponseSchema = z.object({
  items: z.array(leadSummarySchema),
  total: z.number(),
});
export type LeadListResponse = z.infer<typeof leadListResponseSchema>;

// models/dossier.py::TradeSignalView
export const tradeSignalViewSchema = z.object({
  signal_type: signalTypeSchema,
  commodity: z.string().nullable(),
  band: signalBandSchema.nullable(),
  numeric_value: z.number().nullable(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  details: z.record(z.string(), z.unknown()).nullable(),
  source: z.string(),
  retrieved_at: z.iso.datetime({ offset: true }),
  confidence: z.number(),
});
export type TradeSignalView = z.infer<typeof tradeSignalViewSchema>;

// models/dossier.py::VerificationVerdictView
export const verificationVerdictViewSchema = z.object({
  check_type: checkTypeSchema,
  verdict: verdictSchema,
  evidence: z.record(z.string(), z.unknown()).nullable(),
  source: z.string(),
  retrieved_at: z.iso.datetime({ offset: true }),
  confidence: z.number(),
});
export type VerificationVerdictView = z.infer<typeof verificationVerdictViewSchema>;

// models/dossier.py::CompanyDossier
export const companyDossierSchema = z.object({
  company_id: z.uuid(),
  tenant_id: z.uuid(),
  legal_name: z.string(),
  display_name: z.string().nullable(),
  country: z.string().nullable(),
  vat_number: z.string().nullable(),
  eori_number: z.string().nullable(),
  duns_number: z.string().nullable(),
  is_sanctioned: z.boolean(),
  sanctions_review_suggested: z.boolean(),
  credibility_score: z.number().nullable(),
  trade_signals: z.array(tradeSignalViewSchema),
  verification_results: z.array(verificationVerdictViewSchema),
});
export type CompanyDossier = z.infer<typeof companyDossierSchema>;

// api/routers/leads.py::get_lead
export const leadDetailResponseSchema = z.object({
  lead: leadSummarySchema,
  incoterm: incotermSchema.nullable(),
  payment_terms: paymentTermsSchema.nullable(),
  intake: z.record(z.string(), z.unknown()).nullable(),
  dossier: companyDossierSchema.nullable(),
});
export type LeadDetailResponse = z.infer<typeof leadDetailResponseSchema>;

// api/routers/outbound.py::OutboundRunResponse
export const outboundRunResponseSchema = z.object({
  thread_id: z.string(),
  status: z.string(),
});
export type OutboundRunResponse = z.infer<typeof outboundRunResponseSchema>;

// api/routers/outbound.py::ApprovalItem
export const approvalItemSchema = z.object({
  lead_id: z.uuid(),
  company_id: z.string(),
  legal_name: z.string(),
  country: z.string().nullable(),
  fit_score: z.number().nullable(),
  fit_reasons: z.array(z.string()),
  credibility: z.record(z.string(), z.string()),
  decision_maker_email: z.string().nullable(),
  draft_body: z.string().nullable(),
});
export type ApprovalItem = z.infer<typeof approvalItemSchema>;

export const approvalDecisionSchema = z.enum(["approve", "reject"]);
export type ApprovalDecision = z.infer<typeof approvalDecisionSchema>;

// models/tenant_config.py::TenantConfig
export const tenantConfigSchema = z.object({
  commodities: z.array(z.string()),
  regions: z.array(z.string()).nullable(),
  outbound_fit_threshold: z.number().min(0).max(1),
  inbound_fit_threshold: z.number().min(0).max(1),
  default_routing_target: routingTargetSchema,
  slack_webhook_url: z.string().nullable(),
  ack_from_email: z.string().nullable(),
  ack_from_name: z.string(),
});
export type TenantConfig = z.infer<typeof tenantConfigSchema>;

// api/schemas/suppression.py::SuppressionEntryResponse
export const suppressionEntrySchema = z.object({
  id: z.uuid(),
  email: z.string(),
  reason: z.string().nullable(),
  added_by: z.string(),
  created_at: z.iso.datetime({ offset: true }),
});
export type SuppressionEntry = z.infer<typeof suppressionEntrySchema>;
