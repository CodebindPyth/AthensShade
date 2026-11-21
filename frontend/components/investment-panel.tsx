"use client"

import { Calculator, ExternalLink, Thermometer } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { api } from "../lib/api"
import type { Comparison, FinancialAppraisal, FinancialAssumptions, Location, Plan, ThermalImpact } from "../lib/api"
import { euros, interventionLabel, numeric, shadeArea } from "../lib/format"
import styles from "./investment-panel.module.css"

type InvestmentPanelProps = {
  plan: Plan | null
  isStale?: boolean
  comparison?: Comparison | null
}

const signedNumber = new Intl.NumberFormat("el-GR", { signDisplay: "exceptZero", maximumFractionDigits: 2 })
const fields = [
  { name: "annual-savings", label: "Ετήσιες εξοικονομήσεις (€)", inputMode: "decimal", step: "0.01", min: 0, max: 100000000 },
  { name: "annual-maintenance", label: "Ετήσια συντήρηση (€)", inputMode: "decimal", step: "0.01", min: 0, max: 100000000 },
  { name: "horizon", label: "Ορίζοντας (έτη)", inputMode: "numeric", step: "1", min: 1, max: 40 },
  { name: "discount-rate", label: "Προεξοφλητικό επιτόκιο (%)", inputMode: "decimal", step: "0.01", min: 0, max: 30 },
  { name: "savings-delay", label: "Έτη μέχρι να αρχίσει η εξοικονόμηση", inputMode: "numeric", step: "1", min: 0, max: 40 },
  { name: "capital-override", label: "Δικό σου αρχικό κόστος (€)", inputMode: "decimal", step: "0.01", min: 0.01, max: 100000000 },
  { name: "grant", label: "Επιχορήγηση στο αρχικό κόστος (€)", inputMode: "decimal", step: "0.01", min: 0, max: null },
] as const

const initialInputs = {
  "annual-savings": "",
  "annual-maintenance": "",
  horizon: "20",
  "discount-rate": "0",
  "savings-delay": "0",
  "capital-override": "",
  grant: "0",
}
const exampleInputs = {
  ...initialInputs,
  "annual-savings": "9000",
  "annual-maintenance": "2000",
  "discount-rate": "3",
}
const coverageAssumptions = {
  annual_savings_eur: 0,
  annual_maintenance_eur: 0,
  horizon_years: 20,
  discount_rate_pct: 3,
  savings_delay_years: 0,
  grant_eur: 0,
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
      <a className={styles.measurementLink} href="#microclimate-monitor">Αποτίμηση με μετρήσεις πριν και μετά</a>
    </section>
  )
}

export function InvestmentPanel({ plan, isStale = false, comparison }: InvestmentPanelProps) {
  const activePlan = plan && !isStale && plan.selected.length > 0 ? plan : null
  const comparable = activePlan && comparison && sameScenario(activePlan, comparison.proposed) ? comparison : null

  return (
    <section id="investment-appraisal" className={`panel ${styles.panel}`} aria-labelledby="investment-heading">
      <header className={styles.heading}>
        <h2 id="investment-heading">Εκτίμηση απόσβεσης</h2>
        {activePlan && (
          <p className={styles.cost}>
            <span>Αρχικό κόστος πλάνου</span>
            <strong>{euros(activePlan.total_cost_eur)}</strong>
          </p>
        )}
      </header>
      {activePlan ? (
        <div className={styles.sectionBody}>
          <div className={styles.finance}>
            <h3 className={styles.subheading}><Calculator size={17} aria-hidden="true" /> Οικονομική αποτίμηση για τον Δήμο</h3>
            {comparable && <ComparisonCost comparison={comparable} />}
            <FundingThreshold plan={activePlan} />
            <FinanceForm
              key={JSON.stringify([activePlan.dataset_version, activePlan.strategy, activePlan.budget_eur, activePlan.include_inspection, activePlan.priority_only, activePlan.total_cost_eur, activePlan.selected.map((item) => item.id)])}
              plan={activePlan}
            />
          </div>
        </div>
      ) : (
        <p className={styles.empty}>
          {isStale ? "Υπολόγισε ξανά το πλάνο για να ενημερωθεί η εκτίμηση." : "Υπολόγισε ένα πλάνο με παρεμβάσεις για να δεις την εκτίμηση απόσβεσης."}
        </p>
      )}
    </section>
  )
}

