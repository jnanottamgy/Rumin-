import { Icon } from "@/components/Icon";
import styles from "./ReadOnlyNote.module.css";

/**
 * Why a control is not offered (role or ownership, Phase 10). Give it an `id` and point the
 * disabled control's `aria-describedby` at it, so the reason is read out with the control.
 */
export function ReadOnlyNote({ reason, id }: { reason: string; id?: string }) {
  return (
    <p id={id} className={styles.note}>
      <Icon name="info" size={14} />
      <span>{reason}</span>
    </p>
  );
}
