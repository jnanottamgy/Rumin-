/**
 * One turn as a research note: the question, then the answer with its evidence margin,
 * then how it was answered — the tool calls that actually ran, with their timings, the
 * grounding check it passed and what composed it. A question still being answered shows
 * only what the server has recorded so far.
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import type { AnalystToolCall, AnalystTurn } from "@/types/api";
import styles from "./Analyst.module.css";
import { type BlockContext, BlockView } from "./Blocks";
import { EvidenceMargin } from "./Evidence";
import { answerMarkdown } from "./exportMarkdown";
import { citedOrder, duration, evidenceById, STATUS, STATUS_TONE, TOOL_LABEL } from "./format";

const CALL_STATUS: Record<AnalystToolCall["status"], string> = {
  ok: "done",
  invalid: "refused: invalid arguments",
  refused: "refused",
  not_found: "nothing found",
  failed: "failed",
  timeout: "timed out",
  skipped: "skipped",
};

export function ToolCalls({ calls }: { calls: AnalystToolCall[] }) {
  if (!calls.length) return <p className={styles.muted}>No tool was needed.</p>;
  return (
    <ol className={styles.calls}>
      {calls.map((call) => (
        <li
          key={call.position}
          className={cx(styles.call, call.status !== "ok" && styles.callProblem)}
        >
          <span className={styles.callName}>
            <span className="mono">{call.tool}</span>
            <span className={styles.muted}> {TOOL_LABEL[call.tool] ?? ""}</span>
          </span>
          <span className={styles.callStatus}>{CALL_STATUS[call.status]}</span>
          <span className={cx(styles.callTime, "tabular")}>{duration(call.duration_ms)}</span>
          {(call.summary || call.error) && (
            <span className={styles.callSummary}>
              {call.summary ?? call.error}
              {call.evidence.length > 0 && <span className="mono"> {call.evidence.join(" ")}</span>}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

function Method({ turn }: { turn: AnalystTurn }) {
  const answer = turn.answer;
  const grounding = answer?.grounding;
  const composed =
    answer?.provider === "anthropic"
      ? `A language model${turn.model ? ` (${turn.model})` : ""}, checked against the evidence`
      : "RUMIN's grounded composer (no language model)";
  return (
    <details className={styles.method}>
      <summary>
        How this was answered: {turn.tool_calls.length} tool{" "}
        {turn.tool_calls.length === 1 ? "call" : "calls"}, {duration(turn.duration_ms)}
      </summary>
      <ToolCalls calls={turn.tool_calls} />
      <dl className={styles.methodFacts}>
        <div>
          <dt>Composed by</dt>
          <dd>{composed}</dd>
        </div>
        {grounding && (
          <div>
            <dt>Grounding check</dt>
            <dd>
              {grounding.passed ? "Passed" : "Not passed"}: {grounding.figures_checked} figures and{" "}
              {grounding.citations_checked} citations checked against the evidence
            </dd>
          </div>
        )}
        {turn.fallback && (
          <div>
            <dt>Fallback</dt>
            <dd>{turn.fallback}</dd>
          </div>
        )}
        {turn.usage.requests > 0 && (
          <div>
            <dt>Language model</dt>
            <dd className="tabular">
              {turn.usage.requests} requests, {turn.usage.input_tokens} input and{" "}
              {turn.usage.output_tokens} output tokens
            </dd>
          </div>
        )}
        <div>
          <dt>Read as</dt>
          <dd className="mono">{turn.intent ?? "—"}</dd>
        </div>
      </dl>
    </details>
  );
}

function CopyButton({ turn }: { turn: AnalystTurn }) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(answerMarkdown(turn));
          setCopied("copied");
        } catch {
          setCopied("failed");
        }
      }}
    >
      {copied === "copied" ? "Copied" : copied === "failed" ? "Copy failed" : "Copy answer"}
    </Button>
  );
}

export function Note({
  turn,
  onAsk,
  disabled,
}: {
  turn: AnalystTurn;
  onAsk: (question: string) => void;
  disabled: boolean;
}) {
  const [active, setActive] = useState<string | null>(null);
  const answer = turn.answer;
  const prefix = `t${turn.position}-`;
  const evidence = useMemo(() => (answer ? evidenceById(answer) : new Map()), [answer]);
  const order = useMemo(() => (answer ? citedOrder(answer) : []), [answer]);
  const context: BlockContext = {
    evidence,
    highlight: { active, setActive },
    prefix,
    onAsk,
    disabled,
    headline: answer?.headline,
  };
  const cited = order.flatMap((id) => {
    const item = evidence.get(id);
    return item ? [item] : [];
  });
  const others = answer ? answer.evidence.filter((item) => !order.includes(item.id)) : [];
  const followUps = [...new Set(answer?.follow_ups ?? [])];
  return (
    <article className={styles.note} aria-labelledby={`${prefix}q`}>
      <p className={styles.question} id={`${prefix}q`}>
        {turn.question}
      </p>
      {turn.status === "failed" || !answer ? (
        <div className={styles.failed} role="alert">
          <Icon name="alert" size={16} />
          <p>{turn.error?.message ?? "This question could not be answered."}</p>
          <Button size="sm" disabled={disabled} onClick={() => onAsk(turn.question)}>
            Ask again
          </Button>
        </div>
      ) : (
        <div className={styles.body}>
          <div className={styles.main}>
            <h3 className={styles.headline}>{answer.headline}</h3>
            <p className={cx(styles.status, styles[`tone_${STATUS_TONE[answer.status]}`])}>
              {STATUS[answer.status]}
              {answer.provider === "anthropic" ? ", written by a language model and checked" : ""}
            </p>
            {answer.blocks.map((block, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: blocks are fixed once answered
              <BlockView key={index} block={block} context={context} />
            ))}
            {followUps.length > 0 && (
              <div className={styles.followUps}>
                <p className={styles.muted}>Ask next</p>
                <div className={styles.options}>
                  {followUps.map((question) => (
                    <Button
                      key={question}
                      size="sm"
                      variant="secondary"
                      disabled={disabled}
                      onClick={() => onAsk(question)}
                    >
                      {question}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            <div className={styles.noteFoot}>
              <Method turn={turn} />
              <CopyButton turn={turn} />
            </div>
          </div>
          <EvidenceMargin
            cited={cited}
            others={others}
            highlight={context.highlight}
            prefix={prefix}
          />
        </div>
      )}
    </article>
  );
}

export function PendingNote({
  question,
  turn,
  error,
  stalled,
  onRetry,
  onDismiss,
}: {
  question: string;
  turn: AnalystTurn | null;
  error: unknown;
  stalled: boolean;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  const where = turn?.status === "running" ? "Reading RUMIN's records" : "Waiting for a worker";
  return (
    <article className={cx(styles.note, styles.pending)} aria-busy={!error}>
      <p className={styles.question}>{question}</p>
      {error ? (
        <div className={styles.failed} role="alert">
          <Icon name="alert" size={16} />
          <p>{describeError(error)}</p>
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      ) : (
        <div className={styles.progress} role="status" aria-live="polite">
          <p className={styles.status}>
            {stalled
              ? "Still being answered. Open the conversation again later to see the answer."
              : turn
                ? `${where}…`
                : "Sending the question…"}
          </p>
          {turn && turn.tool_calls.length > 0 && <ToolCalls calls={turn.tool_calls} />}
        </div>
      )}
    </article>
  );
}
