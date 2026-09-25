import { useEffect } from "react";
import { Link } from "react-router";
import { type MotionPreference, type ThemePreference, useTheme } from "@/app/theme";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ScrollRegion } from "@/components/ScrollRegion";
import { ErrorState, LoadingState } from "@/components/States";
import { StatusIndicator } from "@/components/StatusIndicator";
import { KIND_ENCODING } from "@/features/network/encoding";
import { KIND_ORDER } from "@/features/network/model";
import { useApiResource } from "@/hooks/useApiResource";
import { apiBaseUrl } from "@/lib/apiClient";
import { formatCount, formatDateTime } from "@/lib/format";
import { api } from "@/services/api";
import styles from "./SystemPage.module.css";

function Segmented<T extends string>({
  legend,
  value,
  options,
  onChange,
}: {
  legend: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className={styles.setting}>
      <legend>{legend}</legend>
      <div className={styles.segmented}>
        {options.map((option) => (
          <label key={option.value}>
            <input
              type="radio"
              name={legend}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Settings() {
  const { theme, setTheme, motion, setMotion, resolvedTheme, reducedMotion } = useTheme();
  return (
    <div className={styles.settings}>
      <Segmented<ThemePreference>
        legend="Theme"
        value={theme}
        onChange={setTheme}
        options={[
          { value: "system", label: "Match system" },
          { value: "light", label: "Bone (light)" },
          { value: "dark", label: "Charcoal (dark)" },
        ]}
      />
      <Segmented<MotionPreference>
        legend="Motion"
        value={motion}
        onChange={setMotion}
        options={[
          { value: "system", label: "Match system" },
          { value: "reduce", label: "Reduced" },
          { value: "full", label: "Full" },
        ]}
      />
      <p className={styles.hint}>
        Currently {resolvedTheme} theme, {reducedMotion ? "reduced" : "full"} motion. Stored in this
        browser only.
      </p>
      <div>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setTheme("system");
            setMotion("system");
          }}
        >
          Reset to system defaults
        </Button>
      </div>
    </div>
  );
}

export function SystemPage() {
  const system = useApiResource("system", () => api.system());
  const readiness = useApiResource("readiness", () => api.readiness());
  const docsUrl = `${apiBaseUrl()}/docs`;

  useEffect(() => {
    document.title = "System — RUMIN";
  }, []);

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="System"
        title="System & settings"
        description="What is running, what is loaded, and what this build can and cannot do — reported by the API, not assumed by the interface."
        actions={
          <Button
            size="sm"
            onClick={() => {
              system.reload();
              readiness.reload();
            }}
          >
            Refresh
          </Button>
        }
      />

      <div className={styles.grid}>
        <Panel title="Runtime" eyebrow="Status">
          {system.status === "loading" && <LoadingState lines={4} />}
          {system.status === "error" && <ErrorState error={system.error} onRetry={system.reload} />}
          {system.status === "success" && (
            <dl className={styles.facts}>
              <dt>API</dt>
              <dd>
                <StatusIndicator
                  tone="good"
                  label="Responding"
                  detail={`${system.data.service} ${system.data.version} · ${system.data.api_version}`}
                />
              </dd>
              <dt>Readiness</dt>
              <dd>
                {readiness.status === "success" ? (
                  <StatusIndicator
                    tone={readiness.data.status === "ready" ? "good" : "warning"}
                    label={readiness.data.status === "ready" ? "Ready" : "Not ready"}
                    detail={`database ${readiness.data.checks.database} · migrations ${readiness.data.checks.migrations} · dataset ${readiness.data.checks.dataset}`}
                  />
                ) : (
                  <span className={styles.muted}>Checking…</span>
                )}
              </dd>
              <dt>Environment</dt>
              <dd>{system.data.environment}</dd>
              <dt>Database</dt>
              <dd>
                {system.data.database.backend} ·{" "}
                {system.data.database.reachable ? "reachable" : "unreachable"}
              </dd>
              <dt>Migrations</dt>
              <dd>
                <span className="mono">{system.data.database.migration_revision ?? "none"}</span> of{" "}
                <span className="mono">{system.data.database.migration_head ?? "?"}</span>{" "}
                {system.data.database.schema_up_to_date ? (
                  <Badge tone="good">current</Badge>
                ) : (
                  <Badge tone="warning">not current</Badge>
                )}
              </dd>
              <dt>Server time</dt>
              <dd className="tabular">{formatDateTime(system.data.server_time)}</dd>
            </dl>
          )}
        </Panel>

        <Panel
          title="Reference dataset"
          eyebrow="Provenance"
          description={
            <>
              The curated network. Provider data (series and prices) is in the{" "}
              <Link to="/data">Data Explorer</Link>.
            </>
          }
        >
          {system.status === "success" &&
            (system.data.dataset.summary ? (
              <div className={styles.dataset}>
                <p className={styles.datasetName}>
                  {system.data.dataset.summary.name}{" "}
                  <span className="mono">v{system.data.dataset.summary.version}</span>
                </p>
                <div className={styles.badges}>
                  {system.data.dataset.summary.is_illustrative && (
                    <Badge tone="outline">Illustrative</Badge>
                  )}
                  <Badge tone="neutral">
                    Loaded {formatDateTime(system.data.dataset.summary.loaded_at)}
                  </Badge>
                </div>
                <p className={styles.provenance}>{system.data.dataset.summary.provenance_note}</p>
                <dl className={styles.facts}>
                  {KIND_ORDER.map((kind) => (
                    <div key={kind} className={styles.factRow}>
                      <dt>{KIND_ENCODING[kind].plural}</dt>
                      <dd className="tabular">
                        {formatCount(system.data.dataset.entity_counts[kind] ?? 0)}
                      </dd>
                    </div>
                  ))}
                  <div className={styles.factRow}>
                    <dt>Relationships</dt>
                    <dd className="tabular">
                      {formatCount(system.data.dataset.relationship_count)}
                    </dd>
                  </div>
                  <div className={styles.factRow}>
                    <dt>Checksum</dt>
                    <dd className="mono">
                      {system.data.dataset.summary.checksum_sha256.slice(0, 16)}…
                    </dd>
                  </div>
                  <div className={styles.factRow}>
                    <dt>Licence</dt>
                    <dd>{system.data.dataset.summary.license}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <p className={styles.muted}>
                No dataset is loaded. Run <span className="mono">python -m app.db.seed</span> in{" "}
                <span className="mono">backend/</span>.
              </p>
            ))}
          {system.status !== "success" && <p className={styles.muted}>Waiting for the API…</p>}
        </Panel>
      </div>

      <Panel
        title="Capabilities"
        eyebrow="What this build can do"
        description="Reported by the backend. The interface never offers a capability the API does not have."
      >
        {system.status === "success" ? (
          <ScrollRegion className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Capability</th>
                  <th scope="col">Status</th>
                  <th scope="col">Phase</th>
                  <th scope="col">Note</th>
                </tr>
              </thead>
              <tbody>
                {system.data.capabilities.map((capability) => (
                  <tr key={capability.id}>
                    <th scope="row">{capability.label}</th>
                    <td>
                      <StatusIndicator
                        tone={capability.available ? "good" : "planned"}
                        label={capability.available ? "Available" : "Not available"}
                      />
                    </td>
                    <td className="tabular">{capability.planned_phase ?? "—"}</td>
                    <td className={styles.muted}>{capability.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
        ) : (
          <LoadingState lines={4} />
        )}
      </Panel>

      <div className={styles.grid}>
        <Panel title="Display" eyebrow="Settings">
          <Settings />
        </Panel>
        <Panel title="About this build" eyebrow="Frontend">
          <dl className={styles.facts}>
            <dt>Version</dt>
            <dd className="mono">{__RUMIN_VERSION__}</dd>
            <dt>Mode</dt>
            <dd>{import.meta.env.MODE}</dd>
            <dt>API base URL</dt>
            <dd className="mono">{apiBaseUrl() || "same origin (proxied)"}</dd>
            <dt>API reference</dt>
            <dd>
              <a href={docsUrl} target="_blank" rel="noopener noreferrer">
                OpenAPI documentation
              </a>
            </dd>
            <dt>Authentication</dt>
            <dd className={styles.muted}>Not implemented — run locally only (Phase 10)</dd>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
