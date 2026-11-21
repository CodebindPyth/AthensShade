"use client"

import { Calculator, ExternalLink, Thermometer } from "lucide-react"
import { useEffect, useState } from "react"
import { api } from "../lib/api"
import type { Location, Plan, SavingsEstimate, ThermalImpact } from "../lib/api"
import { euros, interventionLabel, numeric, shadeArea } from "../lib/format"
import styles from "./investment-panel.module.css"

type InvestmentPanelProps = {
  plan: Plan | null
  isStale?: boolean
  locations?: Map<string, Location>
}

export function CoolingEstimates({ plan, isStale = false, locations }: Pick<InvestmentPanelProps, "plan" | "isStale"> & { locations: Map<string, Location> }) {
  const activePlan = plan && !isStale && plan.selected.length > 0 ? plan : null
  return (
    <section id="cooling-estimates" className={`panel ${styles.panel}`} aria-labelledby="cooling-heading">
      <header className={styles.heading}>
        <h2 id="cooling-heading">Εκτίμηση ψύξης</h2>
        <Thermometer size={20} aria-hidden="true" />
      </header>
      {activePlan?.thermal_impact?.length ? (
        <ul className={styles.impactRows}>
          {activePlan.thermal_impact.map((item) => <ThermalRow key={item.type} item={item} locations={locations} />)}
        </ul>
      ) : <p className={styles.empty}>Υπολόγισε ένα πλάνο για να δεις τα διαθέσιμα θερμικά σενάρια.</p>}
    </section>
  )
}

export function InvestmentPanel({ plan, isStale = false, locations }: InvestmentPanelProps) {
  const activePlan = plan && !isStale && plan.selected.length > 0 ? plan : null

  return (
    <section id="plan-savings" className={["panel", styles.panel].join(" ")} aria-labelledby="savings-heading">
      <header className={styles.heading}>
        <h2 id="savings-heading">Εξοικονόμηση χρημάτων</h2>
        <Calculator size={20} aria-hidden="true" />
      </header>
      {activePlan ? (
        <PlanSavings
          key={JSON.stringify([activePlan.dataset_version, activePlan.budget_eur, activePlan.include_inspection, activePlan.strategy, activePlan.priority_only])}
          plan={activePlan}
          locations={locations}
        />
      ) : (
        <p className={styles.empty}>
          {isStale ? "Υπολόγισε ξανά το πλάνο για να ενημερωθεί η εξοικονόμηση." : plan ? "Το πλάνο περιλαμβάνει 0 παρεμβάσεις. Η εκτιμώμενη μείωση δαπανών είναι 0 € ανά έτος." : "Υπολόγισε ένα πλάνο για να δεις την εκτίμηση εξοικονόμησης."}
        </p>
      )}
    </section>
  )
}

