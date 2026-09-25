import { isRouteErrorResponse, useRouteError } from "react-router";
import { ButtonLink } from "@/components/Button";
import { ErrorState } from "@/components/States";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

/** Catches rendering errors so a crash in one page never leaves a blank screen. */
export function RouteErrorPage() {
  const error = useRouteError();
  useDocumentTitle("Something went wrong");
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";

  return (
    <div style={{ maxWidth: "44rem", margin: "0 auto", padding: "var(--space-16) var(--gutter)" }}>
      <ErrorState title="Something went wrong while showing this page" error={new Error(message)} />
      <p style={{ marginTop: "var(--space-4)" }}>
        <ButtonLink to="/dashboard">Back to the overview</ButtonLink>
      </p>
    </div>
  );
}
