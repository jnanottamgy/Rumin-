/**
 * A wrapper that may scroll sideways — a wide table on a narrow screen. While its content
 * overflows, it is a named region in the tab order, so keyboard users can scroll it (WCAG
 * 2.1.1); while it fits, it stays out of the way (no extra tab stop, no extra landmark).
 * The name is the table's caption or label unless one is given.
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

function nameOf(element: HTMLElement): string {
  const table = element.querySelector("table");
  return (
    table?.getAttribute("aria-label") ??
    table?.querySelector("caption")?.textContent?.trim() ??
    "Table"
  );
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
