import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fixtureRunList, fixtureRuns } from "@/modules/research/fixtures";
import { mockFetch } from "@/test/mockFetch";
import HomePage from "./page";
import NotFound from "./not-found";
import ResearchRunPage from "./research/[id]/page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
afterEach(() => vi.unstubAllGlobals());

describe("pages", () => {
  it("home shows the form and recent research", async () => {
    mockFetch({ "GET /api/v1/research?limit=20&offset=0": { body: fixtureRunList } });
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Know your market.Verified.");
    expect(await screen.findByRole("link", { name: /Monzo/ })).toBeInTheDocument();
  });

  it("run page follows the run with the id from the URL", async () => {
    mockFetch({ "GET /api/v1/research/demo-failed": { body: fixtureRuns["demo-failed"] } });
    render(await ResearchRunPage({ params: Promise.resolve({ id: "demo-failed" }) }));
    expect(await screen.findByText("This research could not be completed")).toBeInTheDocument();
  });

  it("404 page offers a way back", () => {
    render(<NotFound />);
    expect(screen.getByRole("link", { name: "Start a new research" })).toHaveAttribute("href", "/");
  });
});
