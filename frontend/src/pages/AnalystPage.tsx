/**
 * The AI Analyst workspace: conversations on the left, the conversation as a column of
 * research notes — each answer with its evidence margin — and the question box.
 *
 * Answers come from RUMIN's records through the Analyst's tools; every figure cites its
 * source, and an answer whose figures are not in its evidence is never shown. Which
 * provider answers (RUMIN's grounded composer, or a configured language model) is stated
 * in the header, from the API.
 */
import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatusIndicator } from "@/components/StatusIndicator";
import styles from "@/features/analyst/Analyst.module.css";
import { download, sessionMarkdown } from "@/features/analyst/exportMarkdown";
import { Note, PendingNote } from "@/features/analyst/Note";
import { isFinal, useConversation } from "@/features/analyst/useConversation";
import { useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatDate } from "@/lib/format";
import { analystApi } from "@/services/api";
import type { AnalystCapabilities, AnalystSessionSummary } from "@/types/api";

function ProviderStatus({ capabilities }: { capabilities: AnalystCapabilities | undefined }) {
  if (!capabilities) return null;
  const provider = capabilities.provider;
  const [label, note] =
    provider.active === "anthropic"
      ? [
          "Language model configured",
          "A Claude model answers through RUMIN's tools; any answer that fails the grounding check is replaced by RUMIN's own.",
        ]
      : [
          "Grounded answers",
          provider.configured === "anthropic"
            ? `RUMIN composes every answer itself: the configured language model is not ready (${(provider.reason ?? "not configured").replace(/\.$/, "")}).`
            : "RUMIN composes every answer itself from its tools; no language model is configured.",
        ];
  return (
    <span className={styles.provider}>
      <StatusIndicator tone="good" label={label} />
      <span className={styles.providerNote}>{note}</span>
    </span>
  );
}

function Rail({
  sessions,
  activeId,
  onOpen,
  onNew,
}: {
  sessions: AnalystSessionSummary[];
  activeId: string | null;
  onOpen: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <nav className={styles.rail} aria-label="Conversations">
      <Button variant="secondary" size="sm" icon={<Icon name="plus" size={14} />} onClick={onNew}>
        New conversation
      </Button>
      {sessions.length === 0 ? (
        <p className={styles.muted}>Conversations you start are kept here until you delete them.</p>
      ) : (
        <ol className={styles.sessions}>
          {sessions.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={cx(styles.sessionItem, item.id === activeId && styles.sessionActive)}
                aria-current={item.id === activeId ? "true" : undefined}
                onClick={() => onOpen(item.id)}
              >
                <span className={styles.sessionTitle}>{item.title}</span>
                <span className={styles.sessionMeta}>
                  {item.turn_count} {item.turn_count === 1 ? "question" : "questions"},{" "}
                  {formatDate(item.updated_at)}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </nav>
  );
}

/**
 * A question handed over in the router's state (by the 3D universe, say): it is put in the
 * question box for the reader to edit or send, and never sent by itself.
 */
export function handedQuestion(state: unknown): string {
  const question = (state as { draftQuestion?: unknown } | null)?.draftQuestion;
  return typeof question === "string" ? question.trim() : "";
}

function Composer({
  limit,
  busy,
  onAsk,
  inputRef,
  initial = "",
}: {
  limit: number;
  busy: boolean;
  onAsk: (question: string) => Promise<boolean>;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  initial?: string;
}) {
  const [text, setText] = useState(initial);
  const id = useId();
  const over = text.length > limit;
  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!text.trim() || over || busy) return;
    const question = text;
    setText("");
    const accepted = await onAsk(question);
    if (!accepted) setText(question);
  };
  return (
    <form className={styles.composer} onSubmit={submit}>
      <label htmlFor={id} className="visually-hidden">
        Your question
      </label>
      <textarea
        id={id}
        ref={inputRef}
        rows={2}
        value={text}
        placeholder="Ask about a company, a variable, a series or a scenario…"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void submit();
          }
        }}
        aria-describedby={`${id}-hint`}
        aria-invalid={over || undefined}
      />
      <div className={styles.composerFoot}>
        <p id={`${id}-hint`} className={cx(styles.muted, over && styles.over)}>
          {over
            ? `${text.length - limit} ${text.length - limit === 1 ? "character" : "characters"} over the limit of ${limit}.`
            : "Enter to ask, Shift+Enter for a new line. Answers cite RUMIN's records; no forecasts or investment advice."}
        </p>
        <Button type="submit" variant="primary" size="sm" disabled={busy || !text.trim() || over}>
          {busy ? "Answering…" : "Ask"}
        </Button>
      </div>
    </form>
  );
}

