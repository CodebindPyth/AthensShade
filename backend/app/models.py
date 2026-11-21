from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, HttpUrl, model_validator

InterventionType = Literal["tree_planting", "shade_structure", "shaded_bench", "greenery", "green_roof"]
Feasibility = Literal["verified", "requires_site_inspection", "unsuitable"]
PriorityBand = Literal["high", "standard", "unknown"]
CostStatus = Literal["indicative", "verified"]
PlanStatus = Literal["optimal", "feasible", "no_eligible_interventions", "no_affordable_interventions"]
PlanStrategy = Literal["balanced", "immediate_shade", "shade_and_rest"]
ShadeHorizon = Literal["after_installation", "at_tree_maturity"]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
Budget = Annotated[Decimal, Field(ge=0, le=100_000_000, decimal_places=2)]
Cost = Annotated[Decimal, Field(gt=0, le=100_000_000, decimal_places=2)]


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    url: HttpUrl | None = None
    period: str
    kind: str
    license: str | None = None


class GeoJSONFeature(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["Feature"]
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class GeoJSONCollection(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature] = Field(default_factory=list)


class HeatProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    temperature_c: FiniteFloat
    source_id: str


class Location(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    district: str
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    heat_c: FiniteFloat | None
    canopy_percent: Percent | None
    shade_status: Literal["present", "deficit", "unknown"]
    source_ids: list[str]
    plantings_count: Annotated[int, Field(ge=0)] | None = None
    planting_records_count: Annotated[int, Field(ge=0)] | None = None
    planting_documented: bool | None = None
    population_density_per_km2: Annotated[FiniteFloat, Field(ge=0, le=10_000_000)] | None = None
    population_source_id: str | None = None
    population_grid_m: Annotated[int, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def verify_population_metadata(self) -> "Location":
        if self.population_density_per_km2 is not None and (
            not self.population_source_id or self.population_grid_m is None
        ):
            raise ValueError("A population density requires a source and grid resolution")
        return self


class RankedLocation(Location):
    priority_band: PriorityBand
    priority_score: int | None
    heat_hotspot: bool | None
    tree_deficit: bool | None
    shade_deficit: bool | None


class ShadeProjection(BaseModel):
    unit_count: Annotated[int, Field(ge=1, le=1_000_000)]
    unit_projection_min_m2: Annotated[FiniteFloat, Field(ge=0, le=1_000_000)]
    unit_projection_max_m2: Annotated[FiniteFloat, Field(ge=0, le=1_000_000)]
    horizon: ShadeHorizon
    assumption: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def verify_range(self) -> "ShadeProjection":
        if self.unit_projection_min_m2 > self.unit_projection_max_m2:
            raise ValueError("Minimum projection must not exceed maximum projection")
        return self


class Intervention(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    location_id: str
    type: InterventionType
    cost_eur: Cost
    modeled_benefit: Annotated[FiniteFloat, Field(ge=0, le=10_000)] | None = None
    feasibility: Feasibility
    cost_source_id: str
    cost_status: CostStatus
    rationale: str
    shade_projection: ShadeProjection | None = None
    greened_roof_area_m2: Annotated[FiniteFloat, Field(gt=0, le=1_000_000)] | None = None

    @model_validator(mode="after")
    def verify_impact_metadata(self) -> "Intervention":
        expected_horizon = {
            "tree_planting": "at_tree_maturity",
            "shade_structure": "after_installation",
            "shaded_bench": "after_installation",
        }
        if self.shade_projection and self.shade_projection.horizon != expected_horizon.get(self.type):
            raise ValueError(f"Shade horizon does not match intervention type {self.type}")
        if self.greened_roof_area_m2 is not None and self.type != "green_roof":
            raise ValueError("Greened roof area requires a green roof intervention")
        return self


class Dataset(BaseModel):
    dataset_version: str
    sources: list[Source]
    heat: GeoJSONCollection
    trees: GeoJSONCollection | None = None
    context: GeoJSONCollection | None = None
    locations: list[Location]
    interventions: list[Intervention]

    @model_validator(mode="after")
    def verify_references(self) -> "Dataset":
        for records in (self.sources, self.locations, self.interventions):
            if len({record.id for record in records}) != len(records):
                raise ValueError("Dataset contains duplicate IDs")

        source_ids = {source.id for source in self.sources}
        location_ids = {location.id for location in self.locations}
        for feature in self.heat.features:
            heat = HeatProperties.model_validate(feature.properties)
            if heat.source_id not in source_ids:
                raise ValueError("Heat feature references an unknown source")

        for location in self.locations:
            if set(location.source_ids) - source_ids:
                raise ValueError(f"Location {location.id} references an unknown source")
            if location.population_source_id is not None and location.population_source_id not in source_ids:
                raise ValueError(f"Location {location.id} references an unknown population source")

        for intervention in self.interventions:
            if intervention.location_id not in location_ids:
                raise ValueError(f"Intervention {intervention.id} references an unknown location")
            if intervention.cost_source_id not in source_ids:
                raise ValueError(f"Intervention {intervention.id} references an unknown source")
        return self


class HealthResponse(BaseModel):
    status: Literal["ok", "dataset_unavailable"]
    dataset_version: str | None


class LocationsResponse(BaseModel):
    dataset_version: str
    heat_hotspot_threshold_c: float | None
    tree_deficit_threshold_percent: float
    locations: list[RankedLocation]


class ShadeImpact(BaseModel):
    unit_count: int
    estimated_min_m2: float
    estimated_max_m2: float
    horizon: ShadeHorizon
    assumption: str


class ExplainedIntervention(BaseModel):
    id: str
    location_id: str
    type: InterventionType
    cost_eur: float
    modeled_benefit: float
    benefit_basis: Literal["supplied_model", "priority_heuristic"]
    feasibility: Feasibility
    cost_source_id: str
    cost_status: CostStatus
    rationale: str
    explanation: str
    priority_band: PriorityBand
    shade_impact: ShadeImpact | None
    greened_roof_area_m2: float | None


class FootprintRange(BaseModel):
    min_m2: float
    max_m2: float


class PlanShadeImpact(BaseModel):
    after_installation: FootprintRange
    at_tree_maturity: FootprintRange
    unestimated_count: int


class LocationAnalysis(BaseModel):
    location: RankedLocation
    interventions: list[ExplainedIntervention]
    explanation: str


class SourcesResponse(BaseModel):
    dataset_version: str
    sources: list[Source]


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_eur: Budget
    include_inspection: bool = False
    strategy: PlanStrategy = "balanced"
    priority_only: bool = False


class ThermalImpact(BaseModel):
    type: InterventionType
    area_min_m2: float | None
    area_max_m2: float | None
    installation_cost_eur: float
    cost_per_m2_min_eur: float | None
    cost_per_m2_max_eur: float | None
    cooling_min_c: float | None
    cooling_max_c: float | None
    metric: str
    evidence: str
    evidence_url: HttpUrl | None
    location_ids: list[str]


class Plan(BaseModel):
    dataset_version: str
    budget_eur: float
    total_cost_eur: float
    remaining_budget_eur: float
    modeled_benefit: float
    selected: list[ExplainedIntervention]
    status: PlanStatus
    include_inspection: bool
    strategy: PlanStrategy
    priority_only: bool = False
    priority_site_count: int
    shade_impact: PlanShadeImpact
    greened_roof_area_m2: float
    population_exposure_proxy: float
    population_priority_sites_with_data: int
    thermal_impact: list[ThermalImpact] = Field(default_factory=list)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: OptimizeRequest
    proposed: OptimizeRequest


class CompareResponse(BaseModel):
    baseline: Plan
    proposed: Plan
    added_ids: list[str]
    removed_ids: list[str]
    retained_ids: list[str]


class MethodologyIndicator(BaseModel):
    indicator: str
    unit: str
    method: str


class MonitoringStage(BaseModel):
    stage: str
    method: str


class MethodologyReference(BaseModel):
    title: str
    url: HttpUrl


class MethodologyResponse(BaseModel):
    priority_order: list[str]
    population_exposure_note: str
    outcomes: list[MethodologyIndicator]
    monitoring: list[MonitoringStage]
    references: list[MethodologyReference]
