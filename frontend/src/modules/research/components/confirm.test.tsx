import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockFetch } from "@/test/mockFetch";
import { fixtureRunList, identifyResult } from "../fixtures";
import type { IdentifyResult } from "../types";
import { ConfirmSheet } from "./ConfirmSheet";

afterEach(() => vi.unstubAllGlobals());

const started = { ...fixtureRunList.items[0], id: "new-run" };

function open(result: IdentifyResult | { status: number; body: unknown } = identifyResult, startRoute: object = { status: 202, body: started }) {
  const identify = "status" in result ? result : { body: result };
  const fetchState = mockFetch({ "POST /api/v1/research/identify": identify, "POST /api/v1/research": startRoute });
  const onClose = vi.fn();
  const onStarted = vi.fn();
  render(<ConfirmSheet query="Notion" onClose={onClose} onStarted={onStarted} />);
  return { ...fetchState, onClose, onStarted };
}

const lastBody = (calls: Array<{ body?: unknown }>) => calls.at(-1)?.body;

describe("ConfirmSheet", () => {
  it("shows a check in progress that can be cancelled", async () => {
    const { onClose } = open();
    expect(screen.getByText("Checking “Notion”…")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Checking" })).toBeInTheDocument(); // the spinner
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
    await screen.findByRole("dialog", { name: "Confirm company and competitors" }); // let the request settle
  });

  it("starts with the confirmed company and the edited competitor list", async () => {
    const { calls, onStarted } = open();
    const sheet = await screen.findByRole("dialog", { name: "Confirm company and competitors" });
    expect(within(sheet).getByRole("radio", { name: /Notion/ })).toBeChecked();
    expect(within(sheet).getByRole("link", { name: "Source ↗" })).toHaveAttribute("href", "https://www.notion.so");
    expect(within(sheet).getByText("3 of 6")).toBeInTheDocument();
    expect(within(sheet).getByRole("heading", { name: /Main product lines/ })).toBeInTheDocument();
    expect(within(sheet).getByText("Docs and wikis")).toBeInTheDocument();
    expect(within(sheet).getByText("Project management · Databases for teams")).toBeInTheDocument();
    expect(within(sheet).getByText("Weak evidence: only on a company-database list")).toBeInTheDocument();

    fireEvent.click(within(sheet).getByRole("button", { name: "Remove Confluence" }));
    const input = within(sheet).getByLabelText("Add a competitor (name or website)");
    fireEvent.change(input, { target: { value: "ClickUp" } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Add" }));
    fireEvent.change(input, { target: { value: "asana.com" } });
    fireEvent.submit(input);
    expect(within(sheet).getAllByText("Added by you")).toHaveLength(2);

    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(started));
    expect(lastBody(calls)).toEqual({
      query: "Notion",
      company: { name: "Notion", website: "https://www.notion.so" },
      competitors: [
        { name: "Airtable", website: "https://airtable.com", added_by_user: false },
        { name: "Coda", website: "https://coda.io", added_by_user: false },
        { name: "ClickUp", website: null, added_by_user: true },
        { name: "asana.com", website: "https://asana.com", added_by_user: true },
      ],
    });
  });

  it("rejects bad, duplicate and too many competitors", async () => {
    open();
    const sheet = await screen.findByRole("dialog");
    const input = within(sheet).getByLabelText("Add a competitor (name or website)");
    const add = (value: string) => {
      fireEvent.change(input, { target: { value } });
      fireEvent.click(within(sheet).getByRole("button", { name: "Add" }));
    };
    add("http://localhost");
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Local addresses are not allowed");
    add("coda");
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Coda is already on the list");
    add("https://airtable.com/pricing");
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Airtable is already on the list"); // same website
    add("ClickUp");
    add("Asana");
    add("Monday");
    expect(within(sheet).getByText("6 of 6")).toBeInTheDocument();
    expect(input).toBeDisabled();
    expect(within(sheet).getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("lets the user pick between several matches", async () => {
    const { calls } = open({
      ...identifyResult,
      query: "Mercury",
      note: "Mercury can mean several companies; pick one.",
      matches: [
        { name: "Mercury", website: "https://mercury.com", description: "US business banking.", source_url: "https://mercury.com" },
        { name: "Mercury Systems", website: "https://mrcy.com", description: "Defence electronics.", source_url: "https://mrcy.com" },
      ],
    });
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("Mercury can mean several companies; pick one.")).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("radio", { name: /Mercury Systems/ }));
    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    await waitFor(() => expect(lastBody(calls)).toMatchObject({ company: { name: "Mercury Systems", website: "https://mrcy.com" } }));
  });

  it("with no clear match it still lets the user start", async () => {
    const { calls } = open({ ...identifyResult, matches: [], competitors: [], note: "" });
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("heading", { name: "We couldn’t confirm “Notion”" })).toBeInTheDocument();
    expect(within(sheet).getByText(/None yet/)).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    await waitFor(() => expect(lastBody(calls)).toEqual({ query: "Notion", competitors: [] }));
  });

  it("when the check fails, offers to start without confirming", async () => {
    const { calls, onStarted } = open({ status: 502, body: { detail: "The quick check failed. You can start without confirming.", code: "identify_failed" } });
    const sheet = await screen.findByRole("dialog", { name: "Quick check unavailable" });
    expect(sheet).toHaveTextContent("The quick check failed.");
    fireEvent.click(within(sheet).getByRole("button", { name: "Start without confirming" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(lastBody(calls)).toEqual({ query: "Notion" });
  });

  it("shows why a run could not start and allows another try", async () => {
    open(identifyResult, { status: 429, body: { detail: "2 research run(s) already in progress", code: "capacity_reached" } });
    const sheet = await screen.findByRole("dialog");
    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    expect(await within(sheet).findByRole("alert")).toHaveTextContent("2 research run(s) already in progress");
    expect(within(sheet).getByRole("button", { name: "Start research" })).toBeEnabled();
  });

  const milk: IdentifyResult = {
      ...identifyResult,
      query: "Milk",
      kind: "market",
      matches: [{ name: "Milk Makeup", website: "https://milkmakeup.com", description: "Cosmetics brand.", source_url: "https://milkmakeup.com" }],
      competitors: [],
      market: { product: "Fresh packaged milk", region: "Kerala", customer_type: null },
      note: "",
    };

  it("a market: shows the scope and starts a market-entry run", async () => {
    const { calls, onStarted } = open(milk);
    const sheet = await screen.findByRole("dialog", { name: "Market research" });
    expect(within(sheet).getByRole("heading", { name: "This looks like a market, not a company" })).toBeInTheDocument();
    expect(within(sheet).getByLabelText("Product or idea")).toHaveValue("Fresh packaged milk");
    expect(within(sheet).getByLabelText("Region")).toHaveValue("Kerala");
    expect(within(sheet).getByRole("note")).toHaveTextContent("not investment advice");
    fireEvent.change(within(sheet).getByLabelText("Customers (optional)"), { target: { value: " households " } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Start market research" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(started));
    expect(lastBody(calls)).toEqual({
      query: "Notion",
      mode: "market",
      market: { product: "Fresh packaged milk", region: "Kerala", customer_type: "households" },
    });
  });

  it("a market needs a product and a region before it starts", async () => {
    const { calls } = open({ ...milk, market: { product: "Milk", region: null, customer_type: null } });
    const sheet = await screen.findByRole("dialog", { name: "Market research" });
    fireEvent.click(within(sheet).getByRole("button", { name: "Start market research" }));
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Enter a region");
    expect(within(sheet).getByLabelText("Region")).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(within(sheet).getByLabelText("Product or idea"), { target: { value: " " } });
    expect(within(sheet).queryByRole("alert")).not.toBeInTheDocument(); // typing clears the message
    fireEvent.change(within(sheet).getByLabelText("Region"), { target: { value: "Global" } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Start market research" }));
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Enter the product or idea.");
    expect(calls.filter((c) => c.method === "POST" && c.url.endsWith("/api/v1/research"))).toHaveLength(0);
  });

  it("a market start that fails shows the error and can be retried", async () => {
    open(milk, { status: 429, body: { detail: "Too many research runs in progress.", code: "capacity" } });
    const sheet = await screen.findByRole("dialog", { name: "Market research" });
    fireEvent.click(within(sheet).getByRole("button", { name: "Start market research" }));
    expect(await within(sheet).findByText("Too many research runs in progress.")).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Start market research" })).toBeEnabled();
  });

  it("a market can be switched to the matched company instead", async () => {
    const { calls } = open(milk);
    let sheet = await screen.findByRole("dialog", { name: "Market research" });
    fireEvent.click(within(sheet).getByRole("button", { name: /Research Milk Makeup/ }));
    sheet = screen.getByRole("dialog", { name: "Confirm company and competitors" });
    expect(within(sheet).getByRole("radio", { name: /Milk Makeup/ })).toBeChecked();
    fireEvent.click(within(sheet).getByRole("button", { name: "Start research" }));
    await waitFor(() => expect(lastBody(calls)).toMatchObject({ company: { name: "Milk Makeup" }, competitors: [] }));
  });

  it("the user can switch between company and market views", async () => {
    open({ ...identifyResult, market: null });
    let sheet = await screen.findByRole("dialog", { name: "Confirm company and competitors" });
    fireEvent.click(within(sheet).getByRole("button", { name: "This is a product or market, not a company" }));
    sheet = screen.getByRole("dialog", { name: "Market research" });
    expect(within(sheet).getByLabelText("Product or idea")).toHaveValue("Notion"); // defaults to what was typed
    expect(within(sheet).getByText("Matched Notion Labs.")).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: "This is a company" }));
    expect(screen.getByRole("dialog", { name: "Confirm company and competitors" })).toBeInTheDocument();
  });

  it("Escape and a click outside close the sheet", async () => {
    const { onClose } = open();
    const sheet = await screen.findByRole("dialog");
    fireEvent.keyDown(sheet, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
