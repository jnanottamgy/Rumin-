import { LoadingState } from "@/components/States";

/** Shown while a code-split page is being fetched on first load. */
export function RouteLoading() {
  return (
    <div style={{ padding: "var(--space-12) var(--gutter)" }}>
      <LoadingState label="Loading RUMIN…" />
    </div>
  );
}
