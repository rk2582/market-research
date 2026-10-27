import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { marketReport, monzoReport, notionReport, partialReport } from "../../fixtures";
import type { KeyFigure, Report } from "../../types";
import { withYear } from "./charts/KeyFigures";
import { ReportDashboard } from "./ReportDashboard";

const figures: KeyFigure[] = [
  {
    label: "Entry paid plan price",
    company: "Notion",
    value: 10,
    unit: "USD per user per month",
    year: null,
    claim_ids: ["C9"],
    refs: [2],
  },
  {
    label: "Entry paid plan price",
    company: "Craft",
    value: 6,
    unit: "USD per user per month",
    year: null,
    claim_ids: ["C40"],
    refs: [18],
  },
  { label: "Users", company: "Notion", value: 100000000, unit: "users", year: 2025, claim_ids: ["C3"], refs: [1] },
];

function renderReport(report: Report = notionReport, durationMs: number | null = 59000) {
  return render(<ReportDashboard report={report} durationMs={durationMs} />);
}

function tab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
  return screen.getByRole("tabpanel", { name });
}

describe("ReportDashboard", () => {
  it("shows the headline band and the key numbers", () => {
    renderReport();
    expect(screen.getByRole("heading", { level: 1, name: "Notion" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "notion.so" })).toHaveAttribute("href", "https://www.notion.so");
    const numbers = screen.getByRole("region", { name: "Key figures" });
    expect(within(numbers).getByText("82%")).toBeInTheDocument(); // 36 of 44
    expect(within(numbers).getByText("36 of 44 checked against their source")).toBeInTheDocument();
    expect(within(numbers).getByText("5")).toBeInTheDocument();
    expect(within(numbers).getByText("18")).toBeInTheDocument();
    expect(within(numbers).getByText("59 s")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save as PDF" })).toBeInTheDocument();
  });

  it("falls back to step times when the run time is unknown", () => {
    renderReport(notionReport, null);
    const total = notionReport.meta.usage.reduce((s, u) => s + (u.duration_ms ?? 0), 0);
    expect(
      within(screen.getByRole("region", { name: "Key figures" })).getByText(`${Math.round(total / 1000)} s`),
    ).toBeInTheDocument();
  });

  it("tabs: click and arrow keys; every tab stays in the page for printing", () => {
    renderReport();
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tabpanel", { hidden: true })).toHaveLength(5);
    tab("Analysis");
    expect(screen.getByRole("tab", { name: "Analysis" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Analysis" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Recommendations" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Recommendations" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Sources" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Sources" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Overview" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Sources" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Sources" }), { key: "Home" });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Overview" }), { key: "a" }); // ignored
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  it("a source number opens the source with every claim that cites it; Escape closes", () => {
    renderReport();
    fireEvent.click(screen.getAllByRole("button", { name: "Source 15" })[0]);
    const panel = screen.getByRole("dialog", { name: "Source 15" });
    expect(within(panel).getByRole("link", { name: "Open the page ↗" })).toHaveAttribute(
      "href",
      "https://airtable.com/pricing",
    );
    expect(within(panel).getByText(/Company website/)).toBeInTheDocument();
    expect(within(panel).getByText("Airtable — Pricing")).toBeInTheDocument();
    expect(within(panel).getByText("Unconfirmed")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Close" })).toHaveFocus();
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("third-party sources are labelled, and the panel closes from outside", () => {
    renderReport();
    fireEvent.click(screen.getAllByRole("button", { name: "Source 9" })[0]);
    const panel = screen.getByRole("dialog", { name: "Source 9" });
    expect(within(panel).getByText(/News, analyst or database/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("'show only verified claims' hides weaker claims everywhere", () => {
    renderReport();
    const competitors = tab("Competitors");
    fireEvent.click(within(competitors).getByRole("button", { name: /Asana/ }));
    let panel = screen.getByRole("dialog", { name: "Asana profile" });
    expect(within(panel).getByText("Partly verified")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));

    fireEvent.click(screen.getByRole("switch", { name: "Show only verified claims" }));
    expect(screen.getByRole("switch", { name: "Show only verified claims" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(
      within(screen.getByRole("tabpanel", { name: "Competitors" })).getByRole("button", { name: /Asana/ }),
    );
    panel = screen.getByRole("dialog", { name: "Asana profile" });
    expect(within(panel).queryByText("Partly verified")).not.toBeInTheDocument();
    expect(within(panel).queryByText("Unconfirmed")).not.toBeInTheDocument();

    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Source 15" })[0]);
    expect(screen.getByText("No claims shown with the current filter")).toBeInTheDocument();
  });

  it("competitors: cards with scores, and a comparison table", () => {
    renderReport();
    const panel = tab("Competitors");
    expect(within(panel).getByRole("button", { name: /Airtable/ })).toHaveTextContent("4 of 5 facts verified");
    expect(within(panel).getByRole("button", { name: /Craft/ })).toHaveTextContent("Indirect");
    expect(within(panel).getByText("Side-by-side comparison")).toBeInTheDocument();
    expect(within(panel).getAllByText("Not publicly available.").length).toBeGreaterThan(0);
  });

  it("analysis, recommendations and sources tabs", () => {
    renderReport();
    const analysis = tab("Analysis");
    for (const q of ["Strengths", "Weaknesses", "Opportunities", "Threats"])
      expect(within(analysis).getAllByText(q).length).toBeGreaterThan(0);
    const recs = tab("Recommendations");
    expect(within(recs).getByText(/4 recommendations, most important first/)).toBeInTheDocument();
    expect(within(recs).getAllByText("What to do").length).toBe(4);
    const sources = tab("Sources");
    expect(within(sources).getByText("How this report was made")).toBeInTheDocument();
    fireEvent.click(within(sources).getByRole("button", { name: /Craft Pricing Plans/ }));
    expect(screen.getByRole("dialog", { name: "Source 18" })).toBeInTheDocument();
  });

  it("key figures: comparable numbers as a chart, single numbers as big numbers, each with sources", () => {
    renderReport({ ...notionReport, key_figures: figures });
    expect(screen.getByText("Entry paid plan price")).toBeInTheDocument();
    const chart = screen.getByRole("list", { name: "Entry paid plan price" });
    expect(
      within(chart)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Notion102", "Craft618"]); // name, value, source number

    expect(screen.getByText("Key figures")).toBeInTheDocument();
    expect(screen.getByText("100,000,000")).toBeInTheDocument();
    expect(screen.getByText(/Notion · Users \(2025\)/)).toBeInTheDocument();
  });

  it("no key figures → no figure charts", () => {
    renderReport({ ...notionReport, key_figures: [] });
    expect(screen.queryByText("Entry paid plan price")).not.toBeInTheDocument();
    expect(screen.queryByText("Key figures")).not.toBeInTheDocument();
  });

  it("a partial report says so and marks missing sections", () => {
    renderReport(partialReport);
    expect(screen.getByRole("note")).toHaveTextContent("This is a partial report.");
    expect(screen.getByRole("note")).toHaveTextContent("Analyst timed out after 120 s");
    expect(screen.getAllByText(/not available/i).length).toBeGreaterThan(0);
    const recs = tab("Recommendations");
    expect(within(recs).getAllByText(/is not available in this report/).length).toBeGreaterThan(0);
  });

  it("works for a URL search with a different shape of data (Monzo)", () => {
    renderReport(monzoReport);
    expect(screen.getByRole("heading", { level: 1, name: "Monzo" })).toBeInTheDocument();
    tab("Competitors");
    expect(screen.getAllByText(/facts verified/).length).toBe(monzoReport.competitor_landscape.length);
  });

  it("says when the user confirmed the competitors, and which ones had no public information", () => {
    renderReport({
      ...notionReport,
      meta: { ...notionReport.meta, competitors_confirmed: true, missing_competitors: ["Asana", "Linear"] },
    });
    expect(screen.getByText("Competitors confirmed by you")).toBeInTheDocument();
    const panel = tab("Competitors");
    expect(within(panel).getByRole("note")).toHaveTextContent(
      "No reliable public information was found for Asana, Linear, so they are",
    );
  });

  it("older reports without the M12 fields show neither note", () => {
    renderReport();
    expect(screen.queryByText("Competitors confirmed by you")).not.toBeInTheDocument();
    expect(within(tab("Competitors")).queryByRole("note")).not.toBeInTheDocument();
  });

  it("one missing competitor reads naturally", () => {
    renderReport({ ...notionReport, meta: { ...notionReport.meta, missing_competitors: ["Asana"] } });
    expect(within(tab("Competitors")).getByRole("note")).toHaveTextContent("for Asana, so it is not profiled below");
  });
});

describe("ReportDashboard — market-entry report (M13)", () => {
  it("names the market, shows the disclaimer and market tab names", () => {
    renderReport(marketReport);
    expect(screen.getByText("Market-entry report")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Fresh packaged milk" })).toBeInTheDocument();
    expect(screen.getByText("Kerala")).toBeInTheDocument();
    expect(screen.getByText("households")).toBeInTheDocument();
    expect(screen.getAllByRole("note")[0]).toHaveTextContent("not a recommendation to invest and not financial advice");
    expect(
      within(screen.getByRole("region", { name: "Key figures" })).getByText("Players profiled"),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Overview",
      "Players",
      "Analysis",
      "Entry options",
      "Sources",
    ]);
  });

  it("overview: bottom line and market snapshot", () => {
    renderReport(marketReport);
    const panel = screen.getByRole("tabpanel", { name: "Overview" });
    expect(within(panel).getByRole("heading", { name: "Bottom line" })).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "Market snapshot" })).toBeInTheDocument();
    expect(within(panel).getByText("What this covers:")).toBeInTheDocument();
    expect(within(panel).getByText("Market size")).toBeInTheDocument();
    expect(within(panel).getByText("Licences and rules")).toBeInTheDocument();
  });

  it("analysis: five forces with ratings and evidence, unrated ones say so, signals for and against", () => {
    renderReport(marketReport);
    const panel = tab("Analysis");
    expect(within(panel).queryByText("Strengths")).not.toBeInTheDocument();
    const barriers = within(panel).getByRole("listitem", { name: "Entry barriers" });
    expect(within(barriers).getByText("High")).toBeInTheDocument();
    expect(within(barriers).getAllByRole("button").length).toBeGreaterThan(0); // cite chips
    const substitutes = within(panel).getByRole("listitem", { name: "Substitutes" });
    expect(within(substitutes).getByText("Not rated")).toBeInTheDocument();
    expect(within(substitutes).getByText("Not enough sourced evidence to rate this.")).toBeInTheDocument();
    expect(within(panel).getByLabelText("Signals for entering")).toHaveTextContent(
      "consumes more milk than it produces",
    );
    expect(within(panel).getByLabelText("Signals against entering")).toHaveTextContent("collection");
    expect(within(panel).getByRole("heading", { name: "Risks" })).toBeInTheDocument();
  });

  it("entry options and the check-before-you-invest list", () => {
    renderReport(marketReport);
    const panel = tab("Entry options");
    expect(within(panel).getByText(/2 entry options, most promising first/)).toBeInTheDocument();
    expect(
      within(panel).getByRole("heading", { name: /^Entry option 1:\s*Start a premium A2 milk subscription/ }),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "Check before you invest" })).toBeInTheDocument();
    expect(
      within(panel).getByText("Ask 3 distributors in Kochi what margin they take on packaged milk."),
    ).toBeInTheDocument();
  });

  it("players tab and panel use market wording", () => {
    renderReport(marketReport);
    const panel = tab("Players");
    fireEvent.click(within(panel).getAllByRole("button", { name: /GreenCow Organics/ })[0]);
    expect(screen.getByRole("dialog", { name: "GreenCow Organics profile" })).toHaveTextContent(
      "Player in this market",
    );
  });

  it("a market report whose analysis failed says so instead of showing empty forces", () => {
    renderReport({
      ...marketReport,
      meta: {
        ...marketReport.meta,
        outcome: "partial",
        missing_sections: ["swot", "recommendations"],
        step_errors: { analyse: "Analyst timed out" },
      },
      market: {
        ...marketReport.market!,
        forces: [],
        signals_for: [],
        signals_against: [],
        checks_before_investing: [],
      },
      recommendations: [],
    });
    expect(within(tab("Analysis")).getByText(/The market analysis is not available/)).toBeInTheDocument();
    expect(within(tab("Entry options")).getByText(/The checklist is not available/)).toBeInTheDocument();
  });

  it("marks research-firm estimates, shows missing topics, and never doubles a year", () => {
    renderReport(marketReport);
    const panel = screen.getByRole("tabpanel", { name: "Overview" });
    const snapshot = within(panel)
      .getByRole("heading", { name: "Market snapshot" })
      .closest("section, div")!.parentElement!;
    expect(within(panel).getAllByText("Estimate · research firm").length).toBeGreaterThanOrEqual(2); // the claim + its figure
    expect(within(panel).getByText(/IMARC estimates the Kerala dairy market/)).toBeInTheDocument();
    expect(within(snapshot).getByText("Costs and margins")).toBeInTheDocument();
    expect(within(panel).getByText("Not found in public sources — check this yourself.")).toBeInTheDocument();
    expect(within(panel).getByText("Market · Kerala dairy market, all dairy (2025)")).toBeInTheDocument(); // not "(2025) (2025)"
    expect(within(panel).getByText(/estimates are marked/)).toBeInTheDocument();
  });

  it("withYear adds the year only when the label lacks it", () => {
    expect(withYear("Market size", 2025)).toBe("Market size (2025)");
    expect(withYear("Production increase by 2030", 2030)).toBe("Production increase by 2030");
    expect(withYear("Users", null)).toBe("Users");
  });

  it("no players: says so in market words", () => {
    renderReport({ ...marketReport, competitor_landscape: [], competitive_comparison: [] });
    expect(within(tab("Players")).getByText("No main players were found for this market.")).toBeInTheDocument();
  });
});

describe("ReportDashboard — research-more loop (M14)", () => {
  function withSecondRound(round: NonNullable<Report["meta"]["second_round"]>, oldYear: number | null = 2018): Report {
    const [first, ...rest] = notionReport.company_overview.facts;
    const facts = [
      { ...first, claims: [{ ...first.claims[0], old_source_year: oldYear }, ...first.claims.slice(1)] },
      ...rest,
    ];
    return {
      ...notionReport,
      company_overview: { ...notionReport.company_overview, facts },
      meta: {
        ...notionReport.meta,
        second_round: round,
        usage: [
          ...notionReport.meta.usage,
          {
            step: "deepen",
            agent_version: "gap_researcher@1",
            model: "gpt-4.1-mini",
            input_tokens: 9000,
            output_tokens: 900,
            total_tokens: 9900,
            tool_calls: 5,
            duration_ms: 31000,
          },
          {
            step: "competitors",
            agent_version: "competitor_researcher@1",
            model: "gpt-4.1-mini",
            input_tokens: 12000,
            output_tokens: 1200,
            total_tokens: 13200,
            tool_calls: 8,
            duration_ms: 18000,
          },
        ],
      },
    };
  }

  it("labels old sources, summarises the second round and shows its time", () => {
    renderReport(
      withSecondRound({
        gaps: ["Coda: its pricing", "Notion: funding or ownership"],
        filled: 1,
        new_claims: 3,
        total_tokens: 9900,
        duration_ms: 31000,
        error: null,
      }),
    );
    const panel = screen.getByRole("tabpanel", { name: "Overview" });
    expect(within(panel).getByText("Old source (2018)")).toBeInTheDocument();
    expect(within(panel).getByText("Second research round: 1 of 2 gaps filled, 3 new claims.")).toBeInTheDocument();
    expect(within(panel).getByText("Coda: its pricing")).toBeInTheDocument();
    const sources = tab("Sources");
    expect(within(sources).getByText("Second round")).toBeInTheDocument();
    expect(within(sources).getByText("Competitor researchers")).toBeInTheDocument();
  });

  it("says when the second round did not finish", () => {
    renderReport(
      withSecondRound(
        {
          gaps: ["Coda: its pricing"],
          filled: 0,
          new_claims: 1,
          total_tokens: 0,
          duration_ms: 120000,
          error: "timed out",
        },
        null,
      ),
    );
    expect(
      screen.getByText("A second research round for 1 gap did not finish; this report uses the first round."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Old source/)).not.toBeInTheDocument();
  });
});
