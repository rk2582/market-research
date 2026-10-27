import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/test/mockFetch";
import { fixtureReports, fixtureRunList, fixtureRuns, identifyResult } from "../fixtures";
import type { ResearchRunSummary } from "../types";
import { HistoryStats, HomeScreen } from "./HomeScreen";
import { NewResearchForm } from "./NewResearchForm";
import { activityLog, ProgressView } from "./ProgressView";
import { RecentResearch } from "./RecentResearch";
import { ResearchRunScreen } from "./ResearchRunScreen";
import { POLL_INTERVAL_MS, RunPage } from "./RunPage";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => push.mockReset());

function type(value: string) {
  fireEvent.change(screen.getByLabelText("Company name or website"), { target: { value } });
}

function Form({ onSubmit }: { onSubmit: (q: string) => Promise<void> }) {
  const [value, setValue] = useState("");
  return <NewResearchForm value={value} onChange={setValue} onSubmit={onSubmit} />;
}

describe("NewResearchForm", () => {
  it("shows the rule before calling the backend, and clears it when typing", async () => {
    const onSubmit = vi.fn();
    render(<Form onSubmit={onSubmit} />);
    type("http://localhost:3000");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Local addresses are not allowed");
    expect(screen.getByLabelText("Company name or website")).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();
    type("Notion");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("submits the cleaned query", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<Form onSubmit={onSubmit} />);
    type("  Notion   Labs ");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("Notion Labs"));
    expect(screen.getByRole("button", { name: "Research" })).toBeEnabled();
  });

  it("shows errors from the backend, or a generic message", async () => {
    const { unmount } = render(<Form onSubmit={vi.fn().mockRejectedValue(new Error("2 runs already in progress"))} />);
    type("Monzo");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("2 runs already in progress");
    unmount();
    render(<Form onSubmit={vi.fn().mockRejectedValue("boom")} />);
    type("Monzo");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start the research");
  });
});

describe("HomeScreen", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows recent research; Research opens the confirm sheet, which starts the run", async () => {
    const { calls } = mockFetch({
      "GET /api/v1/research?limit=20&offset=0": { body: fixtureRunList },
      "POST /api/v1/research/identify": { body: identifyResult },
      "POST /api/v1/research": { status: 202, body: { ...fixtureRunList.items[0], id: "new-run" } },
    });
    render(<HomeScreen />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Know your market.Verified.");
    expect(await screen.findByRole("link", { name: /Monzo/ })).toBeInTheDocument();
    type("Notion");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    const sheet = await screen.findByRole("dialog", { name: "Confirm company and competitors" });
    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/research/new-run"));
    expect(calls.at(-1)).toMatchObject({ method: "POST", body: { query: "Notion", company: { name: "Notion" } } });
  });

  it("Back closes the confirm sheet", async () => {
    mockFetch({
      "GET /api/v1/research?limit=20&offset=0": { body: { items: [], total: 0 } },
      "POST /api/v1/research/identify": { body: identifyResult },
    });
    render(<HomeScreen />);
    type("Notion");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("example chips fill the search box", async () => {
    mockFetch({ "GET /api/v1/research?limit=20&offset=0": { body: { items: [], total: 0 } } });
    render(<HomeScreen />);
    fireEvent.click(screen.getByRole("button", { name: "monzo.com" }));
    expect(screen.getByLabelText("Company name or website")).toHaveValue("monzo.com");
    expect(await screen.findByText(/No research yet/)).toBeInTheDocument();
  });

  it("shows the backend's reason when a run cannot start", async () => {
    mockFetch({
      "GET /api/v1/research?limit=20&offset=0": { body: { items: [], total: 0 } },
      "POST /api/v1/research/identify": { body: identifyResult },
      "POST /api/v1/research": {
        status: 429,
        body: { detail: "2 research run(s) already in progress", code: "capacity_reached" },
      },
    });
    render(<HomeScreen />);
    type("Notion");
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Start research" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("2 research run(s) already in progress");
    expect(push).not.toHaveBeenCalled();
  });

  it("explains when the history cannot load, and retries", async () => {
    mockFetch({
      "GET /api/v1/research?limit=20&offset=0": [
        { status: 502, body: { detail: "down", code: "backend_unavailable" } },
        { body: fixtureRunList },
      ],
    });
    render(<HomeScreen />);
    expect(await screen.findByText("Recent research could not be loaded")).toBeInTheDocument();
    expect(screen.getByText(/The research service is not running/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: /Monzo/ })).toBeInTheDocument();
  });
});

