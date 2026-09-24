import { useEffect } from "react";
import { Link } from "react-router";
import { APP_MODULES, CURRENT_PHASE, ROADMAP, STATUS_LABEL } from "@/app/modules";
import { useTheme } from "@/app/theme";
import { ButtonLink } from "@/components/Button";
import {
  EPISTEMIC,
  EPISTEMIC_ORDER,
  type EpistemicCategory,
  EpistemicGlyph,
} from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { Wordmark } from "@/components/Wordmark";
import { NetworkConstellation } from "@/features/network/NetworkConstellation";
import { useNetworkGraph } from "@/features/network/useNetworkGraph";
import styles from "./LandingPage.module.css";

/** What each kind of knowledge amounts to in this build — stated plainly. */
const IN_THIS_BUILD: Record<EpistemicCategory, string> = {
  observation:
    "World Bank indicators and licensed price files, retrieved from the command line — historical, never live.",
  assumption: "Every relationship in the sample network, each with a written rationale.",
  scenario_input: "Versioned scenarios, built and executed in the Scenario Lab.",
  simulated_output:
    "Deterministic runs of five registered models, stored with every calculation step and read by Financial Intelligence as contributions — never as forecasts.",
  uncertainty:
    "Stated in words, with one-at-a-time sensitivity ranges and an evidence grade on every finding. No probabilities are estimated.",
};

export function LandingPage() {
  const network = useNetworkGraph();
  const { resolvedTheme, setTheme } = useTheme();
  const stats = network.graph?.model;

  useEffect(() => {
    document.title = "RUMIN — Financial intelligence & simulation";
  }, []);

  return (
    <div className={styles.landing}>
      <header className={styles.top}>
        <Wordmark size="lg" />
        <div className={styles.topActions}>
          <button
            type="button"
            className={styles.themeButton}
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            aria-label={`Switch to ${resolvedTheme === "dark" ? "light" : "dark"} theme`}
          >
            <Icon name={resolvedTheme === "dark" ? "sun" : "moon"} />
          </button>
          <ButtonLink to="/dashboard" size="sm">
            Open workspace
          </ButtonLink>
        </div>
      </header>

      <main>
        <section className={styles.hero} aria-labelledby="landing-title">
          <div className={styles.heroText}>
            <p className="eyebrow">Financial intelligence &amp; economic simulation</p>
            <h1 id="landing-title" className={styles.title}>
              An interactive financial intelligence platform.
            </h1>
            <p className={styles.lede}>
              RUMIN maps how companies, industries and economic variables connect, lets you build
              scenarios on that network, turns what it holds into findings with the evidence each
              rests on, and always shows what is observed, what is assumed, what you changed and
              what was simulated.
            </p>
            <div className={styles.ctas}>
              <ButtonLink to="/dashboard" variant="primary" iconAfter={<Icon name="arrowRight" />}>
                Enter RUMIN
              </ButtonLink>
              <a className={styles.secondaryLink} href="#principles">
                How RUMIN separates evidence from assumption
                <Icon name="arrowDown" size={14} />
              </a>
            </div>
          </div>

          <figure className={styles.figure}>
            <div className={styles.figureCanvas}>
              {network.graph && (
                <NetworkConstellation model={network.graph.model} layout={network.graph.layout} />
              )}
            </div>
            <figcaption className={styles.caption}>
              {stats ? (
                <>
                  The illustrative sample network: {stats.nodes.length} entities and{" "}
                  {stats.edges.length} links. Companies are fictional; industries, countries and
                  variables are real concepts. <Link to="/universe">Explore it</Link>
                </>
              ) : network.status === "error" ? (
                <>The sample network appears here once the RUMIN API is running.</>
              ) : (
                <>Loading the sample network…</>
              )}
            </figcaption>
          </figure>
        </section>

        <section id="principles" className={styles.section} aria-labelledby="principles-title">
          <div className={styles.sectionIntro}>
            <p className="eyebrow">Epistemic discipline</p>
            <h2 id="principles-title" className={styles.sectionTitle}>
              Five kinds of knowledge, never blurred
            </h2>
            <p>
              A scenario result is not a forecast, and an assumption is not a fact. Every value
              RUMIN shows carries one of these labels.
            </p>
          </div>
          <ol className={styles.categories}>
            {EPISTEMIC_ORDER.map((category) => (
              <li key={category} className={styles.category} data-category={category}>
                <div className={styles.categoryHead}>
                  <EpistemicGlyph category={category} size={16} />
                  <span className={styles.letter}>{EPISTEMIC[category].letter}</span>
                </div>
                <h3>{EPISTEMIC[category].label}</h3>
                <p>{EPISTEMIC[category].description}</p>
                <p className={styles.inBuild}>
                  <span className="eyebrow">In this build</span>
                  {IN_THIS_BUILD[category]}
                </p>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.section} aria-labelledby="modules-title">
          <div className={styles.sectionIntro}>
            <p className="eyebrow">
              Phase {CURRENT_PHASE} ·{" "}
              {ROADMAP.find((phase) => phase.phase === CURRENT_PHASE)?.title ?? "In progress"}
            </p>
            <h2 id="modules-title" className={styles.sectionTitle}>
              What exists today
            </h2>
          </div>
          <ul className={styles.modules}>
            {APP_MODULES.filter((module) => module.id !== "system").map((module) => (
              <li key={module.id}>
                <Link to={module.path} className={styles.module}>
                  <span className={styles.moduleStatus} data-status={module.status}>
                    {STATUS_LABEL[module.status]}
                  </span>
                  <span className={styles.moduleTitle}>{module.title}</span>
                  <span className={styles.moduleSummary}>{module.summary}</span>
                  <span className={styles.moduleNote}>{module.statusNote}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section} aria-labelledby="roadmap-title">
          <div className={styles.sectionIntro}>
            <p className="eyebrow">Roadmap</p>
            <h2 id="roadmap-title" className={styles.sectionTitle}>
              Ten phases, built in order
            </h2>
          </div>
          <ol className={styles.roadmap}>
            {ROADMAP.map((phase) => (
              <li
                key={phase.phase}
                className={styles.phase}
                aria-current={phase.phase === CURRENT_PHASE ? "step" : undefined}
              >
                <span className={styles.phaseNumber}>{String(phase.phase).padStart(2, "0")}</span>
                <span>{phase.title}</span>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className={styles.footer}>
        <p>
          RUMIN is a research and learning tool. The sample network is illustrative, provider data
          is historical, no live market data is connected, and nothing here is investment advice.
        </p>
      </footer>
    </div>
  );
}
