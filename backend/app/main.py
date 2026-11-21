import logging
import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from .ai_brief import BriefEditor, CityBrief
from .air import AIR_SOURCE, AirFeed, AirResponse
from .analysis import TREE_DEFICIT_THRESHOLD_PERCENT, AthensAnalysis
from .brief_evidence import build_brief_evidence
from .investment import AppraiseRequest, FinancialAppraisal, appraise_investment
from .methodology import methodology
from .models import (
    CompareRequest,
    CompareResponse,
    Dataset,
    GeoJSONCollection,
    HealthResponse,
    LocationAnalysis,
    LocationsResponse,
    MethodologyResponse,
    OptimizeRequest,
    Plan,
    SourcesResponse,
)
from .optimizer import OptimizationError, optimize
from .plan_card import LocalPlanCardEditor, MunicipalAdvice, PlanCard
from .savings import SavingsScenario, calculate_savings
from .semantic import ModelUnavailable, SemanticResult, keyword_search, semantic_search

DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "athens.json"
LOGGER = logging.getLogger(__name__)


class EvidenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class EvidenceSearchResponse(BaseModel):
    method: Literal["semantic", "keywords"]
    results: list[SemanticResult]


@lru_cache(maxsize=4)
def load_dataset(path: Path, modified_ns: int, size: int) -> AthensAnalysis:
    """Use the file signature so replacements are visible without restarting the API."""
    return AthensAnalysis(Dataset.model_validate_json(path.read_bytes()))


