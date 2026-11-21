"use client"

import { ArrowDownUp, CheckCircle2, CircleAlert, FileText, House, MapPin, Minus, Plus, ShieldCheck, TreeDeciduous } from "lucide-react"
import type { FormEvent } from "react"
import type { Comparison, Location, Plan, Strategy } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, shadeArea } from "../lib/format"
import { ImpactCard, ImpactComparison } from "./plan-impact"

type PlannerProps = {
  budget: string
  setBudget: (budget: string) => void
  includeInspection: boolean
  setIncludeInspection: (include: boolean) => void
  strategy: Strategy
  setStrategy: (strategy: Strategy) => void
  busy: boolean
  comparisonBusy: boolean
  error: string | null
  comparisonError: string | null
  plan: Plan | null
  comparison: Comparison | null
  isStale: boolean
  compareOpen: boolean
  baseline: string
  setBaseline: (budget: string) => void
  toggleCompare: () => void
  onCalculate: (event: FormEvent<HTMLFormElement>) => void
  onCompare: (event: FormEvent<HTMLFormElement>) => void
  onSelectLocation: (id: string) => void
  locations: Map<string, Location>
}

const budgetPresets = [50_000, 100_000, 150_000]

export function Planner(props: PlannerProps) {
  const { budget, includeInspection, plan, comparison, locations, onSelectLocation } = props
  return (
    <aside className="panel planner" aria-labelledby="planner-title">
      <div className="planner-heading">
        <h2 id="planner-title">Πλάνο παρεμβάσεων</h2>
        <span className="header-icon"><FileText size={18} aria-hidden="true" /></span>
      </div>
      <form className="budget-form" onSubmit={props.onCalculate}>
        <label htmlFor="plan-budget">Προϋπολογισμός</label>
        <div className="currency-input">
          <input id="plan-budget" type="number" inputMode="decimal" min="0" step="0.01" max="100000000" value={budget} onChange={(event) => props.setBudget(event.target.value)} required />
          <span aria-hidden="true">€</span>
        </div>
        <div className="budget-presets" aria-label="Προκαθορισμένοι προϋπολογισμοί">
          {budgetPresets.map((amount) => (
            <button key={amount} className={Number(budget) === amount ? "preset active" : "preset"} type="button" aria-pressed={Number(budget) === amount} onClick={() => props.setBudget(String(amount))}>{euros(amount)}</button>
          ))}
        </div>
        <div className="strategy-field">
          <label htmlFor="plan-strategy">Στόχος σχεδίου</label>
          <select id="plan-strategy" value={props.strategy} onChange={(event) => props.setStrategy(event.target.value as Strategy)}>
            <option value="balanced">Ισορροπημένο πλάνο</option>
            <option value="immediate_shade">Άμεση σκίαση</option>
            <option value="shade_and_rest">Σκίαση και ξεκούραση</option>
          </select>
        </div>
        <label className="inspection-check">
          <input type="checkbox" checked={includeInspection} onChange={(event) => props.setIncludeInspection(event.target.checked)} />
          <span>Συμπερίληψη θέσεων προς αυτοψία</span>
        </label>
        <button type="submit" className="primary-button" disabled={props.busy}>{props.busy ? "Υπολογισμός…" : "Υπολόγισε πλάνο"}</button>
      </form>
      {props.error && <p className="notice notice--error" role="alert"><CircleAlert size={17} /> {props.error}</p>}
      {props.isStale && <p className="notice" role="status">Οι ρυθμίσεις άλλαξαν. Υπολόγισε ξανά για να ενημερώσεις το πλάνο.</p>}
      <div className="plan-output" aria-live="polite" aria-busy={props.busy}>
        {plan && (
          <>
            <div className="plan-totals">
              <div><span>Εκτιμώμενο κόστος</span><strong>{euros(plan.total_cost_eur)}</strong></div>
              <div><span>Υπόλοιπο</span><strong className="remaining">{euros(plan.remaining_budget_eur)}</strong></div>
            </div>
            {plan.include_inspection ? (
              <p className="notice notice--inspection"><CircleAlert size={17} /> Demo για {euros(plan.budget_eur)}. Οι θέσεις προς αυτοψία χρειάζονται επιτόπια επιβεβαίωση.</p>
            ) : (
              <p className="verified-label"><ShieldCheck size={16} /> Επιβεβαιωμένες θέσεις</p>
            )}
            {plan.selected.length > 0 && Boolean(plan.shade_impact || plan.greened_roof_area_m2) && <ImpactCard plan={plan} />}
            {plan.selected.length > 0 && !props.isStale && (
              <nav aria-label="Ανάλυση πλάνου" className="plan-detail-links">
                <a className="impact-evaluation-link" href="#city-brief">Σύνοψη για τον Δήμο ↓</a>
                <a className="impact-evaluation-link" href="#cooling-estimates">Εκτίμηση ψύξης ↓</a>
                <a className="impact-evaluation-link" href="#plan-savings">Εξοικονόμηση χρημάτων ↓</a>
              </nav>
            )}
            {plan.selected.length === 0 ? (
              <div className="plan-empty">
                <strong>{plan.status === "no_affordable_interventions" ? "Ο προϋπολογισμός δεν επαρκεί" : plan.include_inspection ? "Δεν επιλέχθηκαν θέσεις" : "Δεν βρέθηκαν επιβεβαιωμένες θέσεις"}</strong>
                <p>{plan.status === "no_affordable_interventions" ? "Αύξησε τον προϋπολογισμό για να ελέγξεις τις διαθέσιμες παρεμβάσεις." : plan.include_inspection ? "Δεν υπάρχουν κατάλληλες υποψήφιες παρεμβάσεις στο σύνολο δεδομένων." : "Μπορείς να συμπεριλάβεις θέσεις προς αυτοψία για ένα διερευνητικό πλάνο."}</p>
              </div>
            ) : (
              <ul className="intervention-list">
                {plan.selected.map((item) => (
                  <li key={item.id}>
                    <button type="button" onClick={() => onSelectLocation(item.location_id)}>
                      <span className="intervention-icon">{item.type === "green_roof" ? <House size={17} /> : item.type === "tree_planting" || item.type === "greenery" ? <TreeDeciduous size={17} /> : <MapPin size={17} />}</span>
                      <span className="intervention-description">
                        <strong>{locations.get(item.location_id)?.name ?? item.location_id}</strong>
                        <span>{interventionLabel(item.type)}</span>
                        {item.shade_impact && <span className="row-impact">{shadeArea(item.shade_impact.estimated_min_m2, item.shade_impact.estimated_max_m2)} δυνητικής σκιάς</span>}
                        {item.greened_roof_area_m2 != null && <span className="row-impact">{shadeArea(item.greened_roof_area_m2, item.greened_roof_area_m2)} δυνητικής φύτευσης στο δώμα</span>}
                        {item.feasibility !== "verified" && <small>{feasibilityLabel(item.feasibility)}</small>}
                      </span>
                      <strong className="intervention-cost">{euros(item.cost_eur)}</strong>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      <button type="button" className="outline-button comparison-toggle" aria-expanded={props.compareOpen} aria-controls="comparison-settings" onClick={props.toggleCompare}>
        <ArrowDownUp size={17} aria-hidden="true" /> Σύγκριση προϋπολογισμών
      </button>
      {props.compareOpen && (
        <div className="comparison" id="comparison-settings">
          <form onSubmit={props.onCompare}>
            <div className="comparison-fields">
              <div><label htmlFor="baseline-budget">Αρχικός</label><div className="currency-input currency-input--small"><input id="baseline-budget" min="0" max="100000000" type="number" inputMode="decimal" step="0.01" required value={props.baseline} onChange={(event) => props.setBaseline(event.target.value)} /><span aria-hidden="true">€</span></div></div>
              <div><span>Τρέχων</span><strong>{budget === "" ? "—" : euros(Number(budget))}</strong></div>
            </div>
            <button type="submit" className="secondary-button" disabled={props.comparisonBusy || budget === ""}>{props.comparisonBusy ? "Σύγκριση…" : "Σύγκρινε τα πλάνα"}</button>
          </form>
          {props.comparisonError && <p className="notice notice--error" role="alert">{props.comparisonError}</p>}
          {comparison && (
            <div className="comparison-results" aria-live="polite">
              <ComparisonResults comparison={comparison} locations={locations} />
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

function ComparisonResults({ comparison, locations }: { comparison: Comparison; locations: Map<string, Location> }) {
  const selected = [...comparison.baseline.selected, ...comparison.proposed.selected]
  const label = (id: string) => {
    const item = selected.find((candidate) => candidate.id === id)
    if (!item) return id
    const name = locations.get(item.location_id)?.name
    return name ? `${name} · ${interventionLabel(item.type)}` : interventionLabel(item.type)
  }
  const groups = [
    { title: "Προστίθενται", ids: comparison.added_ids, icon: <Plus size={15} /> },
    { title: "Αφαιρούνται", ids: comparison.removed_ids, icon: <Minus size={15} /> },
    { title: "Διατηρούνται", ids: comparison.retained_ids, icon: <CheckCircle2 size={15} /> },
  ]
  return (
    <>
      <div className="comparison-spend">
        {[{ label: "Αρχικό", plan: comparison.baseline }, { label: "Νέο", plan: comparison.proposed }].map(({ label, plan }) => (
          <div key={label}>
            <span>{label} · {euros(plan.budget_eur)}<strong>Θέσεις · {plan.selected.length}</strong></span>
          </div>
        ))}
      </div>
      <ImpactComparison baseline={comparison.baseline} proposed={comparison.proposed} />
      {comparison.proposed.include_inspection && <p className="notice notice--inspection">Και τα δύο πλάνα συμπεριλαμβάνουν θέσεις προς αυτοψία.</p>}
      <ul className="comparison-changes">
        {groups.map((group) => (
          <li key={group.title}>{group.icon}<div><strong>{group.title} · {group.ids.length}</strong>{group.ids.map((id) => <span key={id}>{label(id)}</span>)}</div></li>
        ))}
      </ul>
    </>
  )
}