function Welcome({
  capabilities,
  onAsk,
  disabled,
}: {
  capabilities: AnalystCapabilities | undefined;
  onAsk: (question: string) => void;
  disabled: boolean;
}) {
  return (
    <section className={styles.welcome} aria-label="Start a conversation">
      <h2 className={styles.welcomeTitle}>Ask RUMIN about its records</h2>
      <p className={styles.welcomeText}>
        Answers are built from the knowledge graph, stored series, simulation models, stored
        scenarios and Financial Intelligence findings. Every figure carries the source it comes
        from, shown beside the answer. What-ifs are computed on request and never saved.
      </p>
      {capabilities && capabilities.suggestions.length > 0 && (
        <div className={styles.suggestions}>
          {capabilities.suggestions.map((item) => (
            <button
              key={item.question}
              type="button"
              className={styles.suggestion}
              disabled={disabled}
              onClick={() => onAsk(item.question)}
            >
              <span className={styles.suggestionLabel}>{item.label}</span>
              <span>{item.question}</span>
            </button>
          ))}
        </div>
      )}
      <p className={styles.muted}>
        The Analyst does not forecast, does not hold live market data and does not make investment
        decisions.
      </p>
    </section>
  );
}

function ConversationHead({
  title,
  onRename,
  onExport,
  onDelete,
}: {
  title: string;
  onRename: (title: string) => Promise<void>;
  onExport: () => void;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setDraft(title), [title]);
  return (
    <header className={styles.conversationHead}>
      {editing ? (
        <form
          className={styles.renameForm}
          onSubmit={async (event) => {
            event.preventDefault();
            try {
              await onRename(draft.trim());
              setEditing(false);
              setError(null);
            } catch (failure) {
              setError(describeError(failure));
            }
          }}
        >
          <label className="visually-hidden" htmlFor="conversation-title">
            Conversation title
          </label>
          <input
            id="conversation-title"
            value={draft}
            maxLength={120}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" size="sm" disabled={!draft.trim()}>
            Save title
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <h2 className={styles.conversationTitle}>{title}</h2>
      )}
      <div className={styles.conversationActions}>
        {!editing && (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            Rename
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onExport}>
          Export as Markdown
        </Button>
        {confirming ? (
          <fieldset className={styles.confirm}>
            <legend className="visually-hidden">Confirm deletion</legend>
            <span>Delete this conversation and everything in it?</span>
            <Button
              size="sm"
              variant="danger"
              onClick={async () => {
                try {
                  await onDelete();
                } catch (failure) {
                  setError(describeError(failure));
                  setConfirming(false);
                }
              }}
            >
              Delete
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </fieldset>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            icon={<Icon name="trash" size={14} />}
            onClick={() => setConfirming(true)}
          >
            Delete
          </Button>
        )}
      </div>
      {error && (
        <p className={styles.headError} role="alert">
          {error}
        </p>
      )}
    </header>
  );
}

export function AnalystPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get("session");
  const capabilities = useApiResource("analyst:capabilities", () => analystApi.capabilities());
  const sessions = useApiResource("analyst:sessions", () => analystApi.sessions());
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const location = useLocation();
  const handed = useMemo(() => handedQuestion(location.state), [location.state]);

  useEffect(() => {
    document.title = "AI Analyst — RUMIN";
  }, []);

  useEffect(() => {
    if (handed) inputRef.current?.focus();
  }, [handed]);

  const open = useCallback(
    (id: string | null) => {
      setSearchParams(id ? { session: id } : {}, { replace: false });
    },
    [setSearchParams],
  );
  const reloadSessions = sessions.reload;
  const conversation = useConversation(sessionId, {
    onCreated: (id) => setSearchParams({ session: id }, { replace: true }),
    onSettled: reloadSessions,
  });
  const { state, asking } = conversation;
  const turnCount = state.status === "ready" ? state.session.turns.length : 0;

  useEffect(() => {
    if (asking || turnCount) endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [asking, turnCount]);

  const busy = Boolean(asking && !asking.error && !asking.stalled);
  const ask = useCallback(
    async (question: string) => {
      if (busy) return false;
      void conversation.ask(question);
      return true;
    },
    [busy, conversation],
  );
  const limit = capabilities.data?.limits.max_question_chars ?? 2000;

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="AI Analyst"
        title="Questions answered from RUMIN's records"
        description="Ask about exposure, relationships, stored data, scenarios and findings. Each answer shows the records behind every figure and the tools that produced it."
        meta={<ProviderStatus capabilities={capabilities.data} />}
      />
      <div className={styles.workspace}>
        {sessions.status === "error" ? (
          <div className={styles.rail}>
            <ErrorState
              error={sessions.error}
              onRetry={sessions.reload}
              title="Conversations could not be loaded"
            />
          </div>
        ) : (
          <Rail
            sessions={sessions.data?.items ?? []}
            activeId={sessionId}
            onOpen={(id) => open(id)}
            onNew={() => {
              open(null);
              inputRef.current?.focus();
            }}
          />
        )}
        <section className={styles.conversation} aria-label="Conversation">
          {state.status === "loading" && (
            <LoadingState label="Loading the conversation…" lines={5} />
          )}
          {state.status === "error" && (
            <ErrorState
              error={state.error}
              onRetry={conversation.reload}
              title="This conversation could not be loaded"
            />
          )}
          {state.status === "ready" && (
            <ConversationHead
              title={state.session.title}
              onRename={async (title) => {
                await analystApi.rename(state.session.id, title);
                conversation.rename(title);
                sessions.reload();
              }}
              onExport={() =>
                download(
                  `rumin-analyst-${state.session.id.slice(0, 8)}.md`,
                  sessionMarkdown(state.session, window.location.origin),
                )
              }
              onDelete={async () => {
                await analystApi.remove(state.session.id);
                sessions.reload();
                open(null);
              }}
            />
          )}
          {(state.status === "empty" ||
            (state.status === "ready" && state.session.turns.length === 0)) &&
            !asking && (
              <Welcome
                capabilities={capabilities.data}
                onAsk={(q) => void ask(q)}
                disabled={busy}
              />
            )}
          {state.status === "ready" &&
            state.session.turns.map((turn) =>
              isFinal(turn) ? (
                <Note key={turn.id} turn={turn} onAsk={(q) => void ask(q)} disabled={busy} />
              ) : turn.id === asking?.turn?.id ? null : (
                <PendingNote
                  key={turn.id}
                  question={turn.question}
                  turn={turn}
                  error={null}
                  stalled
                  onRetry={conversation.reload}
                  onDismiss={conversation.dismiss}
                />
              ),
            )}
          {asking && (
            <PendingNote
              question={asking.question}
              turn={asking.turn}
              error={asking.error}
              stalled={asking.stalled}
              onRetry={conversation.retry}
              onDismiss={conversation.dismiss}
            />
          )}
          {capabilities.status === "error" && (
            <EmptyState title="The Analyst's settings could not be loaded">
              <p>{describeError(capabilities.error)}</p>
            </EmptyState>
          )}
          <div ref={endRef} />
          <Composer
            key={handed}
            limit={limit}
            busy={busy}
            onAsk={ask}
            inputRef={inputRef}
            initial={handed}
          />
        </section>
      </div>
    </div>
  );
}
