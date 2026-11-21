import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis import AthensAnalysis
from app.main import create_app
from app.models import Dataset, OptimizeRequest
from app.optimizer import optimize


@pytest.fixture
def data() -> dict:
    def location(
        location_id: str, heat: float | None, canopy: float | None, shade: str,
    ) -> dict:
        return {
            "id": location_id,
            "name": location_id,
            "district": "Test district",
            "latitude": 38,
            "longitude": 23.7,
            "heat_c": heat,
            "canopy_percent": canopy,
            "shade_status": shade,
            "source_ids": ["test-heat"],
            "plantings_count": None,
        }

    def intervention(
        intervention_id: str,
        location_id: str,
        cost: int,
        benefit: float,
        feasibility: str = "verified",
    ) -> dict:
        return {
            "id": intervention_id,
            "location_id": location_id,
            "type": "tree_planting",
            "cost_eur": cost,
            "modeled_benefit": benefit,
            "feasibility": feasibility,
            "cost_source_id": "test-cost",
            "cost_status": "indicative",
            "rationale": "Synthetic test fixture",
        }

    fixture = {
        "dataset_version": "test-v1",
        "sources": [
            {"id": "test-heat", "title": "Test Heat", "url": "https://example.org/heat", "period": "Test", "kind": "test"},
            {"id": "test-cost", "title": "Test Cost", "url": "https://example.org/cost", "period": "Test", "kind": "test"},
        ],
        "heat": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [23.7, 38]},
                    "properties": {"temperature_c": value, "source_id": "test-heat"},
                }
                for value in [25, 30, 35, 40, 45]
            ],
        },
        "locations": [
            location("hot-a", 45, 5, "unknown"),
            location("hot-b", 41, None, "deficit"),
            location("unknown", 45, None, "unknown"),
            location("cool", 31, 2, "deficit"),
            location("missing", None, None, "unknown"),
        ],
        "interventions": [
            intervention("tree-a", "hot-a", 42_000, 15),
            intervention("shade-a", "hot-a", 48_000, 20),
            intervention("tree-b", "hot-b", 43_000, 18, "requires_site_inspection"),
            intervention("unsafe-b", "hot-b", 1, 500, "unsuitable"),
            intervention("unknown-option", "unknown", 25_000, 50),
            intervention("cool-option", "cool", 25_000, 99),
        ],
    }
    fixture["interventions"][1].update(
        type="shade_structure",
        shade_projection={
            "unit_count": 3,
            "unit_projection_min_m2": 12,
            "unit_projection_max_m2": 15,
            "horizon": "after_installation",
            "assumption": "Hypothetical test structures",
        },
    )
    fixture["interventions"][2]["shade_projection"] = {
        "unit_count": 4,
        "unit_projection_min_m2": 8,
        "unit_projection_max_m2": 12.5,
        "horizon": "at_tree_maturity",
        "assumption": "Hypothetical adult test trees",
    }
    return fixture


def app_for(data: dict, tmp_path: Path) -> TestClient:
    dataset = tmp_path / "athens.json"
    dataset.write_text(json.dumps(data), encoding="utf-8")
    return TestClient(create_app(dataset_path=dataset))


@pytest.fixture
def client(data: dict, tmp_path: Path) -> TestClient:
    return app_for(data, tmp_path)


def test_public_data_preserves_sources_and_unknowns(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "dataset_version": "test-v1"}
    response = client.get("/api/locations").json()
    by_id = {item["id"]: item for item in response["locations"]}
    assert response["heat_hotspot_threshold_c"] == 40
    assert response["tree_deficit_threshold_percent"] == 15
    assert by_id["hot-a"]["priority_band"] == by_id["hot-b"]["priority_band"] == "high"
    assert by_id["hot-a"]["tree_deficit"] is True
    assert by_id["hot-b"]["shade_deficit"] is True
    assert by_id["unknown"]["priority_band"] == "unknown"
    assert by_id["unknown"]["canopy_percent"] is None
    assert by_id["unknown"]["tree_deficit"] is None
    assert by_id["unknown"]["shade_deficit"] is None
    assert by_id["missing"]["priority_score"] is None
    assert by_id["cool"]["priority_band"] == "standard"
    assert client.get("/api/layers/heat").json()["features"][0]["properties"]["source_id"] == "test-heat"
    assert client.get("/api/layers/trees").json() == {"type": "FeatureCollection", "features": []}
    assert client.get("/api/layers/context").json() == {"type": "FeatureCollection", "features": []}
    assert client.get("/api/data-sources").json()["sources"][0]["url"] == "https://example.org/heat"