describe("HistoryStats and RecentResearch", () => {
  const runs = fixtureRunList.items;

  it("averages finished reports and rounds the competitor count", () => {
    render(<HistoryStats runs={runs} />);
    const stats = screen.getByRole("region", { name: "Your reports so far" });
    expect(within(stats).getByText("3")).toBeInTheDocument(); // notion, monzo, partial
    expect(within(stats).getByText("Claims verified").nextSibling).toHaveTextContent(/^\d+%$/);
    expect(within(stats).getByText("Competitors").nextSibling).toHaveTextContent(/^\d+$/);
  });

  it("is hidden without finished reports, and skips unknown numbers", () => {
    const { container } = render(<HistoryStats runs={runs.filter((r) => r.status === "failed")} />);
    expect(container).toBeEmptyDOMElement();
    const bare: ResearchRunSummary[] = [{ ...runs[1], verified_pct: null, duration_ms: null, competitor_count: null }];
    render(<HistoryStats runs={bare} />);
    expect(screen.queryByText("Claims verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Time per report")).not.toBeInTheDocument();
  });

  it("cards show the trust score, or the status when there is none", () => {
    render(<RecentResearch runs={runs} />);
    const monzo = screen.getByRole("link", { name: /Monzo/ });
    expect(monzo).toHaveAttribute("href", "/research/demo-monzo");
    expect(monzo).toHaveTextContent("claims verified");
    expect(screen.getByRole("link", { name: /Acme Widgets/ })).toHaveTextContent("Failed");
    expect(screen.getByRole("link", { name: /Notion Labs/ })).toHaveTextContent("partial");
  });

  it("market runs carry a Market label and count players", () => {
    const market: ResearchRunSummary = {
      ...runs[0],
      mode: "market",
      company_name: "Fresh packaged milk · Kerala",
      query: "Milk",
      competitor_count: 4,
    };
    render(<RecentResearch runs={[market]} />);
    const card = screen.getByRole("link", { name: /Fresh packaged milk/ });
    expect(within(card).getByText("Market")).toBeInTheDocument();
    expect(card).toHaveTextContent("4 players");
  });
});

