/**
 * A wrapper that may scroll sideways — a wide table on a narrow screen. While its content
 * overflows, it is a named region in the tab order, so keyboard users can scroll it (WCAG
 * 2.1.1); while it fits, it stays out of the way (no extra tab stop, no extra landmark).
 * The name is the one given, else the table's label or caption, else the heading of the
 * section around it: two regions on a page must not share a name (axe landmark-unique).
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

const text = (node: Element | null | undefined) => node?.textContent?.trim() || null;

/** The names of the labelled elements around ``element`` (a region inside "Saved scenarios"
 * must not be called "Saved scenarios" too). */
function namesAround(element: HTMLElement): Set<string> {
  const names = new Set<string>();
  for (let node = element.parentElement; node; node = node.parentElement) {
    const label = node.getAttribute("aria-label")?.trim();
    if (label) names.add(label);
    for (const id of node.getAttribute("aria-labelledby")?.split(/\s+/) ?? []) {
      const labelled = text(document.getElementById(id));
      if (labelled) names.add(labelled);
    }
  }
  return names;
}

function nameOf(element: HTMLElement): string {
  const table = element.querySelector("table");
  const own = table?.getAttribute("aria-label") || text(table?.querySelector("caption"));
  if (own) return own;
  const heading = text(element.parentElement?.closest("section")?.querySelector("h2, h3, h4"));
  return heading && !namesAround(element).has(heading) ? heading : "Table";
}

export function ScrollRegion({
  label,
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () =>
      setName(element.scrollWidth > element.clientWidth + 1 ? (label ?? nameOf(element)) : null);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    return () => observer.disconnect();
  }, [label]);

  return (
    // A section is a named region only while it has a name, that is while it scrolls.
    <section
      ref={ref}
      className={className}
      aria-label={name ?? undefined}
      tabIndex={name ? 0 : undefined}
    >
      {children}
    </section>
  );
}
