import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { formatDateTime } from "@/modules/research/lib/format";
import { LocalTime } from "./LocalTime";

const ISO = "2026-10-21T23:42:16Z";

describe("LocalTime", () => {
  it("renders UTC on the server, so the first browser render matches it", () => {
    expect(renderToString(<LocalTime iso={ISO} />)).toContain("21 Oct 2026, 23:42 UTC");
  });

  it("switches to the reader's time zone after loading", () => {
    render(<LocalTime iso={ISO} />);
    const time = screen.getByText(formatDateTime(ISO));
    expect(time.tagName).toBe("TIME");
    expect(time).toHaveAttribute("datetime", ISO);
  });
});
