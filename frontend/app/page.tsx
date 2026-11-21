"use client"

import dynamic from "next/dynamic"
import { ChevronRight, CircleAlert, Database, ExternalLink, MapPin, Sunrise, X } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import type { FormEvent } from "react"
import type { TileSelection } from "../components/city-map"
import { MicroclimateMonitor } from "../components/microclimate-monitor"
import { Planner } from "../components/planner"
import { api } from "../lib/api"
import type { Analysis, Comparison, DataSource, Dataset, Layers, Location, Plan } from "../lib/api"
import { euros, feasibilityLabel, interventionLabel, numeric, shadeArea, shadeLabel, temperature } from "../lib/format"

const CityMap = dynamic(() => import("../components/city-map"), {
  ssr: false,
  loading: () => <div className="map-frame map-loading" role="status">Φόρτωση χάρτη…</div>,
})

const defaultBudget = 100_000
const layerNames = ["heat", "trees", "context"] as const
const noLocations: Location[] = []
const noSources: DataSource[] = []

export default function AthensShade() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [sources, setSources] = useState<DataSource[]>(noSources)
  const [layers, setLayers] = useState<Partial<Layers>>({})
  const [dataError, setDataError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focusAnalysis, setFocusAnalysis] = useState(false)
  const [selectedTile, setSelectedTile] = useState<TileSelection | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysisErrorId, setAnalysisErrorId] = useState<string | null>(null)
  const [budget, setBudget] = useState(String(defaultBudget))
  const [baseline, setBaseline] = useState("50000")
  const [includeInspection, setIncludeInspection] = useState(false)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [busy, setBusy] = useState(true)
  const [planError, setPlanError] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [comparisonBusy, setComparisonBusy] = useState(false)
  const [comparisonError, setComparisonError] = useState<string | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const loadData = async () => {
      setDataError(null)
      const results = await Promise.allSettled([
        api.locations(signal),
        api.sources(signal),
        ...layerNames.map((name) => api.layer(name, signal)),
      ] as const)
      if (signal.aborted) return
      const [locationsResult, sourcesResult, ...layerResults] = results
      if (locationsResult.status === "fulfilled") setDataset(locationsResult.value)
      if (sourcesResult.status === "fulfilled") setSources(sourcesResult.value.sources)
      const available: Partial<Layers> = {}
      layerResults.forEach((result, index) => {
        if (result.status === "fulfilled") available[layerNames[index]] = result.value
      })
      setLayers((previous) => ({ ...previous, ...available }))
      if (results.some((result) => result.status === "rejected")) {
        setDataError("Ορισμένα δεδομένα του χάρτη δεν είναι διαθέσιμα.")
      }
    }
    void loadData()
    return () => controller.abort()
  }, [retryCount])

  useEffect(() => {
    const controller = new AbortController()
    api.optimize({ budget_eur: defaultBudget, include_inspection: false }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setPlan(result) })
      .catch(() => { if (!controller.signal.aborted) setPlanError("Δεν ήταν δυνατός ο υπολογισμός του πλάνου. Δοκίμασε ξανά.") })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    setAnalysisErrorId(null)
    api.analysis(selectedId, controller.signal)
      .then((details) => { if (!controller.signal.aborted) setAnalysis(details) })
      .catch(() => { if (!controller.signal.aborted) setAnalysisErrorId(selectedId) })
    return () => controller.abort()
  }, [selectedId])

  useEffect(() => {
    if (!focusAnalysis || !selectedId) return
    document.getElementById("site-analysis")?.focus()
    setFocusAnalysis(false)
  }, [focusAnalysis, selectedId])

  const locations = dataset?.locations ?? noLocations
  const locationById = useMemo(() => new Map(locations.map((location) => [location.id, location])), [locations])
  const sourceById = useMemo(() => new Map(sources.map((source) => [source.id, source])), [sources])
  const mapSource = sourceById.get(String(layers.heat?.features[0]?.properties?.source_id ?? ""))
  const selectedLocation = selectedId === null ? null : locationById.get(selectedId) ?? null
  const plannedIds = useMemo(() => plan?.selected.map((item) => item.location_id) ?? [], [plan])

  const onSelectLocation = useCallback((id: string) => {
    setSelectedTile(null)
    setSelectedId(id)
  }, [])

  const onSelectTile = useCallback((tile: TileSelection) => {
    setSelectedId(null)
    setSelectedTile(tile)
  }, [])

  const closeSelection = () => {
    setSelectedId(null)
    setSelectedTile(null)
    setAnalysis(null)
    setAnalysisErrorId(null)
  }

  const calculate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const amount = parseBudget(budget)
    if (amount === null) return
    setBusy(true)
    setPlanError(null)
    try {
      setPlan(await api.optimize({ budget_eur: amount, include_inspection: includeInspection }))
    } catch {
      setPlanError("Δεν ήταν δυνατός ο υπολογισμός του πλάνου. Δοκίμασε ξανά.")
    } finally {
      setBusy(false)
    }
  }

  const compare = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const initial = parseBudget(baseline)
    const current = parseBudget(budget)
    if (initial === null || current === null) {
      setComparisonError("Συμπλήρωσε έγκυρο ποσό και στους δύο προϋπολογισμούς.")
      return
    }
    setComparisonBusy(true)
    setComparisonError(null)
    try {
      setComparison(await api.compare(
        { budget_eur: initial, include_inspection: includeInspection },
        { budget_eur: current, include_inspection: includeInspection },
      ))
    } catch {
      setComparisonError("Δεν ήταν δυνατή η σύγκριση των πλάνων. Δοκίμασε ξανά.")
    } finally {
      setComparisonBusy(false)
    }
  }

  const currentAnalysis = analysis?.location.id === selectedId ? analysis : null
  const isStale = plan !== null && (parseBudget(budget) !== plan.budget_eur || includeInspection !== plan.include_inspection)
  const currentComparison = comparison?.baseline.budget_eur === parseBudget(baseline)
    && comparison.proposed.budget_eur === parseBudget(budget)
    && comparison.proposed.include_inspection === includeInspection ? comparison : null

  return (
    <>
      <a className="skip-link" href="#main">Μετάβαση στο περιεχόμενο</a>
      <header className="header">
        <div className="header-inner">
          <a className="brand" href="#" aria-label="AthensShade, αρχική">
            <span className="brand-symbol" aria-hidden="true"><Sunrise size={43} strokeWidth={1.8} /><i /></span>
            <strong>AthensShade</strong>
          </a>
          <span className="header-description">Χάρτης και παρεμβάσεις</span>
          <a className="header-sources" href="#sources"><Database size={16} /> Πηγές δεδομένων</a>
        </div>
      </header>
      <main className="workspace" id="main">
        <div className="page-heading">
          <h1>Σκίαση της Αθήνας</h1>
          <span>Θερμοκρασία επιφάνειας</span>
        </div>
        {dataError && <p className="data-notice" role="alert"><CircleAlert size={17} /> {dataError} <button type="button" onClick={() => setRetryCount((count) => count + 1)}>Δοκίμασε ξανά</button></p>}
        <div className="workspace-grid">
          <section className="map-column" aria-label="Χάρτης θερμοκρασίας επιφάνειας και θέσεων">
            <div className="map-shell">
              <CityMap
                {...layers}
                locations={locations}
                selectedId={selectedId}
                plannedIds={plannedIds}
                hotspotThreshold={dataset?.heat_hotspot_threshold_c}
                onSelectLocation={onSelectLocation}
                onSelectTile={onSelectTile}
              />
              {(selectedLocation || selectedTile) && (
                <div className="map-selection" role="status">
                  <button className="selection-close" type="button" aria-label="Κλείσιμο πληροφοριών σημείου" onClick={closeSelection}><X size={17} /></button>
                  {selectedLocation ? (
                    <>
                      <span>{selectedLocation.district || "Υποψήφια θέση"}</span>
                      <strong>{selectedLocation.name}</strong>
                      <p>{selectedLocation.heat_c === null ? "Θερμοκρασία άγνωστη" : temperature(selectedLocation.heat_c)} · {shadeLabel(selectedLocation.shade_status)}</p>
                      <a href="#site-analysis">Λεπτομέρειες θέσης <ChevronRight size={15} /></a>
                    </>
                  ) : selectedTile && (
                    <>
                      <span>{selectedTile.name ?? "Θερμοκρασία επιφάνειας"}</span>
                      <strong>{selectedTile.temperature === null ? "Άγνωστη" : temperature(selectedTile.temperature)}</strong>
                      {selectedTile.sourceId && sourceById.get(selectedTile.sourceId)?.period && <p>{sourceById.get(selectedTile.sourceId)?.period}</p>}
                    </>
                  )}
                </div>
              )}
            </div>
            <p className="map-caption">
              {mapSource ? <><strong>Θερμικό επίπεδο</strong> · {mapSource.title}{mapSource.period && ` · ${mapSource.period}`} · </> : null}
              Θερμοκρασία επιφάνειας για την περίοδο της πηγής.
            </p>
            {locations.length > 0 && (
              <div className="location-picker">
                <MapPin size={17} aria-hidden="true" />
                <label htmlFor="location-picker">Υποψήφιες θέσεις</label>
                <select id="location-picker" value={selectedId ?? ""} onChange={(event) => event.target.value ? onSelectLocation(event.target.value) : closeSelection()}>
                  <option value="">Επίλεξε σημείο</option>
                  {locations.map((location) => <option value={location.id} key={location.id}>{location.name}{location.priority_band === "high" ? " · Υψηλή προτεραιότητα" : ""}</option>)}
                </select>
              </div>
            )}
          </section>
          <Planner
            budget={budget} setBudget={setBudget} includeInspection={includeInspection}
            setIncludeInspection={setIncludeInspection} busy={busy} comparisonBusy={comparisonBusy}
            error={planError} comparisonError={comparisonError} plan={plan} comparison={currentComparison}
            isStale={isStale} compareOpen={compareOpen} toggleCompare={() => setCompareOpen(!compareOpen)}
            baseline={baseline} setBaseline={setBaseline} locations={locationById}
            onSelectLocation={(id) => { onSelectLocation(id); setFocusAnalysis(true) }}
            onCalculate={calculate} onCompare={compare}
          />
        </div>
        {selectedLocation && (
          <SiteDetails
            location={selectedLocation}
            analysis={currentAnalysis}
            failed={analysisErrorId === selectedId}
            sourceById={sourceById}
            heatThreshold={dataset?.heat_hotspot_threshold_c}
            treeThreshold={dataset?.tree_deficit_threshold_percent}
          />
        )}
        <MicroclimateMonitor />
        <section className="panel sources" id="sources" aria-labelledby="sources-title">
          <div className="sources-heading"><h2 id="sources-title">Πηγές δεδομένων</h2>{dataset && <small>{dataset.dataset_version}</small>}</div>
          {sources.length > 0 ? (
            <ul>
              {sources.map((source) => (
                <li key={source.id}>
                  <SourceTitle source={source} />
                  <p>{[source.period, source.license].filter(Boolean).join(" · ")}</p>
                </li>
              ))}
            </ul>
          ) : <p className="muted">Οι πηγές εμφανίζονται μόλις φορτωθούν τα δεδομένα.</p>}
        </section>
      </main>
    </>
  )
}