function FundingThreshold({ plan }: { plan: Plan }) {
  const { budget_eur, include_inspection, priority_only, strategy } = plan
  const [threshold, setThreshold] = useState<number | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setThreshold(null)
    setUnavailable(false)
    api.appraise({ budget_eur, include_inspection, priority_only, strategy }, coverageAssumptions, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setThreshold(result.required_annual_savings_eur) })
      .catch(() => { if (!controller.signal.aborted) setUnavailable(true) })
    return () => controller.abort()
  }, [budget_eur, include_inspection, priority_only, strategy])

  return (
    <section className={styles.funding} aria-label="Όριο οικονομικής κάλυψης">
      <strong>Όριο οικονομικής κάλυψης</strong>
      <p aria-live="polite">
        {threshold !== null
          ? <>Το πλάνο χρειάζεται τουλάχιστον <strong>{euros(threshold)} τον χρόνο</strong> σε εξοικονομήσεις για να καλύψει την αρχική επένδυση.</>
          : unavailable ? "Ο αυτόματος υπολογισμός δεν είναι διαθέσιμος." : "Υπολογισμός ελάχιστης ετήσιας εξοικονόμησης…"}
      </p>
      <p className={styles.note}>Ορίζοντας 20 έτη · προεξόφληση 3% · 0 € συντήρηση και επιχορήγηση. Συμπλήρωσε τα πραγματικά ποσά παρακάτω για πλήρη αποτίμηση.</p>
      <details className={styles.fundingDetails}>
        <summary>Πώς μπορεί να αποσβεστεί</summary>
        <ul>
          <li><strong>Φυτεμένα δώματα:</strong> μέτρησε τις kWh που εξοικονομήθηκαν σε συγκρίσιμες συνθήκες και πολλαπλασίασε με τη μεταβλητή χρέωση. Πρόσθεσε το κόστος άρδευσης και συντήρησης στο αντίστοιχο πεδίο.</li>
          <li><strong>Σκίαστρα και παγκάκια:</strong> σύγκρινε κόστος ανά m² άμεσης σκιάς και ανά σκιασμένη θέση ανάπαυσης. Στις εξοικονομήσεις καταχώρισε μόνο τεκμηριωμένες δαπάνες που αποφεύγει ο Δήμος.</li>
          <li><strong>Επιχορήγηση:</strong> καταχώρισε το επιβεβαιωμένο ποσό για να μειωθεί η ίδια συμμετοχή.</li>
        </ul>
      </details>
    </section>
  )
}

function sameScenario(plan: Plan, other: Plan) {
  return plan.dataset_version === other.dataset_version
    && plan.budget_eur === other.budget_eur
    && plan.include_inspection === other.include_inspection
    && plan.priority_only === other.priority_only
    && plan.strategy === other.strategy
}

