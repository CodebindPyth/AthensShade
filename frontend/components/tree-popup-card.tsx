import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { api } from "../lib/api"
import type { Intervention, Location, MunicipalAdvice, Plan, SiteCardResponse, Siting } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, numeric, shadeArea, shadeLabel, temperature } from "../lib/format"
import { civicAppearance } from "./intervention-symbol"
import styles from "./tree-popup-card.module.css"

type TreePopupCardProps = { location: Location; plan: Plan; showImpact: boolean }

export function TreePopupCard({ location, plan, showImpact }: TreePopupCardProps) {
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
        <span className={styles.budget}>Συνολικός προϋπολογισμός {euros(budget_eur)}</span>
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
            {item.siting && item.rationale.length > 0 && (
              <details className={styles.siting} open>
                <summary>Γιατί προτείνεται εδώ</summary>
                <ul>{(typeof item.rationale === "string" ? [item.rationale] : item.rationale).map((reason) => <li key={reason}>{reason}</li>)}</ul>
              </details>
            )}
            {item.siting && <SitingDetails siting={item.siting} />}
          </li>
          )
        })}
      </ul>
      <div className={styles.assessment} aria-live="polite">
        {brief ? <SiteAssessment brief={brief} /> : (
          <p className={styles.context}>{unavailable ? "Η εκτίμηση της θέσης δεν είναι διαθέσιμη αυτή τη στιγμή." : "Υπολογίζεται η εκτίμηση για αυτή τη θέση…"}</p>
        )}
      </div>
      {location.municipal_asset && <MunicipalOptions location={location} showImpact={showImpact} />}
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

function SitingDetails({ siting }: { siting: Siting }) {
  const evidence = siting.evidence
  return (
    <details className={styles.siting}>
      <summary>Χαρτογραφικός προέλεγχος θέσης</summary>
      <p>{siting.message}</p>
      {evidence && (
        <>
          <p>{numeric(evidence.available_area_m2)} m² χαρτογραφημένης επιφάνειας μετά τις ζώνες αποκλεισμού · {numeric(evidence.road_distance_m)} m από καταγεγραμμένο άξονα δρόμου.</p>
          <a href={evidence.source_url} target="_blank" rel="noreferrer">Γεωμετρία OpenStreetMap</a>
          {evidence.constraint_note && <p>{evidence.constraint_note}</p>}
          {evidence.constraint_source_url && (
            <a href={evidence.constraint_source_url} target="_blank" rel="noreferrer">Τεκμηρίωση περιορισμού</a>
          )}
        </>
      )}
      <p>Η αυτοψία ελέγχει τη διαθέσιμη ελεύθερη όδευση, τα δίκτυα και τη στήριξη.</p>
    </details>
  )
}

export function MunicipalPopupCard({ location, showImpact }: { location: Location; showImpact: boolean }) {
  const { agency, address, kind, advisory_only } = location.municipal_asset ?? {}
  const { label } = civicAppearance(kind)
  return (
    <section className={styles.card} aria-label={`${label} · ${location.name}`}>
      <header className={styles.header}>
        <span className={styles.budget}>{label} · κόκκινη ζώνη</span>
        <h3>{location.name}</h3>
        {address && <p className={styles.context}>{address}</p>}
        {agency && <p className={styles.context}>{agency}</p>}
        {location.heat_c !== null && <p className={styles.context}>{temperature(location.heat_c)} ιστορική θερμοκρασία επιφάνειας</p>}
        {advisory_only && <p className={styles.context}>Ενδεικτικές λύσεις προς συζήτηση με τον αρμόδιο φορέα.</p>}
      </header>
      <MunicipalOptions location={location} showImpact={showImpact} />
    </section>
  )
}

function MunicipalOptions({ location, showImpact }: { location: Location; showImpact: boolean }) {
  const [advice, setAdvice] = useState<MunicipalAdvice | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api.municipalAdvice(location.id, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setAdvice(result) })
      .catch(() => {})
    return () => controller.abort()
  }, [location.id])

  const asset = location.municipal_asset
  if (!asset) return null
  const first = advice?.recommendation ?? asset.notes[0]
  return (
    <section className={styles.municipal} aria-label="Λύσεις προς μελέτη για το κτίριο">
      <p className={styles.origin}>{advice?.source === "local_model" ? <><Sparkles size={13} aria-hidden="true" /> Πρόταση ελέγχου από τοπικό AI</> : "Λύσεις προς μελέτη"}</p>
      <p>{first}</p>
      {showImpact && <ul className={styles.buildingStudies} aria-label="Επιλογές προσαρμογής κτιρίου">
        <li><strong>Φύτευση δέντρων</strong><p>{advice?.studies?.tree_planting ?? "Μελέτη φύτευσης στον ελεύθερο χώρο του κτιρίου."}</p></li>
        <li><strong>Φυτεμένο δώμα</strong><p>{advice?.studies?.green_roof ?? "Έλεγχος διαθέσιμης επιφάνειας, φορτίων και στεγάνωσης."}</p></li>
      </ul>}
      <details className={styles.details}>
        <summary>Άλλες επιλογές και πηγή</summary>
        <ul>{asset.notes.filter((note) => note !== first).map((note) => <li key={note}>{note}</li>)}</ul>
        <a href={asset.source_url} target="_blank" rel="noreferrer">{asset.source_label}</a>
        {asset.coordinates_url && <a href={asset.coordinates_url} target="_blank" rel="noreferrer"> Χαρτογραφημένη θέση</a>}
      </details>
    </section>
  )
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
        <p className={styles.origin}>Εκτίμηση για τον Δήμο ανά έτος</p>
        {savings ? (
          <>
            <p className={styles.savingsFigure}>{euros(savings.gross_annual_eur)} δυνητική μείωση δαπανών</p>
            <p className={styles.context}>{euros(savings.annual_maintenance_eur)} πρόσθετη συντήρηση</p>
            <p className={styles.savingsFigure}>Καθαρό λειτουργικό αποτέλεσμα {savings.net_annual_eur > 0 ? "+" : ""}{euros(savings.net_annual_eur)}/έτος</p>
            {savings.items.some((item) => item.type === "tree_planting") && <p className={styles.context}>Στην ωρίμανση, εφόσον η κόμη σκιάζει κλιματιζόμενο δημοτικό κτίριο.</p>}
            <details className={styles.details}>
              <summary>Πώς προκύπτουν τα ποσά</summary>
              {Array.from(new Set(assumptions)).map((assumption) => <p key={assumption}>{assumption}</p>)}
            </details>
          </>
        ) : (
          <p className={styles.context}>Δεν υπάρχει διαθέσιμη εκτίμηση εξοικονόμησης.</p>
        )}
      </div>
    </>
  )
}
