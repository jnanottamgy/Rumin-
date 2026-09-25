import { useEffect, useId, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { APP_MODULES, CURRENT_PHASE, STATUS_LABEL } from "@/app/modules";
import { type ThemePreference, useTheme } from "@/app/theme";
import { Icon, type IconName } from "@/components/Icon";
import { StatusIndicator } from "@/components/StatusIndicator";
import { Wordmark } from "@/components/Wordmark";
import { useApiResource } from "@/hooks/useApiResource";
import { cx } from "@/lib/cx";
import { api } from "@/services/api";
import { AccountMenu, AccountSection } from "./AccountMenu";
import styles from "./AppShell.module.css";

const THEME_ORDER: ThemePreference[] = ["system", "light", "dark"];
const THEME_ICON: Record<ThemePreference, IconName> = {
  system: "monitor",
  light: "sun",
  dark: "moon",
};

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length] ?? "system";
  return (
    <button
      type="button"
      className={styles.iconButton}
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${theme}. Switch to ${next}.`}
      title={`Theme: ${theme}`}
    >
      <Icon name={THEME_ICON[theme]} />
    </button>
  );
}

/** Live workspace state: which data is loaded, straight from the API. */
function WorkspaceStatus() {
  const system = useApiResource("system", () => api.system());
  if (system.status === "loading") {
    return <StatusIndicator tone="neutral" label="Local workspace" detail="Connecting…" />;
  }
  if (system.status === "error") {
    return <StatusIndicator tone="critical" label="Local workspace" detail="API unreachable" />;
  }
  const dataset = system.data.dataset.summary;
  return dataset ? (
    <StatusIndicator
      tone="good"
      label="Local workspace"
      detail={`${dataset.is_illustrative ? "Illustrative sample" : dataset.name} v${dataset.version}`}
    />
  ) : (
    <StatusIndicator tone="warning" label="Local workspace" detail="No dataset loaded" />
  );
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const menuId = useId();

  // Close the mobile menu after navigating.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs on route change only
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const nav = (
    <ul className={styles.navList}>
      {APP_MODULES.map((module) => (
        <li key={module.id}>
          <NavLink
            to={module.path}
            className={({ isActive }) => cx(styles.navLink, isActive && styles.active)}
          >
            {module.navLabel}
            {module.status !== "available" && (
              <span className={styles.navStatus} data-status={module.status}>
                {STATUS_LABEL[module.status]}
              </span>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link to="/" className={styles.brand} aria-label="RUMIN home">
            <Wordmark />
          </Link>
          <nav className={styles.nav} aria-label="Primary">
            {nav}
          </nav>
          <div className={styles.meta}>
            <WorkspaceStatus />
            <ThemeToggle />
            <AccountMenu />
          </div>
          <button
            type="button"
            className={cx(styles.iconButton, styles.menuButton)}
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <Icon name={menuOpen ? "close" : "menu"} />
            <span className="visually-hidden">{menuOpen ? "Close menu" : "Open menu"}</span>
          </button>
        </div>
        <div id={menuId} className={styles.mobileMenu} hidden={!menuOpen}>
          <nav aria-label="Primary (mobile)">{nav}</nav>
          <div className={styles.mobileMeta}>
            <WorkspaceStatus />
            <ThemeToggle />
          </div>
          <AccountSection />
        </div>
      </header>
      <main id="main" className={styles.main}>
        <Outlet />
      </main>
      <footer className={styles.footer}>
        <p>
          RUMIN · Phase {CURRENT_PHASE}. The network's sample data is illustrative (its companies
          are fictional). Provider data is historical and never live. Graph relationships are
          recorded or assumed, not measured. Nothing here is investment advice.
        </p>
      </footer>
    </div>
  );
}
