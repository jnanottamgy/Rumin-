/**
 * Form fields for accounts and passwords: a visible label, the errors under the field (tied
 * to it with `aria-describedby`), and hints read out with it.
 */
import type { InputHTMLAttributes, ReactNode, Ref } from "react";
import { ApiError, describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import styles from "@/pages/AuthPage.module.css";

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "onChange" | "value">;

export function Field({
  id,
  label,
  value,
  onChange,
  errors = [],
  hint,
  inputRef,
  className,
  ...input
}: InputProps & {
  id: string;
  label: ReactNode;
  value: string;
  onChange: (value: string) => void;
  errors?: readonly string[];
  hint?: ReactNode;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const errorId = `${id}-errors`;
  const hintId = `${id}-hint`;
  const describedBy =
    [errors.length > 0 ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div className={cx(styles.field, className)}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <input
        {...input}
        ref={inputRef}
        id={id}
        className={styles.input}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={errors.length > 0 ? true : undefined}
        aria-describedby={describedBy}
      />
      {errors.length > 0 && (
        <ul id={errorId} className={styles.fieldErrors}>
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      {hint && (
        <div id={hintId} className={styles.hint}>
          {hint}
        </div>
      )}
    </div>
  );
}

/** The password policy, as the backend applies it (`app/auth/passwords.py`). */
export const PASSWORD_RULES = [
  "At least 12 characters (a phrase of a few words works well).",
  "Not a common password, and not your e-mail address or name.",
  "No spaces at the start or the end.",
] as const;

export function PasswordRules({ id }: { id?: string }) {
  return (
    <ul id={id} className={styles.hintList}>
      {PASSWORD_RULES.map((rule) => (
        <li key={rule}>{rule}</li>
      ))}
    </ul>
  );
}

export interface FormProblems {
  /** Messages for named fields. */
  fields: Record<string, string[]>;
  /** A message for the whole form, when the problem is not one field's. */
  form: string | null;
}

const NO_PROBLEMS: FormProblems = { fields: {}, form: null };
export const noProblems = (): FormProblems => ({ ...NO_PROBLEMS, fields: {} });

function friendly(field: string, message: string, type: string | null | undefined): string {
  if (field === "email" && type === "string_pattern_mismatch") {
    return "Enter an e-mail address like name@example.com.";
  }
  return message;
}

/**
 * Sort an API failure into field messages and a form message. Validation details for the
 * named `fields` go under them; anything else is said once for the form.
 */
export function problemsFrom(error: unknown, fields: readonly string[]): FormProblems {
  const problems = noProblems();
  if (error instanceof ApiError && error.status === 422 && error.details.length > 0) {
    for (const detail of error.details) {
      const field = detail.field ?? "";
      if (fields.includes(field)) {
        const list = problems.fields[field] ?? [];
        list.push(friendly(field, detail.message, detail.type));
        problems.fields[field] = list;
      } else {
        problems.form = problems.form ?? detail.message;
      }
    }
    if (!problems.form && Object.keys(problems.fields).length === 0) problems.form = error.message;
    return problems;
  }
  problems.form = describeError(error);
  return problems;
}