describe("ProgressView", () => {
  it("activity log: started/finished per step, failure at the stop time, no time for skipped", () => {
    const failed = fixtureRuns["demo-failed"].steps;
    expect(activityLog(failed, 31)).toEqual([
      { at: 31, agent: "Researcher", text: "Researcher timed out after 300 s", tone: "error" },
      ...["Fact-Checker", "Analyst", "Strategist", "Writer"].map((agent) => ({ at: null, agent, text: "Skipped" })),
    ]);
    const log = activityLog(fixtureRuns["demo-running"].steps);
    expect(log.map((l) => [l.at, l.text])).toEqual([
      [0, "Started: company, news and competitors"],
      [8, "Finished · 13,500 tokens"],
      [8, "Started: every claim vs its source"],
      [16, "Finished · 13,500 tokens"],
      [16, "Working: comparison, swot, trends…"],
    ]);
    const timed = failed.map((s, i) => (i === 0 ? { ...s, duration_ms: 12000, error: null } : s));
    expect(activityLog(timed)[0]).toMatchObject({ at: 12, text: "Failed" });
  });

  it("shows the pipeline, clock and counters while running", () => {
    render(<ProgressView run={fixtureRuns["demo-running"]} />);
    expect(screen.getByRole("heading", { level: 1, name: "Researching Canva" })).toBeInTheDocument();
    expect(screen.getByLabelText("Research progress")).toBeInTheDocument();
    const steps = within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem");
    expect(steps).toHaveLength(5);
    expect(within(steps[2]).getByRole("img")).toHaveAccessibleName(/in progress/);
    expect(screen.getByText("2 of 5")).toBeInTheDocument();
  });

  it("the second research round shows as Research filling gaps", () => {
    const steps = fixtureRuns["demo-running"].steps.map((s, i) => ({
      ...s,
      status: i === 0 ? ("running" as const) : i === 1 ? ("completed" as const) : ("pending" as const),
    }));
    render(<ProgressView run={{ ...fixtureRuns["demo-running"], current_step: "deepen", steps }} />);
    expect(screen.getAllByText("Filling gaps (second round)").length).toBeGreaterThan(0);
  });

  it("parallel competitor research shows inside Research", () => {
    const run = { ...fixtureRuns["demo-running"], current_step: "competitors" as const };
    const { unmount } = render(<ProgressView run={run} />);
    expect(screen.getAllByText("Researching competitors in parallel").length).toBeGreaterThan(0);
    unmount();
    render(<ProgressView run={{ ...run, mode: "market" }} />);
    expect(screen.getAllByText("Researching players in parallel").length).toBeGreaterThan(0);
  });

  it("a market run says what it is researching", () => {
    render(<ProgressView run={{ ...fixtureRuns["demo-running"], mode: "market", company_name: "Milk · Kerala" }} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Researching the market for Milk · Kerala" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Market, prices, rules and players").length).toBeGreaterThan(0);
    expect(screen.getByText("Started: market, prices, rules and players")).toBeInTheDocument();
  });

  it("explains a failure and offers a new research", () => {
    render(<ProgressView run={fixtureRuns["demo-failed"]} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Acme Widgets Ltd could not be researched");
    expect(screen.getByRole("alert")).toHaveTextContent("Research step failed: Researcher timed out after 300 s.");
    expect(screen.getByText("until it stopped")).toBeInTheDocument();
    expect(screen.getAllByText("0:31")).toHaveLength(2); // clock and the failure in the activity log
  });

  it("uses a generic message when the failure has no reason", () => {
    render(<ProgressView run={{ ...fixtureRuns["demo-failed"], error: null }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("A step failed. No report was created.");
  });
});

describe("ResearchRunScreen", () => {
  it("shows progress while running and the report when done", () => {
    const { unmount } = render(<ResearchRunScreen run={fixtureRuns["demo-running"]} report={null} />);
    expect(screen.getByLabelText("Research progress")).toBeInTheDocument();
    unmount();
    render(<ResearchRunScreen run={fixtureRuns["demo-notion"]} report={fixtureReports["demo-notion"]} />);
    expect(screen.getByText("Market intelligence report")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Notion" })).toBeInTheDocument();
  });
});

describe("RunPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("follows a run from in progress to the finished report", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { calls } = mockFetch({
      "GET /api/v1/research/r1": [
        { body: fixtureRuns["demo-running"] },
        { body: { ...fixtureRuns["demo-monzo"], id: "r1" } },
      ],
      "GET /api/v1/research/r1/report": { body: fixtureReports["demo-monzo"] },
    });
    render(<RunPage id="r1" />);
    expect(await screen.findByLabelText("Research progress")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByRole("heading", { level: 1, name: "Monzo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save as PDF" })).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3));
    expect(calls.filter((c) => c.url.endsWith("/r1"))).toHaveLength(2); // polling stopped when finished
  });

  it("shows a failed run without asking for a report", async () => {
    const { calls } = mockFetch({ "GET /api/v1/research/r2": { body: fixtureRuns["demo-failed"] } });
    render(<RunPage id="r2" />);
    expect(await screen.findByText("This research could not be completed")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/report"))).toBe(false);
  });

  it("says when the run does not exist", async () => {
    mockFetch({ "GET /api/v1/research/nope": { status: 404, body: { detail: "not found", code: "run_not_found" } } });
    render(<RunPage id="nope" />);
    expect(await screen.findByRole("heading", { name: "Research not found" })).toBeInTheDocument();
  });

  it("offers a retry when the backend is down at first load", async () => {
    mockFetch({
      "GET /api/v1/research/r3": [
        { status: 502, body: { detail: "down", code: "backend_unavailable" } },
        { body: fixtureRuns["demo-failed"] },
      ],
    });
    render(<RunPage id="r3" />);
    expect(await screen.findByText("This research could not be loaded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("This research could not be completed")).toBeInTheDocument();
  });

  it("keeps showing progress if contact is lost mid-run, with a way to reconnect", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetch({
      "GET /api/v1/research/r4": [
        { body: fixtureRuns["demo-running"] },
        { status: 502, body: { detail: "down", code: "backend_unavailable" } },
      ],
    });
    render(<RunPage id="r4" />);
    expect(await screen.findByLabelText("Research progress")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByText("Lost contact with the research service")).toBeInTheDocument();
    expect(screen.getByLabelText("Research progress")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
  });

  it("explains when the report cannot load, and retries", async () => {
    mockFetch({
      "GET /api/v1/research/r5": { body: { ...fixtureRuns["demo-notion"], id: "r5" } },
      "GET /api/v1/research/r5/report": [
        { status: 500, body: { detail: "An unexpected error occurred.", code: "internal_error" } },
        { body: fixtureReports["demo-notion"] },
      ],
    });
    render(<RunPage id="r5" />);
    expect(await screen.findByText("The report could not be loaded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Notion" })).toBeInTheDocument();
  });
});
