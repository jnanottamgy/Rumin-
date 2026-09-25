/**
 * ScrollRegion: a named, focusable region only while its table is wider than the screen,
 * and never two regions with one name on a page (axe landmark-unique, found on a phone).
 * jsdom has no layout, so the widths are set by hand.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Panel } from "@/components/Panel";
import { ScrollRegion } from "@/components/ScrollRegion";

function widths(scroll: number, client: number) {
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(scroll);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(client);
}

afterEach(() => {
  vi.restoreAllMocks();
});

const table = (props: { "aria-label"?: string; caption?: string } = {}) => (
  <table aria-label={props["aria-label"]}>
    {props.caption && <caption>{props.caption}</caption>}
    <tbody>
      <tr>
        <td>1</td>
      </tr>
    </tbody>
  </table>
);

describe("ScrollRegion", () => {
  it("stays out of the way while its content fits", () => {
    widths(300, 300);
    render(<ScrollRegion>{table({ "aria-label": "Prices" })}</ScrollRegion>);
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.getByRole("table").parentElement).not.toHaveAttribute("tabindex");
  });

  it("is a focusable region named like its table while it scrolls", () => {
    widths(700, 300);
    render(<ScrollRegion>{table({ "aria-label": "Prices" })}</ScrollRegion>);
    const region = screen.getByRole("region", { name: "Prices" });
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("takes the caption, then the heading of its panel, so names do not repeat", () => {
    widths(700, 300);
    render(
      <>
        <Panel title="Instruments and prices">
          <ScrollRegion>{table()}</ScrollRegion>
        </Panel>
        <Panel title="Recent ingestion runs">
          <ScrollRegion>{table()}</ScrollRegion>
        </Panel>
        <ScrollRegion>{table({ caption: "Values rounded to two decimals." })}</ScrollRegion>
      </>,
    );
    const names = screen.getAllByRole("region").map((region) => region.getAttribute("aria-label"));
    expect(names).toEqual([
      "Instruments and prices",
      "Recent ingestion runs",
      "Values rounded to two decimals.",
    ]);
  });

  it("does not repeat the name of a region it sits in", () => {
    widths(700, 300);
    render(
      <section aria-labelledby="saved">
        <h2 id="saved">Saved scenarios</h2>
        <ScrollRegion>{table()}</ScrollRegion>
      </section>,
    );
    expect(screen.getByRole("region", { name: "Table" })).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: "Saved scenarios" })).toHaveLength(1);
  });

  it("prefers the name it is given", () => {
    widths(700, 300);
    render(<ScrollRegion label="Monthly values">{table({ "aria-label": "Prices" })}</ScrollRegion>);
    expect(screen.getByRole("region", { name: "Monthly values" })).toBeInTheDocument();
  });
});
