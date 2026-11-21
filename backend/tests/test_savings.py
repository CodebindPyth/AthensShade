from fastapi.testclient import TestClient

from app.main import DEFAULT_DATASET_PATH, create_app
from app.models import ExplainedIntervention, ShadeImpact
from app.savings import calculate_savings


def demo_scenario(budget: int) -> dict:
    return {
        "budget_eur": budget,
        "strategy": "tree_priority",
        "include_inspection": True,
        "priority_only": True,
    }


def test_savings_scale_with_selected_interventions() -> None:
    trees = ExplainedIntervention.model_construct(
        id="trees", location_id="plaza", type="tree_planting", cost_eur=10_000,
        shade_impact=ShadeImpact(unit_count=10, estimated_min_m2=100, estimated_max_m2=180,
                                 horizon="at_tree_maturity", assumption="Example"),
    )
    shelter = trees.model_copy(update={
        "id": "shelter", "location_id": "square", "type": "shade_structure", "cost_eur": 20_000,
        "shade_impact": trees.shade_impact.model_copy(update={"unit_count": 1, "horizon": "after_installation"}),
    })
    roof = trees.model_copy(update={
        "id": "roof", "location_id": "school", "type": "green_roof", "cost_eur": 15_000,
        "shade_impact": None, "greened_roof_area_m2": 40,
    })
    plan = calculate_savings([trees, shelter, roof])
    assert plan.source == "hypothetical_scenario"
    assert [row.gross_annual_eur for row in plan.items] == [100, 4_800, 200]
    assert [row.net_annual_eur for row in plan.items] == [-100, 4_400, -100]
    assert (plan.gross_annual_eur, plan.annual_maintenance_eur, plan.net_annual_eur) == (5_100, 900, 4_200)
    assert "500 kWh" in plan.items[0].assumptions[0]
    assert "δημοτικό λογαριασμό" in plan.items[0].assumptions[0]
    unknown = calculate_savings([trees.model_copy(update={"shade_impact": None})])
    assert unknown.gross_annual_eur == 0 and unknown.net_annual_eur == -200


def test_savings_uses_same_site_figures_on_map_card(monkeypatch) -> None:
    monkeypatch.setenv("ATHENSSHADE_LOCAL_ENGINE", "disabled")
    with TestClient(create_app(DEFAULT_DATASET_PATH)) as client:
        scenario = demo_scenario(150_000)
        plan_response = client.post("/api/savings", json=scenario)
        assert plan_response.status_code == 200
        plan_savings = plan_response.json()
        assert len(plan_savings["items"]) >= 1
        for plan_item in plan_savings["items"][:3]:
            location_id = plan_item["location_id"]
            response = client.post(f"/api/locations/{location_id}/plan-card", json=scenario)
            assert response.status_code == 200
            card = response.json()["savings"]
            assert card["items"] == [plan_item]
            assert card["net_annual_eur"] == plan_item["net_annual_eur"]

        no_budget = client.post("/api/savings", json=demo_scenario(0))
        assert no_budget.status_code == 200
        assert no_budget.json() == {
            "source": "hypothetical_scenario",
            "gross_annual_eur": 0,
            "annual_maintenance_eur": 0,
            "net_annual_eur": 0,
            "items": [],
        }