function ComparisonCost({ comparison }: { comparison: Comparison }) {
  const difference = comparison.proposed.total_cost_eur - comparison.baseline.total_cost_eur
  if (Math.abs(difference) < 0.005) return <p className={styles.comparison}>Ίδιο αρχικό κόστος με το πλάνο αναφοράς.</p>
  return (
    <p className={styles.comparison}>
      Το τρέχον πλάνο κοστίζει <strong>{euros(Math.abs(difference))}</strong> {difference > 0 ? "περισσότερο" : "λιγότερο"} από το πλάνο αναφοράς.
    </p>
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

function FinanceForm({ plan }: { plan: Plan }) {
  const [inputs, setInputs] = useState(initialInputs)
  const [selectedType, setSelectedType] = useState("")
  const [exampleLoaded, setExampleLoaded] = useState(false)
  const [assessment, setAssessment] = useState<FinancialAppraisal | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const request = useRef<AbortController | null>(null)
  const costsByType = new Map<string, number>()
  for (const intervention of plan.selected) {
    const currentCost = costsByType.get(intervention.type) ?? 0
    costsByType.set(intervention.type, currentCost + intervention.cost_eur)
  }
  const capitalCost = selectedType ? costsByType.get(selectedType) ?? 0 : plan.total_cost_eur
  const capitalOverride = inputs["capital-override"] === "" ? null : Number(inputs["capital-override"])
  const grantLimit = capitalOverride !== null && capitalOverride > 0 ? capitalOverride : capitalCost

  useEffect(() => () => request.current?.abort(), [])

  function invalidate() {
    request.current?.abort()
    setAssessment(null)
    setError(null)
    setPending(false)
  }

  function loadExample() {
    invalidate()
    setInputs(exampleInputs)
    setExampleLoaded(true)
  }

  function changeScope(type: string) {
    setSelectedType(type)
    setInputs((previous) => ({
      ...initialInputs,
      horizon: previous.horizon,
      "discount-rate": previous["discount-rate"],
    }))
    setExampleLoaded(false)
    invalidate()
  }

  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const assumptions: FinancialAssumptions = {
      annual_savings_eur: Number(inputs["annual-savings"]),
      annual_maintenance_eur: Number(inputs["annual-maintenance"]),
      horizon_years: Number(inputs.horizon),
      discount_rate_pct: Number(inputs["discount-rate"]),
      savings_delay_years: Number(inputs["savings-delay"]),
      grant_eur: Number(inputs.grant),
      capital_override_eur: capitalOverride,
    }
    if (assumptions.savings_delay_years > assumptions.horizon_years) {
      setError("Η καθυστέρηση εξοικονόμησης πρέπει να χωρά στον ορίζοντα της αποτίμησης.")
      return
    }
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setError(null)
    setAssessment(null)
    setPending(true)
    try {
      const result = await api.appraise({
        budget_eur: plan.budget_eur,
        priority_only: plan.priority_only,
        include_inspection: plan.include_inspection,
        strategy: plan.strategy,
      }, assumptions, controller.signal, selectedType || undefined)
      if (!controller.signal.aborted) setAssessment(result)
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error && failure.message
          ? failure.message
          : "Η αποτίμηση δεν ολοκληρώθηκε. Έλεγξε τις παραδοχές και ξαναδοκίμασε.")
      }
    } finally {
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return (
    <>
      {costsByType.size > 1 && (
        <div className={styles.scope}>
          <label>
            Αντικείμενο αποτίμησης
            <select value={selectedType} onChange={(event) => changeScope(event.currentTarget.value)}>
              <option value="">Σύνολο πλάνου</option>
              {[...costsByType.keys()].map((type) => <option key={type} value={type}>{interventionLabel(type)}</option>)}
            </select>
          </label>
          {selectedType && <p className={styles.note}>Αρχικό κόστος επιλογής <strong>{euros(capitalCost)}</strong></p>}
        </div>
      )}
      <p className={styles.note}>Χρησιμοποίησε εξοικονομήσεις που θα φανούν στον δημοτικό προϋπολογισμό. Για το ρεύμα, πολλαπλασίασε τις εκτιμώμενες kWh που θα εξοικονομηθούν με τη μεταβλητή χρέωση ανά kWh.</p>
      <button type="button" className={styles.example} onClick={loadExample}>Φόρτωσε υποθετικό παράδειγμα</button>
      {exampleLoaded && <p className={styles.note} role="status">Το σενάριο ξεκίνησε με υποθετικά ποσά. Προσάρμοσέ τα με στοιχεία του Δήμου.</p>}
      <form className={styles.form} onSubmit={calculate} aria-label="Παραδοχές οικονομικής αποτίμησης">
        <div className={styles.fields}>
          {fields.map(({ name, label, max, ...limits }) => (
            <label key={name}>
              {label}
              <input
                {...limits}
                name={name}
                type="number"
                max={max ?? grantLimit.toFixed(2)}
                value={inputs[name]}
                onChange={(event) => {
                  const value = event.currentTarget.value
                  setInputs((previous) => ({ ...previous, [name]: value }))
                  invalidate()
                }}
                required={name !== "capital-override"}
                aria-describedby={name === "capital-override" ? "initial-cost-help" : undefined}
              />
            </label>
          ))}
        </div>
        <p className={styles.costHelp} id="initial-cost-help">Προαιρετικά, βάλε ποσό προσφοράς που περιλαμβάνει ΦΠΑ και αρχικές εργασίες. Με κενό πεδίο χρησιμοποιείται το εκτιμώμενο κόστος της επιλογής.</p>
        <button type="submit" className={`primary-button ${styles.submit}`} disabled={pending}>
          {pending ? "Υπολογισμός…" : "Υπολόγισε την απόσβεση"}
        </button>
      </form>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div aria-live="polite" aria-busy={pending}>
        {assessment && <AssessmentResult assessment={assessment} />}
      </div>
    </>
  )
}

function formatPayback(year: number | null) {
  if (year === null) return "Εκτός ορίζοντα"
  return year === 0 ? "Κατά την έναρξη" : `Έτος ${numeric(year)}`
}

function AssessmentResult({ assessment }: { assessment: FinancialAppraisal }) {
  return (
    <section className={styles.results} aria-label="Αποτέλεσμα οικονομικής αποτίμησης">
      <h4>Αποτέλεσμα οικονομικής αποτίμησης</h4>
      <dl className={styles.resultMetrics}>
        <div><dt>Αρχικό κόστος μετά την επιχορήγηση</dt><dd>{euros(assessment.net_initial_cost_eur)}</dd></div>
        <div><dt>Καθαρή παρούσα αξία (ΚΠΑ)</dt><dd className={assessment.npv_eur < 0 ? styles.negative : undefined}>{euros(assessment.npv_eur)}</dd></div>
        <div><dt>Σωρευτικό υπόλοιπο</dt><dd>{euros(assessment.cumulative_net_eur)}</dd></div>
        <div><dt>Απλή απόσβεση</dt><dd>{formatPayback(assessment.simple_payback_year)}</dd></div>
        <div><dt>Προεξοφλημένη απόσβεση</dt><dd>{formatPayback(assessment.discounted_payback_year)}</dd></div>
      </dl>
      {assessment.required_annual_savings_eur !== null ? (
        <p className={styles.threshold}>
          Για να καλυφθεί η επένδυση στον επιλεγμένο ορίζοντα, απαιτούνται <strong>{euros(assessment.required_annual_savings_eur)} ετησίως</strong> σε εξοικονομήσεις μετά την έναρξή τους.
        </p>
      ) : (
        <p className={styles.threshold}>Ο επιλεγμένος ορίζοντας δεν περιλαμβάνει έτος με εξοικονόμηση.</p>
      )}
      <p className={styles.note}>
        {assessment.npv_eur < 0
          ? "Στο σενάριο αυτό το προεξοφλημένο κόστος υπερβαίνει τις εξοικονομήσεις."
          : "Στο σενάριο αυτό οι προεξοφλημένες εξοικονομήσεις καλύπτουν το κόστος."}
        {" "}Οι ετήσιες χρηματορροές υπολογίζονται στο τέλος κάθε έτους, σε σημερινές τιμές.
      </p>
      {assessment.sensitivity.length > 0 && (
        <table className={styles.sensitivity}>
          <caption>ΚΠΑ σε τρία σενάρια εξοικονόμησης</caption>
          <thead><tr><th scope="col">Μεταβολή</th><th scope="col">Εξοικονόμηση ανά έτος</th><th scope="col">ΚΠΑ</th></tr></thead>
          <tbody>
            {assessment.sensitivity.map((scenario) => (
              <tr key={scenario.change_pct}>
                <th scope="row">{signedNumber.format(scenario.change_pct)}%</th>
                <td>{euros(scenario.annual_savings_eur)}</td>
                <td>{euros(scenario.npv_eur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
