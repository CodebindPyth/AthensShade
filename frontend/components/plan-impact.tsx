import type { Intervention, Plan, ShadeRange } from "../lib/api"
import { euros, numeric, shadeArea } from "../lib/format"
import { InterventionSymbol } from "./intervention-symbol"
import styles from "./plan-impact.module.css"

const metrics = [
  { id: "installed", label: "Σκιά μετά την εγκατάσταση", type: "shade_structure" },
  { id: "mature", label: "Σκιά από ώριμα δέντρα", type: "tree_planting" },
  { id: "roof", label: "Επιφάνεια φυτεμένων δωμάτων", type: "green_roof" },
] as const

const unitTypes = [
  { id: "tree_planting", label: "Δέντρα" },
  { id: "shade_structure", label: "Σκίαστρα" },
] as const

function unitLabel(items: Intervention[], type: string) {
  const relevant = items.filter((item) => item.type === type)
  const reported = relevant.flatMap((item) => item.shade_impact?.unit_count ?? [])
  const known = reported.reduce((sum, count) => sum + count, 0)
  if (relevant.length === reported.length) return numeric(known)
  return reported.length ? `≥${numeric(known)}` : "Άγνωστο"
}

function getPlanImpact(plan: Plan) {
  const roof = plan.greened_roof_area_m2
  const values = {
    installed: plan.shade_impact?.after_installation,
    mature: plan.shade_impact?.at_tree_maturity,
    roof: roof == null ? undefined : { min_m2: roof, max_m2: roof },
  }
  return metrics.map((metric) => {
    const relevant = plan.selected.filter((item) => metric.type === item.type)
    const missingCount = relevant.filter((item) => (
      metric.id === "roof" ? item.greened_roof_area_m2 == null : item.shade_impact == null
    )).length
    const range = values[metric.id]
    // A zero aggregate also occurs when every intervention of this type lacks an estimate.
    const hasOnlyUnknown = relevant.length > 0 && missingCount === relevant.length && range?.max_m2 === 0
    return { ...metric, range: hasOnlyUnknown ? undefined : range, missingCount }
  })
}

function areaLabel(range: ShadeRange | undefined) {
  return range ? shadeArea(range.min_m2, range.max_m2) : "Χωρίς εκτίμηση"
}

export function ImpactCard({ plan }: { plan: Plan }) {
  const rows = getPlanImpact(plan)
  const missingCount = rows.reduce((total, row) => total + row.missingCount, 0)
  const roof = rows.find((row) => row.id === "roof")
  return (
    <>
      <section className={styles.quantities} aria-label="Σύνολο παρεμβάσεων για τον προϋπολογισμό">
        <h3>Σύνολο πλάνου για {euros(plan.budget_eur)}</h3>
        <dl>
          {unitTypes.map(({ id, label }) => (
            <div key={id}>
              <dt><InterventionSymbol type={id} size={15} />{label}</dt>
              <dd>{unitLabel(plan.selected, id)}</dd>
            </div>
          ))}
          <div>
            <dt><InterventionSymbol type="green_roof" size={15} />Φυτεμένα δώματα</dt>
            <dd>{areaLabel(roof?.range)}</dd>
          </div>
        </dl>
      </section>
      <section className={`shade-impact ${styles.summary}`} aria-label="Εκτίμηση σκίασης και πρασίνου">
        <h3>Εκτίμηση σκίασης και πρασίνου</h3>
        <dl className={styles.metrics}>
          {rows.filter(({ id }) => id !== "roof").map(({ id, label, type, range }) => (
            <div key={id} className={styles.metric}>
              <dt><InterventionSymbol type={type} size={16} />{label}</dt>
              <dd>{areaLabel(range)}</dd>
            </div>
          ))}
        </dl>
        <p className={styles.caption}>Οι επιφάνειες σκιάς είναι ενδεικτικές, πριν από πιθανές επικαλύψεις.</p>
        {missingCount > 0 && <p className={styles.caption}>Παρεμβάσεις χωρίς εκτίμηση επιφάνειας · {missingCount}</p>}
      </section>
    </>
  )
}

export function ImpactComparison({ baseline, proposed }: { baseline: Plan; proposed: Plan }) {
  const baselineMetrics = getPlanImpact(baseline)
  const proposedMetrics = getPlanImpact(proposed)
  const allMetrics = [...baselineMetrics, ...proposedMetrics]
  const maxArea = Math.max(0, ...allMetrics.map(({ range }) => range?.max_m2 ?? 0))
  const hasIntervals = allMetrics.some(({ range }) => range && range.min_m2 !== range.max_m2)
  return (
    <section className={styles.comparison} aria-label="Σύγκριση εκτιμώμενης σκίασης και πρασίνου">
      <h3>Σύγκριση σκίασης και πρασίνου</h3>
      <ul className={styles.legend} aria-hidden="true">
        <li data-scenario="baseline">Αρχικό πλάνο</li>
        <li data-scenario="proposed">Νέο πλάνο</li>
      </ul>
      {maxArea > 0 && <div className={styles.axis} aria-hidden="true"><span>0 m²</span><span>{shadeArea(maxArea, maxArea)}</span></div>}
      <ul className={styles.seriesList}>
        {baselineMetrics.map(({ id, label, range }, index) => (
          <li key={id}>
            <h4>{label}</h4>
            <div className={styles.seriesPair}>
              <ImpactBar range={range} maxArea={maxArea} scenario="baseline" />
              <ImpactBar range={proposedMetrics[index].range} maxArea={maxArea} scenario="proposed" />
            </div>
          </li>
        ))}
      </ul>
      {hasIntervals && <p className={styles.caption}>Η ανοιχτή απόχρωση δείχνει το εύρος από την ελάχιστη έως τη μέγιστη εκτίμηση.</p>}
      {allMetrics.some(({ missingCount }) => missingCount > 0) && (
        <p className={styles.caption}>Οι επιφάνειες αφορούν παρεμβάσεις με διαθέσιμες εκτιμήσεις.</p>
      )}
    </section>
  )
}

function ImpactBar({ range, maxArea, scenario }: {
  range: ShadeRange | undefined
  maxArea: number
  scenario: "baseline" | "proposed"
}) {
  const scale = maxArea || 1
  const lower = range ? (range.min_m2 / scale) * 100 : 0
  const upper = range ? (range.max_m2 / scale) * 100 : 0
  return (
    <div className={styles.barRow} data-scenario={scenario}>
      <div className={styles.track} aria-hidden="true">
        <span className={styles.upper} style={{ width: `${upper}%` }} />
        <span className={styles.lower} style={{ width: `${lower}%` }} />
      </div>
      <span className={styles.barValue}>
        <span className={styles.screenReader}>{scenario === "baseline" ? "Αρχικό πλάνο: " : "Νέο πλάνο: "}</span>
        {areaLabel(range)}
      </span>
    </div>
  )
}
