import { House, TreeDeciduous, Umbrella } from "lucide-react"
import type { Plan, ShadeRange } from "../lib/api"
import { shadeArea } from "../lib/format"
import styles from "./plan-impact.module.css"

const metrics = [
  { id: "installed", label: "Σκιά μετά την εγκατάσταση", icon: Umbrella, interventionType: "shade_structure" },
  { id: "mature", label: "Σκιά από ώριμα δέντρα", icon: TreeDeciduous, interventionType: "tree_planting" },
  { id: "roof", label: "Επιφάνεια φυτεμένων δωμάτων", icon: House, interventionType: "green_roof" },
] as const

function getPlanImpact(plan: Plan) {
  const roof = plan.greened_roof_area_m2
  const values = {
    installed: plan.shade_impact?.after_installation,
    mature: plan.shade_impact?.at_tree_maturity,
    roof: roof == null ? undefined : { min_m2: roof, max_m2: roof },
  }
  return metrics.map((metric) => {
    const relevant = plan.selected.filter((item) => item.type === metric.interventionType)
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
  return (
    <section className={`shade-impact ${styles.summary}`} aria-label="Εκτίμηση σκίασης και πρασίνου">
      <h3>Εκτίμηση σκίασης και πρασίνου</h3>
      <dl className={styles.metrics}>
        {rows.map(({ id, label, icon: Icon, range }) => (
          <div key={id} className={styles.metric}>
            <dt><Icon size={16} aria-hidden="true" />{label}</dt>
            <dd>{areaLabel(range)}</dd>
          </div>
        ))}
      </dl>
      <p className={styles.caption}>Οι επιφάνειες σκιάς είναι ενδεικτικές, πριν από πιθανές επικαλύψεις.</p>
      {missingCount > 0 && <p className={styles.caption}>Παρεμβάσεις χωρίς εκτίμηση επιφάνειας · {missingCount}</p>}
      <p className={styles.caption}>
        Η μεταβολή θερμοκρασίας προκύπτει από{" "}
        <a href="#microclimate-monitor">μετρήσεις πριν και μετά</a>.
      </p>
    </section>
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
