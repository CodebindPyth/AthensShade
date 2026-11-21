import type { FeatureCollection } from "geojson"

export type Location = {
  id: string
  name: string
  district: string | null
  latitude: number
  longitude: number
  heat_c: number | null
  canopy_percent: number | null
  shade_status: string
  source_ids: string[]
  plantings_count?: number | null
  planting_documented?: boolean | null
  planting_records_count?: number | null
  priority_score?: number | null
  priority_band?: string | null
  heat_hotspot?: boolean | null
  tree_deficit?: boolean | null
  shade_deficit?: boolean | null
  population_density_per_km2?: number | null
  population_source_id?: string | null
  population_grid_m?: number | null
}

export type Intervention = {
  id: string
  location_id: string
  type: string
  cost_eur: number
  feasibility: string
  cost_status: string
  cost_source_id?: string
  rationale: string | string[]
  explanation: string
  shade_impact?: {
    unit_count: number
    estimated_min_m2: number
    estimated_max_m2: number
    horizon: "after_installation" | "at_tree_maturity"
    assumption: string
  } | null
  greened_roof_area_m2?: number | null
}

export type Dataset = {
  dataset_version: string
  locations: Location[]
  heat_hotspot_threshold_c?: number | null
  tree_deficit_threshold_percent?: number
}
export type DataSource = { id: string; title: string; url: string | null; period: string | null; kind: string; license?: string | null }
export type DataSources = { dataset_version: string; sources: DataSource[] }
export type Analysis = { location: Location; interventions: Intervention[]; explanation: string }
export type Strategy = "balanced" | "immediate_shade"
export type Scenario = { budget_eur: number; include_inspection: boolean; strategy: Strategy }
export type ShadeRange = { min_m2: number; max_m2: number }
export type ShadeImpact = {
  after_installation: ShadeRange
  at_tree_maturity: ShadeRange
  unestimated_count: number
}
export type Plan = Scenario & {
  dataset_version: string
  total_cost_eur: number
  remaining_budget_eur: number
  modeled_benefit: number
  selected: Intervention[]
  status: string
  priority_site_count?: number
  shade_impact?: ShadeImpact
  greened_roof_area_m2?: number
}
export type Comparison = { baseline: Plan; proposed: Plan; added_ids: string[]; removed_ids: string[]; retained_ids: string[] }

export type LayerName = "heat" | "trees" | "context"
export type Layers = Record<LayerName, FeatureCollection>

export const api = {
  locations: (signal?: AbortSignal) => request<Dataset>("/locations", { signal }),
  sources: (signal?: AbortSignal) => request<DataSources>("/data-sources", { signal }),
  layer: (layer: LayerName, signal?: AbortSignal) => request<FeatureCollection>(`/layers/${layer}`, { signal }),
  analysis: (id: string, signal?: AbortSignal) => request<Analysis>(`/locations/${encodeURIComponent(id)}/analysis`, { signal }),
  optimize: (scenario: Scenario, signal?: AbortSignal) => post<Plan>("/optimize", scenario, signal),
  compare: (baseline: Scenario, proposed: Scenario) => post<Comparison>("/scenarios/compare", { baseline, proposed }),
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)
  if (!response.ok) {
    throw new Error(`Η υπηρεσία επέστρεψε κωδικό ${response.status}.`)
  }
  return response.json() as Promise<T>
}

function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  })
}