function SourceTitle({ source }: { source: DataSource }) {
  const href = source.url
  if (!href || !/^https?:\/\//i.test(href)) return <span>{source.title}</span>
  return <a href={href} target="_blank" rel="noreferrer">{source.title}<ExternalLink size={13} aria-hidden="true" /></a>
}

function parseBudget(value: string) {
  const amount = Number(value)
  if (value === "" || !Number.isFinite(amount) || amount < 0 || amount > 100_000_000) return null
  const cents = Math.round(amount * 100)
  return Math.abs(cents / 100 - amount) < 1e-10 ? cents / 100 : null
}

function SiteDetails({ location, analysis, failed, sourceById, heatThreshold, treeThreshold }: {
  location: Location
  analysis: Analysis | null
  failed: boolean
  sourceById: Map<string, DataSource>
  heatThreshold?: number | null
  treeThreshold?: number
}) {
  const dataSourceIds = new Set([...location.source_ids, ...(location.population_source_id ? [location.population_source_id] : [])])
  const dataSources = [...dataSourceIds].flatMap((id) => sourceById.get(id) ?? [])
  const heatText = location.heat_c === null ? "Άγνωστη" : temperature(location.heat_c)
  const treeText = location.canopy_percent === null ? "Άγνωστη" : `${numeric(location.canopy_percent)}%`
  return (
    <section className="panel site-details" id="site-analysis" aria-labelledby="site-title" tabIndex={-1}>
      <div className="detail-heading">
        <div><span>{location.district || "Υποψήφια θέση"}</span><h2 id="site-title">{location.name}</h2></div>
        {location.priority_band === "high" && <span className="priority">Υψηλή προτεραιότητα</span>}
        {location.priority_band === "unknown" && <span className="priority priority--neutral">Εκκρεμεί αξιολόγηση</span>}
      </div>
      <dl className="site-metrics">
        <div><dt>Θερμοκρασία επιφάνειας</dt><dd>{heatText}</dd></div>
        <div><dt>Δενδροκάλυψη</dt><dd>{treeText}</dd></div>
        <div>
          <dt>Καταγραφές φύτευσης σε ακτίνα 100 m</dt>
          <dd>{location.planting_records_count == null ? location.planting_documented ? "Υπάρχει τεκμηρίωση" : "Άγνωστες" : numeric(location.planting_records_count)}</dd>
          <small>{location.plantings_count == null ? "Πλήθος δέντρων άγνωστο" : `${numeric(location.plantings_count)} τεκμηριωμένα δέντρα`}</small>
        </div>
        <div><dt>Σκίαση</dt><dd>{shadeLabel(location.shade_status)}</dd></div>
        <div>
          <dt>Πληθυσμιακή πυκνότητα</dt>
          <dd>{location.population_density_per_km2 == null ? "Άγνωστη" : `${numeric(location.population_density_per_km2)} κάτ./km²`}</dd>
          {location.population_grid_m != null && <small>Κελί πληθυσμιακού πλέγματος {numeric(location.population_grid_m)} m</small>}
        </div>
      </dl>
      {analysis ? <p>{analysis.explanation}</p> : failed ? <p role="alert">Δεν ήταν δυνατή η φόρτωση της ανάλυσης.</p> : <p role="status">Φόρτωση ανάλυσης…</p>}
      {heatThreshold != null && treeThreshold != null && <p className="muted">Όριο θερμής ζώνης {temperature(heatThreshold)} · Όριο χαμηλής δενδροκάλυψης {numeric(treeThreshold)}%</p>}
      {analysis && analysis.interventions.length > 0 && (
        <ul className="detail-interventions">
          {analysis.interventions.map((item) => (
            <li key={item.id}>
              <div><strong>{interventionLabel(item.type)}</strong><span>{euros(item.cost_eur)} · {item.cost_status === "verified" ? "Τεκμηριωμένο κόστος" : "Ενδεικτικό κόστος"}</span></div>
              <small className={item.feasibility === "verified" ? "verified-text" : "inspection-text"}>{feasibilityLabel(item.feasibility)}</small>
              <p>{Array.isArray(item.rationale) ? item.rationale.join(" ") : item.rationale}</p>
              {item.shade_impact && (
                <>
                  <p><strong>{shadeArea(item.shade_impact.estimated_min_m2, item.shade_impact.estimated_max_m2)}</strong> δυνητικής σκιάς {item.shade_impact.horizon === "after_installation" ? "μετά την εγκατάσταση" : "στην ωρίμανση των δέντρων"}.</p>
                  <p className="impact-assumption">{item.shade_impact.assumption}</p>
                </>
              )}
              {item.greened_roof_area_m2 != null && <p><strong>{shadeArea(item.greened_roof_area_m2, item.greened_roof_area_m2)}</strong> ενδεικτικής φύτευσης στο δώμα. Η φέρουσα ικανότητα και η πρόσβαση ελέγχονται κατά την αυτοψία.</p>}
              {item.cost_source_id && sourceById.has(item.cost_source_id) && <SourceTitle source={sourceById.get(item.cost_source_id)!} />}
            </li>
          ))}
        </ul>
      )}
      {analysis?.interventions.length === 0 && <p className="muted">Δεν έχουν οριστεί υποψήφιες παρεμβάσεις για τη θέση.</p>}
      {dataSources.length > 0 && <ul className="detail-sources">{dataSources.map((source) => <li key={source.id}><SourceTitle source={source} /></li>)}</ul>}
    </section>
  )
}
