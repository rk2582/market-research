// Mirrors the backend's public API (backend/schemas/api.py and backend/schemas/report.py).
// Keep these in sync when the backend changes.

export type InputType = "name" | "url";
export type RunStatus = "running" | "succeeded" | "partial" | "failed";
export type StepName = "research" | "validate" | "analyse" | "strategise" | "write";
export type StepState = "pending" | "running" | "completed" | "failed" | "skipped";

export interface ResearchRunSummary {
  id: string;
  query: string;
  input_type: InputType;
  company_name: string | null;
  status: RunStatus;
  mode?: "company" | "market"; // added in M13
  created_at: string;
  finished_at: string | null;
  // Added in M11 (null while running or without a report; older backends omit them).
  duration_ms?: number | null;
  verified_pct?: number | null;
  competitor_count?: number | null;
}

export interface ResearchRunList {
  items: ResearchRunSummary[];
  total: number;
}

export interface StepInfo {
  name: StepName;
  status: StepState;
  duration_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
}

export interface RunTotals {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  duration_ms: number | null;
}

export interface ResearchRunDetail extends ResearchRunSummary {
  website_url: string | null;
  error: string | null;
  agno_run_id: string | null;
  // "competitors" = M15 parallel competitor researchers; "deepen" = M14 second research round (both inside Research)
  current_step: StepName | "competitors" | "deepen" | null;
  totals: RunTotals;
  steps: StepInfo[];
  has_report: boolean;
}

// --- Report ---------------------------------------------------------------------------

export type ClaimKind = "fact" | "interpretation" | "prediction";
export type Verdict = "supported" | "partially_supported" | "unsupported" | "contradicted";
export type Confidence = "high" | "medium" | "low";
export type Outcome = "succeeded" | "partial" | "failed";

export interface ReportClaim {
  id: string;
  text: string;
  kind: ClaimKind;
  verdict: Verdict;
  confidence: Confidence;
  refs: number[];
  /** M13: rests on a market-research firm's summary page — one firm's estimate. */
  estimate?: boolean;
  /** M14: a trend, price or recent-news claim whose only dated source is more than 3 years old. */
  old_source_year?: number | null;
}

export interface FactGroup {
  label: string;
  claims: ReportClaim[];
}

export interface CompanyOverview {
  name: string;
  website: string | null;
  identity: ReportClaim | null;
  facts: FactGroup[];
}

export interface CompetitorProfile {
  name: string;
  website: string | null;
  relation: "direct" | "indirect";
  facts: FactGroup[];
}

export interface IndustryOverview {
  text: string;
  claims: ReportClaim[];
}

export interface ComparisonCell {
  company: string;
  value: string;
  refs: number[];
}

export interface ComparisonRow {
  dimension: string;
  cells: ComparisonCell[];
}

export interface Insight {
  id: string;
  text: string;
  kind: ClaimKind;
  claim_ids: string[];
  refs: number[];
}

export interface Swot {
  strengths: Insight[];
  weaknesses: Insight[];
  opportunities: Insight[];
  threats: Insight[];
}

export interface Recommendation {
  priority: number;
  title: string;
  rationale: string;
  impact: "high" | "medium" | "low";
  next_steps: string[];
  risks_tradeoffs: string[];
  evidence_ids: string[];
  refs: number[];
  warning: string | null;
}

export interface Reference {
  ref: number;
  url: string;
  title: string | null;
  retrieved_by: string;
}

export interface ValidationSummary {
  claims_total: number;
  supported: number;
  partially_supported: number;
  unsupported: number;
  contradicted: number;
  warnings: string[];
}

export interface StepUsage {
  step: string;
  agent_version: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  tool_calls: number;
  duration_ms: number | null;
}

export interface ReportMeta {
  query: string;
  company_name: string;
  generated_at: string;
  outcome: Outcome;
  missing_sections: string[];
  step_errors: Record<string, string>;
  agent_versions: Record<string, string>;
  usage: StepUsage[];
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  // Added in M12 (older reports omit them).
  competitors_confirmed?: boolean;
  missing_competitors?: string[];
  mode?: "company" | "market"; // added in M13
  second_round?: SecondRound | null; // M14
}

/** M14: one targeted research round after fact-checking, for the gaps code found. */
export interface SecondRound {
  gaps: string[];
  filled: number;
  new_claims: number;
  total_tokens: number;
  duration_ms: number | null;
  error: string | null;
}

// --- Market-entry reports (M13) ---------------------------------------------------------------------

export type ForceName = "rivalry" | "entry_barriers" | "supplier_power" | "buyer_power" | "substitutes";

export interface ForceRating {
  force: ForceName;
  rating: "low" | "medium" | "high";
  reason: string;
  claim_ids: string[];
  refs: number[];
}

export interface MarketSection {
  scope: { product: string; region: string; customer_type: string | null };
  forces: ForceRating[];
  signals_for: Insight[];
  signals_against: Insight[];
  checks_before_investing: string[];
  not_found?: string[]; // snapshot topics with nothing in public sources
  disclaimer: string;
}

/** A number for charts; the backend keeps it only when it appears in a verified claim it cites. */
export interface KeyFigure {
  label: string;
  company: string;
  value: number;
  unit: string;
  year: number | null;
  claim_ids: string[];
  refs: number[];
  estimate?: boolean; // M13: only backed by a market-research firm's estimate
}

export interface Report {
  meta: ReportMeta;
  executive_summary: string;
  company_overview: CompanyOverview;
  industry_overview: IndustryOverview;
  competitor_landscape: CompetitorProfile[];
  competitive_comparison: ComparisonRow[];
  swot: Swot;
  market_trends: Insight[];
  opportunities: Insight[];
  risks: Insight[];
  recommendations: Recommendation[];
  next_steps: string[];
  references: Reference[];
  validation: ValidationSummary;
  key_figures?: KeyFigure[]; // M11; older reports have none
  market?: MarketSection | null; // M13: market-entry reports only
}

export const STEP_NAMES: StepName[] = ["research", "validate", "analyse", "strategise", "write"];
export const TERMINAL_STATUSES: RunStatus[] = ["succeeded", "partial", "failed"];

// --- Confirm step (M12): POST /api/v1/research/identify -------------------------------------------

export interface CompanyChoice {
  name: string;
  website: string | null;
  description: string;
  source_url: string;
}

export interface CompetitorChoice {
  name: string;
  website: string | null;
  competes_in?: string; // the company's product line, e.g. "Instant noodles"
  reason: string;
  source_url: string;
  weak_evidence?: boolean; // only found on a company-database list
}

export interface ProductLine {
  name: string;
  brands: string[];
}

export interface MarketScope {
  product: string;
  region: string | null;
  customer_type: string | null;
}

export interface IdentifyResult {
  query: string;
  input_type: InputType;
  kind: "company" | "market";
  matches: CompanyChoice[];
  product_lines?: ProductLine[];
  competitors: CompetitorChoice[];
  market: MarketScope | null;
  note: string;
  total_tokens: number;
  duration_ms: number | null;
}

/** What the user confirmed; sent with POST /api/v1/research. */
export interface ConfirmedCompetitor {
  name: string;
  website: string | null;
  added_by_user: boolean;
}

export interface StartOptions {
  company?: { name: string; website: string | null };
  competitors?: ConfirmedCompetitor[];
  mode?: "company" | "market";
  market?: { product: string; region: string; customer_type: string | null };
}

export const MAX_COMPETITORS = 6;
