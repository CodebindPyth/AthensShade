import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { api } from "../lib/api"
import type { Intervention, Location, Plan, SiteCardResponse } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, numeric, shadeArea, shadeLabel, temperature } from "../lib/format"
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
            shadeLabel(location.shade_status),
          ].filter(Boolean).join(" · ")}
        </p>
      </header>
      <dl className={styles.greenContext}>
        <div>
          <dt>Δενδροκάλυψη στα 100 m</dt>
          <dd>{location.canopy_percent === null ? "Άγνωστη" : `${numeric(location.canopy_percent)}%`}</dd>
        </div>
        {location.planting_records_count != null && (
          <div><dt>Καταγραφές φύτευσης στα 100 m</dt><dd>{numeric(location.planting_records_count)}</dd></div>
        )}
      </dl>
      <ul className={styles.actions} aria-label="Προτεινόμενες παρεμβάσεις">
        {interventions.map((item) => {
          const benefit = brief?.savings?.items.find((entry) => entry.intervention_id === item.id)?.benefit
          return (
          <li key={item.id}>
            <div className={styles.actionTitle}>
              <strong>{interventionLabel(item.type)}</strong>
              <strong title="Αρχικό κόστος παρέμβασης">{euros(item.cost_eur)}</strong>
            </div>
            <p className={styles.context}>
              {[interventionQuantity(item), feasibilityLabel(item.feasibility)].filter(Boolean).join(" · ")}
            </p>
            {item.shade_impact && (
              <p className={styles.context}>
                Εκτιμώμενη σκιά {shadeArea(item.shade_impact.estimated_min_m2, item.shade_impact.estimated_max_m2)}
                {item.shade_impact.horizon === "at_tree_maturity" ? " σε ώριμη κόμη" : " μετά την εγκατάσταση"}
              </p>
            )}
            {benefit && <p className={styles.benefit}>{benefit}</p>}
          </li>
          )
        })}
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
  if (item.type === "shaded_bench" && item.shade_impact) {
    const count = item.shade_impact.unit_count
    return `${numeric(count)} ${count === 1 ? "παγκάκι με σκίαστρο" : "παγκάκια με σκίαστρο"}`
  }
  return null
}

function SiteAssessment({ brief }: { brief: SiteCardResponse }) {
  const { savings } = brief
  const assumptions = savings?.items.flatMap((item) => item.assumptions) ?? []
  return (
    <>
      <p className={styles.origin}>
        {brief.source === "local_model" ? <><Sparkles size={13} aria-hidden="true" /> Επεξήγηση από τοπικό AI</> : "Επεξήγηση σεναρίου"}
      </p>
      <p className={styles.guidance}>{brief.explanation}</p>
      <div className={styles.finance}>
        <p className={styles.origin}>Ετήσια οικονομική επίδραση · Demo</p>
        {savings ? (
          <>
            <p className={styles.savingsFigure}>
              {savings.net_annual_eur >= 0
                ? `${euros(savings.net_annual_eur)}/έτος καθαρή εξοικονόμηση`
                : `${euros(-savings.net_annual_eur)}/έτος καθαρό κόστος`}
            </p>
            {assumptions[0] && <p className={styles.context}>{assumptions[0]}</p>}
            <details className={styles.details}>
              <summary>Παραδοχές υποθετικού σεναρίου</summary>
              <p>{euros(savings.gross_annual_eur)} μείωση δαπανών · {euros(savings.annual_maintenance_eur)} συντήρηση ανά έτος.</p>
              {Array.from(new Set(assumptions.slice(1))).map((assumption) => <p key={assumption}>{assumption}</p>)}
            </details>
          </>
        ) : (
          <p className={styles.context}>Δεν υπάρχει διαθέσιμη εκτίμηση εξοικονόμησης.</p>
        )}
      </div>
    </>
  )
}
