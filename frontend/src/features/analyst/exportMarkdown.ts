/**
 * Conversations and answers as Markdown, for copying or saving: the question, the answer
 * with its citations kept, its tables, and the list of sources each answer cites (with
 * where to find them). Built in the browser from what the API returned; nothing is sent.
 */
import type { AnalystSession, AnalystTurn } from "@/types/api";
import { citedOrder, evidenceById, KNOWLEDGE, moneyText, percentText } from "./format";

function cell(text: string | null | undefined): string {
  return (text ?? "—").replaceAll("|", "\\|").replaceAll("\n", " ");
}

export function answerMarkdown(turn: AnalystTurn, origin = ""): string {
  const answer = turn.answer;
  const lines: string[] = [`### ${turn.question}`, ""];
  if (!answer) {
    lines.push(`_${turn.error?.message ?? "Not answered."}_`, "");
    return lines.join("\n");
  }
  lines.push(`**${answer.headline}**`, "");
  for (const block of answer.blocks) {
    switch (block.type) {
      case "text": {
        const label =
          block.role === "interpretation"
            ? "_Interpretation:_ "
            : block.role === "general"
              ? "_General knowledge, not from RUMIN's records:_ "
              : "";
        lines.push(`${label}${block.text}`, "");
        break;
      }
      case "table": {
        lines.push(`${block.title}`, "");
        lines.push(`| ${block.columns.map((column) => cell(column.label)).join(" | ")} |`);
        lines.push(`| ${block.columns.map(() => "---").join(" | ")} |`);
        for (const row of block.rows) {
          lines.push(
            `| ${block.columns.map((column) => cell(row.cells[column.key])).join(" | ")} |`,
          );
        }
        lines.push("");
        break;
      }
      case "scenario": {
        lines.push(`${block.title} (${block.status})`, "");
        for (const line of block.lines ?? []) {
          lines.push(
            `- ${line.label}: ${moneyText(line.change, line.currency, true)} ` +
              `(${percentText(line.percent_change)}) against a baseline of ` +
              `${moneyText(line.baseline, line.currency)}`,
          );
        }
        for (const item of block.missing ?? []) lines.push(`- Missing: ${item}`);
        lines.push("");
        break;
      }
      case "notice":
        lines.push(`> **${block.title}.** ${block.text}`, "");
        break;
      case "series":
        lines.push(
          `${block.title} (${block.unit}): ${block.points.map((point) => `${point.period} ${point.value}`).join(", ")}`,
          "",
        );
        break;
      case "paths":
        lines.push(block.title, "");
        for (const path of block.paths) {
          lines.push(`- ${path.steps.map((step) => step.name).join(" → ")}`);
        }
        lines.push("");
        break;
      case "clarification":
        lines.push(block.question, "");
        break;
    }
  }
  const evidence = evidenceById(answer);
  const order = citedOrder(answer);
  if (order.length) {
    lines.push("Sources:", "");
    for (const id of order) {
      const item = evidence.get(id);
      if (!item) continue;
      const where = item.source.link ? ` (${origin}${item.source.link})` : "";
      const period = item.period ? `, ${item.period}` : "";
      lines.push(`- [${id}] ${KNOWLEDGE[item.kind].label}: ${item.title}${period}${where}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

export function sessionMarkdown(session: AnalystSession, origin = ""): string {
  const header = [
    `# ${session.title}`,
    "",
    "Answers from RUMIN's records. Every figure cites its source; simulated results hold only " +
      "under their scenario's changes and figures and are not forecasts.",
    "",
  ];
  return [...header, ...session.turns.map((turn) => answerMarkdown(turn, origin))].join("\n");
}

export function download(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