function PlanSavings({ plan, locations }: { plan: Plan; locations?: Map<string, Location> }) {
  const { budget_eur, include_inspection, priority_only, strategy } = plan
  const [estimate, setEstimate] = useState<SavingsEstimate | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    api.savings({ budget_eur, include_inspection, priority_only, strategy }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setEstimate(result) })
      .catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [attempt, budget_eur, include_inspection, priority_only, strategy])

  const yearly = (amount: number) => euros(amount) + " / έτος"
  return (
    <div className={styles.savingsBody}>
      <p className={styles.scenario}>Εκτίμηση ετήσιας λειτουργίας</p>
      {failed ? (
        <p className={styles.error} role="alert">
          Η εκτίμηση εξοικονόμησης δεν είναι διαθέσιμη.{" "}
          <button type="button" className={styles.retry} onClick={() => {
            setFailed(false)
            setAttempt((previous) => previous + 1)
          }}>Δοκίμασε ξανά</button>
        </p>
      ) : !estimate ? (
        <p className={styles.empty} role="status">Υπολογίζεται η ετήσια εξοικονόμηση…</p>
      ) : (
        <>
          <dl className={styles.savingsMetrics} aria-label="Ετήσια σύνολα εξοικονόμησης">
            <div>
              <dt>Δυνητική μείωση δαπανών του Δήμου</dt>
              <dd>{yearly(estimate.gross_annual_eur)}</dd>
            </div>
            <div>
              <dt>Πρόσθετη συντήρηση</dt>
              <dd>{yearly(estimate.annual_maintenance_eur)}</dd>
            </div>
            <div data-net={estimate.net_annual_eur >= 0 ? "saving" : "cost"}>
              <dt>Καθαρό ετήσιο αποτέλεσμα Δήμου</dt>
              <dd>{estimate.net_annual_eur > 0 ? "+" : ""}{yearly(estimate.net_annual_eur)}</dd>
            </div>
          </dl>
          <p className={styles.note}>Το ετήσιο αποτέλεσμα αφαιρεί τη συντήρηση από τις δυνητικές μειώσεις δαπανών. Η αρχική επένδυση εμφανίζεται στο πλάνο. Για τα δέντρα η εκτίμηση αφορά την ώριμη κόμη. Ο Δήμος μπορεί να ελέγξει τις παραδοχές με θερινούς λογαριασμούς ρεύματος και συμβάσεις.</p>
          <details className={styles.assumptions}>
            <summary>Υποθετικές παραδοχές ανά παρέμβαση</summary>
            <ul>
              {estimate.items.map((item) => {
                const siteName = locations?.get(item.location_id)?.name
                return (
                  <li key={item.intervention_id}>
                    <div className={styles.itemHeading}>
                      <strong>{interventionLabel(item.type)}{siteName && " · " + siteName}</strong>
                      <span data-net={item.net_annual_eur >= 0 ? "saving" : "cost"}>
                        {item.net_annual_eur >= 0 ? "Καθαρή εξοικονόμηση " : "Καθαρή επιβάρυνση "}{yearly(Math.abs(item.net_annual_eur))}
                      </span>
                    </div>
                    <p className={styles.note}>Μείωση δαπανών {yearly(item.gross_annual_eur)} · Συντήρηση {yearly(item.annual_maintenance_eur)}</p>
                    {item.assumptions.length > 0 && (
                      <ul className={styles.itemAssumptions}>
                        {item.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          </details>
        </>
      )}
    </div>
  )
}

function ThermalRow({ item, locations }: { item: ThermalImpact; locations?: Map<string, Location> }) {
  const siteNames = item.location_ids.flatMap((id) => {
    const location = locations?.get(id)
    return location ? [location.name] : []
  })
  const cooling = item.cooling_min_c != null && item.cooling_max_c != null
    ? `${formatRange(item.cooling_min_c, item.cooling_max_c)} °C`
    : null
  const area = item.area_min_m2 != null && item.area_max_m2 != null
    ? shadeArea(item.area_min_m2, item.area_max_m2)
    : null
  const costPerArea = item.cost_per_m2_min_eur != null && item.cost_per_m2_max_eur != null
    ? `${formatRange(item.cost_per_m2_min_eur, item.cost_per_m2_max_eur)} €/m²`
    : null
  return (
    <li className={styles.impactRow}>
      <h4>{interventionLabel(item.type)}</h4>
      {siteNames.length > 0 && <p className={styles.note}>{siteNames.join(", ")}</p>}
      <p className={styles.forecast}>
        <strong>{cooling ?? "Χωρίς ποσοτική εκτίμηση ψύξης"}</strong>
        {cooling && <span>Ενδεικτική μείωση</span>}
      </p>
      <p className={styles.metric}>{item.metric}</p>
      <dl className={styles.impactData}>
        {area && <div><dt>Εκτιμώμενη επιφάνεια</dt><dd>{area}</dd></div>}
        <div><dt>Αρχικό κόστος</dt><dd>{euros(item.installation_cost_eur)}</dd></div>
        {costPerArea && <div><dt>Αρχικό κόστος ανά m²</dt><dd>{costPerArea}</dd></div>}
      </dl>
      <p className={styles.evidence}>
        {item.evidence}
        {item.evidence_url && (
          <>{" "}<a href={item.evidence_url} target="_blank" rel="noreferrer">Πηγή <ExternalLink aria-hidden="true" size={11} /></a></>
        )}
      </p>
    </li>
  )
}

function formatRange(min: number, max: number) {
  return min === max ? numeric(min) : `${numeric(min)}–${numeric(max)}`
}