def create_app(dataset_path: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="AthensShade Optimizer",
        description="Athens heat and shade data with budget-constrained intervention scenarios.",
        version="0.1.0",
    )
    default_origins = "http://localhost:3000,http://127.0.0.1:3000"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.getenv("ATHENSSHADE_CORS_ORIGINS", default_origins).split(",")
            if origin.strip()
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    path = dataset_path or Path(os.getenv("ATHENSSHADE_DATA_PATH", str(DEFAULT_DATASET_PATH)))
    api = APIRouter(prefix="/api")
    air_feed = AirFeed()
    brief_editor = BriefEditor(os.getenv("GROQ_API_KEY"))
    card_editor = LocalPlanCardEditor()

    def dataset_analysis() -> AthensAnalysis:
        try:
            stat = path.stat()
            return load_dataset(path, stat.st_mtime_ns, stat.st_size)
        except OSError as exc:
            LOGGER.warning("Athens data file unavailable: %s", exc)
        except ValidationError as exc:
            LOGGER.error("Athens dataset failed validation (%s errors)", exc.error_count())
        raise HTTPException(status_code=503, detail="Το σύνολο δεδομένων δεν είναι διαθέσιμο.")

    @app.get("/health", include_in_schema=False)
    @api.get("/health", tags=["Status"])
    def health() -> HealthResponse:
        try:
            analysis = dataset_analysis()
        except HTTPException:
            return HealthResponse(status="dataset_unavailable", dataset_version=None)
        return HealthResponse(status="ok", dataset_version=analysis.dataset.dataset_version)

    @api.get("/locations", tags=["Locations"])
    def locations(analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)]) -> LocationsResponse:
        return LocationsResponse(
            dataset_version=analysis.dataset.dataset_version,
            heat_hotspot_threshold_c=analysis.hotspot_threshold,
            tree_deficit_threshold_percent=TREE_DEFICIT_THRESHOLD_PERCENT,
            locations=list(analysis.locations.values()),
        )

    @api.get("/locations/{location_id}/analysis", tags=["Locations"])
    def explain_location(
        location_id: str, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> LocationAnalysis:
        if location_id not in analysis.locations:
            raise HTTPException(status_code=404, detail="Το σημείο δεν βρέθηκε.")
        return analysis.location_analysis(location_id)

    @api.get("/locations/{location_id}/municipal-advice", tags=["Locations"])
    def municipal_advice(
        location_id: str, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> MunicipalAdvice:
        site = analysis.locations.get(location_id)
        notes = (site.municipal_asset or {}).get("notes") if site and site.heat_hotspot else None
        if site is None or not notes:
            raise HTTPException(status_code=404, detail="Δεν υπάρχει τεκμηριωμένη δημοτική θέση σε θερμή ζώνη.")
        return card_editor.advise_municipal_site(site, notes)

    @api.get("/layers/{layer}", tags=["Map"])
    def read_layer(
        layer: Literal["heat", "trees", "context"],
        analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> GeoJSONCollection:
        data = analysis.dataset
        layers = {"heat": data.heat, "trees": data.trees, "context": data.context}
        return layers[layer] or GeoJSONCollection()

    @api.get("/data-sources", tags=["Map"])
    def data_sources(analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)]) -> SourcesResponse:
        return SourcesResponse(dataset_version=analysis.dataset.dataset_version, sources=[*analysis.dataset.sources, AIR_SOURCE])

    @api.get("/air-observations", tags=["Map"])
    def air_observations() -> AirResponse:
        return air_feed.latest()

    @api.get("/methodology", tags=["Planning"])
    def planning_methodology() -> MethodologyResponse:
        return methodology()

    @api.post("/evidence-search", tags=["Map"])
    def evidence_search(request: EvidenceQuery) -> EvidenceSearchResponse:
        try:
            return EvidenceSearchResponse(method="semantic", results=semantic_search(request.query))
        except ModelUnavailable:
            return EvidenceSearchResponse(method="keywords", results=keyword_search(request.query))

    def get_plan(analysis: AthensAnalysis, request: OptimizeRequest) -> Plan:
        try:
            return optimize(analysis, request)
        except OptimizationError as exc:
            LOGGER.error("AthensShade optimization failed: %s", exc)
            raise HTTPException(status_code=503, detail="Η βελτιστοποίηση δεν είναι διαθέσιμη.") from exc

    @api.post("/optimize", tags=["Planning"])
    def plan(request: OptimizeRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)]) -> Plan:
        return get_plan(analysis, request)

    @api.post("/savings", tags=["Planning"])
    def annual_savings(
        request: OptimizeRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> SavingsScenario:
        return calculate_savings(get_plan(analysis, request).selected)

    @api.post("/locations/{location_id}/plan-card", tags=["Planning"])
    def plan_card(
        location_id: str, request: OptimizeRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> PlanCard:
        site = analysis.locations.get(location_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Το σημείο δεν βρέθηκε.")
        plan = get_plan(analysis, request)
        selected = [item for item in plan.selected if item.location_id == location_id]
        if not selected:
            raise HTTPException(status_code=422, detail="Η θέση δεν περιλαμβάνεται στο υπολογισμένο πλάνο.")
        return card_editor.build(site, selected, plan.strategy)

    @api.post("/ai-brief", tags=["Planning"])
    def city_brief(
        request: OptimizeRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> CityBrief:
        plan = get_plan(analysis, request)
        if not plan.selected:
            raise HTTPException(status_code=422, detail="Υπολόγισε πρώτα ένα πλάνο με παρεμβάσεις.")
        return brief_editor.edit(build_brief_evidence(plan, analysis), plan.strategy)

    @api.post("/investment-appraisal", tags=["Planning"])
    def investment_appraisal(
        request: AppraiseRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> FinancialAppraisal:
        plan = get_plan(analysis, request.scenario)
        selected = [item for item in plan.selected if request.intervention_type in (None, item.type)]
        if not selected:
            raise HTTPException(status_code=422, detail="Το πλάνο δεν περιλαμβάνει παρεμβάσεις για αυτή την αποτίμηση.")
        capital = sum((Decimal(str(item.cost_eur)) for item in selected), start=Decimal(0))
        try:
            return appraise_investment(capital, request.assumptions)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/scenarios/compare", tags=["Planning"])
    def compare(
        request: CompareRequest, analysis: Annotated[AthensAnalysis, Depends(dataset_analysis)],
    ) -> CompareResponse:
        baseline = get_plan(analysis, request.baseline)
        proposed = get_plan(analysis, request.proposed)
        baseline_ids = {item.id for item in baseline.selected}
        proposed_ids = {item.id for item in proposed.selected}
        return CompareResponse(
            baseline=baseline,
            proposed=proposed,
            added_ids=sorted(proposed_ids - baseline_ids),
            removed_ids=sorted(baseline_ids - proposed_ids),
            retained_ids=sorted(proposed_ids & baseline_ids),
        )

    app.include_router(api)
    return app


app = create_app()
