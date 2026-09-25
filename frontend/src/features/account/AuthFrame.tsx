import type { ReactNode } from "react";
import { Link } from "react-router";
import { Wordmark } from "@/components/Wordmark";
import styles from "@/pages/AuthPage.module.css";

/** The frame of the pages outside the workspace: signing in and choosing a password. */
export function AuthFrame({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className={styles.page}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className={styles.top}>
        <Link to="/" className={styles.brand} aria-label="RUMIN home">
          <Wordmark />
        </Link>
        {aside}
      </header>
      <main id="main" className={styles.main}>
        {children}
      </main>
      <footer className={styles.footer}>
        <p>
          RUMIN is a workspace for financial intelligence and economic simulation. Accounts are
          created by an administrator; there is no public sign-up. Nothing here is investment
          advice.
        </p>
      </footer>
    </div>
  );
}
