/**
 * What has been checked about a model version, and what has not: the verification register
 * run now through the engine. Passing checks are stated as exactly that — the arithmetic and
 * the stated properties hold on hypothetical figures — never as "validated". The list of
 * what is not verified is always shown with them.
 */
import { useState } from "react";
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { ErrorState, LoadingState } from "@/components/States";
import styles from "@/features/scenarioLab/Analyses.module.css";
import lab from "@/features/scenarioLab/ScenarioLab.module.css";
import { useApiResource } from "@/hooks/useApiResource";
import { simulationApi } from "@/services/api";
import type { ModelVerification } from "@/types/api";

const KIND: Record<string, string> = {
  reference: "hand calculation",
  property: "property",
  range: "limits",
  reproducibility: "reproducibility",
};

function useVerification(modelId: string, version: string | null) {
  return useApiResource(`simulation:verification:${modelId}:${version ?? "latest"}`, () =>
    simulationApi.verification(modelId, version),
  );
}

function summaryTone(register: ModelVerification) {
  return register.failed === 0 ? ("good" as const) : ("critical" as const);
}

function summaryText(register: ModelVerification) {
  return register.failed === 0
    ? `${register.passed} of ${register.total} checks passed`
    : `${register.failed} of ${register.total} checks failed`;
}

export function VerificationDetails({ register }: { register: ModelVerification }) {
  return (
    <div className={styles.verification}>
      <p className={lab.caption}>{register.note}</p>
      <ul className={styles.checks}>
        {register.checks.map((check) => (
          <li key={check.id} className={styles.check} data-passed={check.passed ? "true" : "false"}>
            <Icon name={check.passed ? "check" : "alert"} size={14} />
            <div>
              <p>
                <span className={styles.checkTitle}>{check.title}</span>
                <span className={styles.checkKind}>{KIND[check.kind] ?? check.kind}</span>
                <span className="visually-hidden">{check.passed ? " — passed" : " — failed"}</span>
              </p>
              <p className={styles.checkDetail}>{check.detail}</p>
              {!check.passed && Object.keys(check.expected).length > 0 && (
                <p className={styles.checkDetail}>
                  Expected{" "}
                  {Object.entries(check.expected)
                    .map(([name, value]) => `${name} ${value}`)
                    .join(", ")}
                  ; got{" "}
                  {Object.entries(check.actual)
                    .map(([name, value]) => `${name} ${value}`)
                    .join(", ")}
                  .
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
      <section className={styles.section}>
        <h4 className={lab.sectionTitle}>Not verified</h4>
        <ul className={styles.notes}>
          {register.not_verified.map((item) => (
            <li key={item.id}>{item.text}</li>
          ))}
        </ul>
      </section>
      <p className={lab.caption}>
        Version {register.version} · definition {register.definition_hash.slice(0, 12)} · engine{" "}
        {register.engine_version} · worked example: {register.reference_source} · ran in{" "}
        {register.duration_ms} ms
      </p>
    </div>
  );
}

/** The full register, for a model's page. */
export function VerificationPanel({
  modelId,
  version,
}: {
  modelId: string;
  version: string | null;
}) {
  const register = useVerification(modelId, version);
  return (
    <section aria-labelledby="verification-title" className={styles.section}>
      <div className={lab.modelRowHeader}>
        <h3 id="verification-title" className={lab.sectionTitle}>
          Verification
        </h3>
        {register.status === "success" && (
          <Badge tone={summaryTone(register.data)}>{summaryText(register.data)}</Badge>
        )}
      </div>
      {register.status === "loading" && <LoadingState label="Running the checks" lines={2} />}
      {register.status === "error" && (
        <ErrorState error={register.error} onRetry={register.reload} />
      )}
      {register.status === "success" && <VerificationDetails register={register.data} />}
    </section>
  );
}

/** One line for a model in a list, with the details a click away. */
export function VerificationSummary({
  modelId,
  version,
}: {
  modelId: string;
  version: string | null;
}) {
  const register = useVerification(modelId, version);
  const [open, setOpen] = useState(false);
  if (register.status !== "success") {
    return register.status === "error" ? (
      <p className={styles.compactVerification}>Verification could not be run.</p>
    ) : null;
  }
  return (
    <div>
      <p className={styles.compactVerification}>
        <Badge tone={summaryTone(register.data)}>{summaryText(register.data)}</Badge>
        <span>Not verified: parameters are assumptions; no back-testing.</span>
        <button
          type="button"
          className={lab.disclosure}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide the checks" : "Show the checks"}
        </button>
      </p>
      {open && <VerificationDetails register={register.data} />}
    </div>
  );
}
