import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { api } from "../lib/api"
import type { Intervention, Location, Plan, SiteCardResponse } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, numeric, shadeLabel, temperature } from "../lib/format"
import styles from "./tree-popup-card.module.css"

type TreePopupCardProps = { location: Location; plan: Plan }

export function TreePopupCard({ location, plan }: TreePopupCardProps) {
  const { budget_eur, include_inspection, strategy, priority_only } = plan
  const [brief, setBrief] = useState<SiteCardResponse | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const interventions = plan.selected.filter((item) => item.location_id === location.id)

  useEffect(() => {
    const controller = new AbortController()
    api.siteCard(location.id, { budget_eur, include_inspection, strategy, priority_only }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setBrief(result) })
      .catch(() => { if (!controller.signal.aborted) setUnavailable(true) })
    return () => controller.abort()
  }, [location.id, budget_eur, include_inspection, strategy, priority_only])

  return (
    <section className={styles.card} aria-label={`Παρέμβαση στο σημείο ${location.name}`}>
      <header className={styles.header}>
        <span className={styles.budget}>Demo · Συνολικό budget {euros(budget_eur)}</span>
        <h3>{location.name}</h3>
        <p className={styles.context}>
          {[
            location.heat_c !== null ? `${temperature(location.heat_c)} επιφάνειας` : null,
            location.canopy_percent !== null ? `${numeric(location.canopy_percent)}% δενδροκάλυψη` : null,
            shadeLabel(location.shade_status),
          ].filter(Boolean).join(" · ")}
        </p>
      </header>
      <ul className={styles.actions} aria-label="Προτεινόμενες παρεμβάσεις">
        {interventions.map((item) => (
          <li key={item.id}>
            <div className={styles.actionTitle}>
              <strong>{interventionLabel(item.type)}</strong>
              <strong>{euros(item.cost_eur)}</strong>
            </div>
            <p className={styles.context}>
              {[interventionQuantity(item), feasibilityLabel(item.feasibility)].filter(Boolean).join(" · ")}
            </p>
          </li>
        ))}
      </ul>
      <div className={styles.assessment} aria-live="polite">
        {brief ? <SiteAssessment brief={brief} /> : (
          <p className={styles.context}>{unavailable ? "Η εκτίμηση της θέσης δεν είναι διαθέσιμη αυτή τη στιγμή." : "Υπολογίζεται η εκτίμηση για αυτή τη θέση…"}</p>
        )}
      </div>
    </section>
  )
}

function interventionQuantity(item: Intervention) {
  if (item.type === "tree_planting" && item.shade_impact) {
    const count = item.shade_impact.unit_count
    return `${numeric(count)} ${count === 1 ? "δέντρο" : "δέντρα"}`
  }
  const roofArea = item.greened_roof_area_m2 ?? 0
  if (item.type === "green_roof" && roofArea > 0) {
    return `${numeric(roofArea)} m² φυτεμένου δώματος`
  }
  if (item.type === "shade_structure" && item.shade_impact) {
    const count = item.shade_impact.unit_count
    return `${numeric(count)} ${count === 1 ? "σκίαστρο" : "σκίαστρα"}`
  }
  return null
}

function SiteAssessment({ brief }: { brief: SiteCardResponse }) {
  const assumptions = brief.assumptions
  return (
    <>
      <p className={styles.origin}>
        {brief.source === "local_model" ? <><Sparkles size={13} aria-hidden="true" /> Επεξήγηση από τοπικό AI</> : "Επεξήγηση σεναρίου"}
      </p>
      <p className={styles.guidance}>{brief.explanation}</p>
      <div className={styles.finance}>
        <p className={styles.origin}>Ενδεικτική απόσβεση · Demo</p>
        {assumptions ? (
          <>
            <p className={styles.payback}>
              {brief.simple_payback_year === null
                ? `Δεν αποσβένεται σε ${numeric(assumptions.horizon_years)} έτη`
                : `Απλή απόσβεση σε ${numeric(brief.simple_payback_year)} έτη`}
            </p>
            <details className={styles.details}>
              <summary>Υποθετικές παραδοχές</summary>
              <p>{euros(assumptions.annual_savings_eur)} εξοικονόμηση και {euros(assumptions.annual_maintenance_eur)} συντήρηση ανά έτος.</p>
              <p>Ορίζοντας {numeric(assumptions.horizon_years)} έτη · επιτόκιο {numeric(assumptions.discount_rate_pct)}%{assumptions.savings_delay_years > 0 ? ` · έναρξη μετά από ${numeric(assumptions.savings_delay_years)} έτη` : ""}.</p>
              <p>Προεξοφλημένη απόσβεση {brief.discounted_payback_year === null
                ? `πέρα από τα ${numeric(assumptions.horizon_years)} έτη`
                : `σε ${numeric(brief.discounted_payback_year)} έτη`}.</p>
              {brief.required_annual_savings_eur !== null && <p>Απαιτούμενη εξοικονόμηση για κάλυψη κόστους {euros(brief.required_annual_savings_eur)} τον χρόνο.</p>}
            </details>
          </>
        ) : (
          <p className={styles.context}>Δεν υπάρχουν διαθέσιμες παραδοχές για απόσβεση.</p>
        )}
      </div>
    </>
  )
}