def test_location_explanation_includes_feasibility_and_does_not_claim_verified_cost(client: TestClient) -> None:
    response = client.get("/api/locations/hot-b/analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["location"]["priority_band"] == "high"
    assert "τεκμηριωμένη έλλειψη σκίασης" in data["explanation"]
    proposed = data["interventions"][0]
    assert proposed["feasibility"] == "requires_site_inspection"
    assert proposed["cost_status"] == "indicative"
    assert "αυτοψία" in proposed["explanation"]
    assert client.get("/api/locations/missing-id/analysis").status_code == 404


def test_optimizer_prioritizes_hot_deficit_before_modeled_benefit(client: TestClient) -> None:
    response = client.post("/api/optimize", json={"budget_eur": 50_000})
    assert response.status_code == 200
    plan = response.json()
    assert plan["status"] == "optimal"
    assert plan["priority_site_count"] == 1
    assert plan["total_cost_eur"] == 48_000
    assert plan["remaining_budget_eur"] == 2_000
    assert [row["id"] for row in plan["selected"]] == ["shade-a"]


def test_budget_and_inspection_comparison(client: TestClient) -> None:
    response = client.post(
        "/api/scenarios/compare",
        json={
            "baseline": {"budget_eur": 100_000},
            "proposed": {"budget_eur": 100_000, "include_inspection": True},
        },
    )
    assert response.status_code == 200
    compare = response.json()
    assert compare["baseline"]["total_cost_eur"] == 98_000
    assert compare["baseline"]["priority_site_count"] == 1
    assert compare["proposed"]["total_cost_eur"] == 91_000
    assert compare["proposed"]["priority_site_count"] == 2
    assert compare["added_ids"] == ["tree-b"]
    assert compare["removed_ids"] == ["cool-option", "unknown-option"]
    assert compare["retained_ids"] == ["shade-a"]


@pytest.mark.parametrize("entry", [-1, 100_000_001, 15.001, "NaN", "Infinity"])
def test_invalid_budgets_are_rejected(client: TestClient, entry: int | float | str) -> None:
    assert client.post("/api/optimize", json={"budget_eur": entry}).status_code == 422


def test_unaffordable_plan_uses_exact_cent_amount(client: TestClient) -> None:
    plan = client.post("/api/optimize", json={"budget_eur": "24999.99"}).json()
    assert plan["status"] == "no_affordable_interventions"
    assert plan["selected"] == []
    assert plan["remaining_budget_eur"] == 24_999.99


def test_only_verified_options_are_used_without_opt_in(data: dict, tmp_path: Path) -> None:
    data["interventions"] = [
        option for option in data["interventions"] if option["feasibility"] != "verified"
    ]
    client = app_for(data, tmp_path)
    default_plan = client.post("/api/optimize", json={"budget_eur": 100_000}).json()
    assert default_plan["status"] == "no_eligible_interventions"
    opt_in_plan = client.post(
        "/api/optimize", json={"budget_eur": 100_000, "include_inspection": True},
    ).json()
    assert [row["id"] for row in opt_in_plan["selected"]] == ["tree-b"]


def test_missing_bundle_exposes_unavailable_status(tmp_path: Path) -> None:
    client = TestClient(create_app(dataset_path=tmp_path / "missing.json"))
    assert client.get("/health").json()["status"] == "dataset_unavailable"
    assert client.get("/api/locations").status_code == 503


def test_shade_footprints_remain_separate_by_horizon(data: dict) -> None:
    analysis = AthensAnalysis(Dataset.model_validate(data))
    plan = optimize(analysis, OptimizeRequest(budget_eur=100_000, include_inspection=True))
    assert plan.shade_impact.model_dump() == {
        "after_installation": {"min_m2": 36, "max_m2": 45},
        "at_tree_maturity": {"min_m2": 32, "max_m2": 50},
        "unestimated_count": 0,
    }
    assert plan.selected[0].shade_impact.unit_count == 3
    assert plan.selected[1].shade_impact.assumption == "Hypothetical adult test trees"
    default_plan = optimize(analysis, OptimizeRequest(budget_eur=100_000))
    assert default_plan.shade_impact.unestimated_count == 2
    assert default_plan.shade_impact.at_tree_maturity.max_m2 == 0


def test_tree_cannot_claim_immediate_shade_projection(data: dict) -> None:
    data["interventions"][2]["shade_projection"]["horizon"] = "after_installation"
    with pytest.raises(ValidationError, match="Shade horizon does not match intervention type"):
        Dataset.model_validate(data)


def test_density_breaks_hotspot_ties_before_benefit(data: dict) -> None:
    data["sources"].append(
        {"id": "test-population", "title": "Sample density", "period": "Test", "kind": "test"}
    )
    for index, density in ((0, 6_000), (1, 12_000), (3, 24_000)):
        data["locations"][index].update(
            population_density_per_km2=density,
            population_source_id="test-population",
            population_grid_m=100,
        )
    data["interventions"][2]["modeled_benefit"] = 1
    analysis = AthensAnalysis(Dataset.model_validate(data))
    plan = optimize(analysis, OptimizeRequest(budget_eur=50_000, include_inspection=True))
    assert [row.id for row in plan.selected] == ["tree-b"]
    assert plan.priority_site_count == 1
    assert plan.population_exposure_proxy == 12_000
    assert plan.population_priority_sites_with_data == 1


def test_missing_density_keeps_legacy_plans_usable(data: dict) -> None:
    analysis = AthensAnalysis(Dataset.model_validate(data))
    assert analysis.locations["hot-a"].population_density_per_km2 is None
    plan = optimize(analysis, OptimizeRequest(budget_eur=50_000))
    assert [row.id for row in plan.selected] == ["shade-a"]
    assert plan.population_exposure_proxy == 0
    assert plan.population_priority_sites_with_data == 0


def test_green_roof_area_is_separate_from_street_shade(data: dict) -> None:
    data["interventions"][-1].update(type="green_roof", greened_roof_area_m2=105.5)
    analysis = AthensAnalysis(Dataset.model_validate(data))
    plan = optimize(analysis, OptimizeRequest(budget_eur=100_000))
    roof = next(row for row in plan.selected if row.type == "green_roof")
    assert roof.greened_roof_area_m2 == plan.greened_roof_area_m2 == 105.5
    assert roof.shade_impact is None
    assert plan.shade_impact.after_installation.max_m2 == 45


def test_immediate_shade_strategy_uses_lower_footprint_before_benefit(data: dict) -> None:
    data["interventions"][0]["modeled_benefit"] = 100
    analysis = AthensAnalysis(Dataset.model_validate(data))
    balanced = optimize(analysis, OptimizeRequest(budget_eur=50_000))
    immediate = optimize(analysis, OptimizeRequest(budget_eur=50_000, strategy="immediate_shade"))
    assert balanced.strategy == "balanced"
    assert [row.id for row in balanced.selected] == ["tree-a"]
    assert immediate.strategy == "immediate_shade"
    assert [row.id for row in immediate.selected] == ["shade-a"]
    assert immediate.priority_site_count == balanced.priority_site_count == 1
    assert immediate.shade_impact.after_installation.min_m2 == 36


def test_plan_reports_evidence_ranges_and_cost_per_matching_area(client: TestClient) -> None:
    response = client.post("/api/optimize", json={"budget_eur": 50_000})
    assert response.status_code == 200
    impact, = response.json()["thermal_impact"]
    assert impact["type"] == "shade_structure"
    assert (impact["area_min_m2"], impact["area_max_m2"]) == (36, 45)
    assert (impact["cost_per_m2_min_eur"], impact["cost_per_m2_max_eur"]) == (1066.67, 1333.33)
    assert (impact["cooling_min_c"], impact["cooling_max_c"]) == (9.2, 13.2)
    assert impact["evidence_url"].startswith("https://doi.org/")


def test_financial_appraisal_uses_selected_type_and_optional_municipal_quote(client: TestClient) -> None:
    request = {
        "scenario": {"budget_eur": 100_000, "include_inspection": True},
        "intervention_type": "shade_structure",
        "assumptions": {
            "annual_savings_eur": 9000, "annual_maintenance_eur": 2000,
            "horizon_years": 20, "discount_rate_pct": 3,
        },
    }
    result = client.post("/api/investment-appraisal", json=request)
    assert result.status_code == 200
    assert result.json()["capital_cost_eur"] == 48000

    request["assumptions"].update(capital_override_eur=53000, grant_eur=5000)
    override = client.post("/api/investment-appraisal", json=request)
    assert override.status_code == 200
    assert override.json()["capital_cost_eur"] == 53000
    assert override.json()["net_initial_cost_eur"] == 48000

    request["intervention_type"] = "green_roof"
    assert client.post("/api/investment-appraisal", json=request).status_code == 422


def test_city_brief_is_grounded_in_the_same_optimized_plan(data: dict, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with app_for(data, tmp_path) as client:
        response = client.post("/api/ai-brief", json={"budget_eur": 50_000})
        assert response.status_code == 200
        brief = response.json()
        assert brief["availability"] == "not_configured"
        assert brief["source"] == "verified_template"
        assert "48.000" in brief["summary"]
        assert brief["priorities"] and brief["next_step"] and brief["evidence"]
        assert client.post("/api/ai-brief", json={"budget_eur": 0}).status_code == 422
