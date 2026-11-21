"use client"

import { ArrowDownUp, CheckCircle2, CircleAlert, FileText, House, MapPin, Minus, Plus, ShieldCheck, TreeDeciduous } from "lucide-react"
import type { FormEvent } from "react"
import type { Comparison, Location, Plan } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, shadeArea } from "../lib/format"

type PlannerProps = {
  budget: string
  setBudget: (budget: string) => void
  includeInspection: boolean
  setIncludeInspection: (include: boolean) => void
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

const budgetPresets = [50_000, 100_000]

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
              <p className="notice notice--inspection"><CircleAlert size={17} /> Διερευνητικό πλάνο. Οι θέσεις προς αυτοψία χρειάζονται επιτόπια επιβεβαίωση.</p>
            ) : (
              <p className="verified-label"><ShieldCheck size={16} /> Επιβεβαιωμένες θέσεις</p>
            )}
            {plan.selected.length > 0 && Boolean(plan.shade_impact || plan.greened_roof_area_m2) && <ImpactCard plan={plan} />}
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

function ImpactCard({ plan }: { plan: Plan }) {
  const immediate = plan.shade_impact?.after_installation
  const maturity = plan.shade_impact?.at_tree_maturity
  const roof = plan.greened_roof_area_m2 ?? 0
  return (
    <section className="shade-impact" aria-label="Εκτίμηση σκίασης και πρασίνου">
      <strong>Εκτίμηση σκίασης και πρασίνου</strong>
      {immediate && maturity && (immediate.max_m2 > 0 || maturity.max_m2 > 0) && (
        <>
          <dl>
            <div><dt>Σκιά μετά την εγκατάσταση</dt><dd>{shadeArea(immediate.min_m2, immediate.max_m2)}</dd></div>
            <div><dt>Σκιά στην ωρίμανση των δέντρων</dt><dd>{shadeArea(maturity.min_m2, maturity.max_m2)}</dd></div>
          </dl>
          <p>Ενδεικτική επιφάνεια σκιάς πριν από επικαλύψεις. Η σκιά μειώνει την έκθεση στον άμεσο ήλιο.</p>
        </>
      )}
      {roof > 0 && <p className="roof-impact"><strong>{shadeArea(roof, roof)}</strong> ενδεικτικής φύτευσης σε δώματα. Η φύτευση περιορίζει την εκτεθειμένη επιφάνεια της στέγης.</p>}
      <p>Η επίδραση στο μικροκλίμα αξιολογείται με επιτόπιες μετρήσεις θερμοκρασίας αέρα και θερμικής άνεσης, πριν και μετά.</p>
      {!!plan.shade_impact?.unestimated_count && <p>Παρεμβάσεις χωρίς εκτίμηση άμεσης σκιάς · {plan.shade_impact.unestimated_count}</p>}
    </section>
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
        {[comparison.baseline, comparison.proposed].map((plan, index) => (
          <div key={index}>
            <span>{euros(plan.budget_eur)}<strong>{plan.selected.length} θέσεις</strong></span>
            {plan.shade_impact && plan.selected.length > 0 && (
              <ul className="comparison-impact">
                <li>{shadeArea(plan.shade_impact.after_installation.min_m2, plan.shade_impact.after_installation.max_m2)} εγκατάστασης</li>
                <li>{shadeArea(plan.shade_impact.at_tree_maturity.min_m2, plan.shade_impact.at_tree_maturity.max_m2)} ωρίμανσης</li>
              </ul>
            )}
            {!!plan.greened_roof_area_m2 && <p className="comparison-impact">{shadeArea(plan.greened_roof_area_m2, plan.greened_roof_area_m2)} φυτεμένων δωμάτων</p>}
          </div>
        ))}
      </div>
      {comparison.proposed.include_inspection && <p className="notice notice--inspection">Και τα δύο πλάνα συμπεριλαμβάνουν θέσεις προς αυτοψία.</p>}
      <ul className="comparison-changes">
        {groups.map((group) => (
          <li key={group.title}>{group.icon}<div><strong>{group.title} · {group.ids.length}</strong>{group.ids.map((id) => <span key={id}>{label(id)}</span>)}</div></li>
        ))}
      </ul>
    </>
  )
}
