import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { Card, CardTitle } from "./Card";
import { Monogram } from "./Monogram";
import { Pill } from "./Pill";
import { SiteHeader } from "./SiteHeader";
import { StatTile } from "./StatTile";
import { Switch } from "./Switch";
import { ErrorState } from "./ErrorState";
import { PrintButton } from "./PrintButton";
import { Skeleton } from "./Skeleton";
import { Spinner } from "./Spinner";
import { StatusBadge } from "./StatusBadge";

describe("ui", () => {
  it("Button defaults to a non-submitting button", () => {
    render(<Button variant="quiet">Retry</Button>);
    expect(screen.getByRole("button", { name: "Retry" })).toHaveAttribute("type", "button");
  });

  it("Spinner and Skeleton are accessible", () => {
    render(<Spinner />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    render(<Skeleton lines={4} />);
    expect(screen.getByTestId("skeleton").children).toHaveLength(4);
  });

  it.each([
    ["running", "Running"],
    ["succeeded", "Complete"],
    ["partial", "Partial report"],
    ["failed", "Failed"],
  ] as const)("StatusBadge %s", (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("ErrorState offers a retry only when given one", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ErrorState title="Backend unavailable" message="Start it and retry." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<ErrorState title="Backend unavailable" message="Start it and retry." onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("PrintButton opens the print dialog", () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(<PrintButton />);
    fireEvent.click(screen.getByRole("button", { name: "Save as PDF" }));
    expect(print).toHaveBeenCalledOnce();
  });

  it("SiteHeader links home, to history and to a new research", () => {
    render(<SiteHeader />);
    expect(screen.getByRole("link", { name: "Market360" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "/#recent");
    expect(screen.getByRole("link", { name: "New research" })).toHaveAttribute("href", "/#start");
  });

  it("Monogram shows the first letter (or ?) and is hidden from screen readers", () => {
    const { container } = render(
      <>
        <Monogram name=" notion" />
        <Monogram name="" size="lg" />
        <Monogram name="Monzo" size="md" onMuted />
      </>,
    );
    const tiles = container.querySelectorAll("[aria-hidden='true']");
    expect([...tiles].map((t) => t.textContent)).toEqual(["N", "?", "M"]);
  });

  it("Switch reports the next state", () => {
    const onChange = vi.fn();
    const { rerender } = render(<Switch checked={false} onChange={onChange} label="Verified only" />);
    fireEvent.click(screen.getByRole("switch", { name: "Verified only" }));
    expect(onChange).toHaveBeenCalledWith(true);
    rerender(<Switch checked onChange={onChange} label="Verified only" />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenLastCalledWith(false);
  });

  it("Card, CardTitle, StatTile and Pill render their content", () => {
    render(
      <Card>
        <CardTitle title="Evidence" note="Checked" id="ev" />
        <StatTile label="Claims verified" value="82%" note="36 of 44" align="center" />
        <StatTile label="Sources" value="18" />
        <Pill tone="verified">Verified</Pill>
        <Pill>Plain</Pill>
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Evidence" })).toHaveAttribute("id", "ev");
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Plain")).toBeInTheDocument();
  });
});
