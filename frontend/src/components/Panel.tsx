import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import styles from "./Panel.module.css";

/** A titled section. Uses <section> + heading so panels appear in the document outline. */
export function Panel({
  title,
  eyebrow,
  description,
  actions,
  children,
  className,
  bodyClassName,
  headingLevel = 2,
  flush = false,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  headingLevel?: 2 | 3;
  flush?: boolean;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section className={cx(styles.panel, className)}>
      <header className={styles.header}>
        <div className={styles.titles}>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <Heading className={styles.title}>{title}</Heading>
          {description && <p className={styles.description}>{description}</p>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </header>
      <div className={cx(styles.body, flush && styles.flush, bodyClassName)}>{children}</div>
    </section>
  );
}
