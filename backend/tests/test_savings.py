from fastapi.testclient import TestClient

from app.main import DEFAULT_DATASET_PATH, create_app, load_dataset
from app.models import OptimizeRequest
from app.optimizer import optimize
from app.savings import calculate_savings


def demo_scenario(budget: int) -> dict:
    return {
        "budget_eur": budget,
        "strategy": "shade_and_rest",
        "include_inspection": True,
        "priority_only": True,
    }


def test_savings_scale_with_selected_interventions() -> None:
    stat = DEFAULT_DATASET_PATH.stat()
    analysis = load_dataset(DEFAULT_DATASET_PATH, stat.st_mtime_ns, stat.st_size)
    large_plan = optimize(analysis, OptimizeRequest(**demo_scenario(100_000)))
    small_plan = optimize(analysis, OptimizeRequest(**demo_scenario(50_000)))
    larger = calculate_savings(large_plan.selected)
    smaller = calculate_savings(small_plan.selected)

    assert larger.source == "hypothetical_scenario"
    assert larger.gross_annual_eur == 11_900
    assert larger.annual_maintenance_eur == 1_921.03
    assert larger.net_annual_eur == 9_978.97
    assert larger.net_annual_eur > smaller.net_annual_eur
    assert [row.intervention_id for row in larger.items] == [row.id for row in large_plan.selected]
    assert all(len(row.assumptions) == 2 for row in larger.items)

    tree = next(row for row in larger.items if row.type == "tree_planting")
    assert tree.gross_annual_eur == 0
    assert tree.net_annual_eur == -tree.annual_maintenance_eur
    assert "1.200 €" in tree.assumptions[0]
    assert "ώριμη κόμη" in tree.assumptions[0]


def test_savings_uses_same_site_figures_on_map_card(monkeypatch) -> None:
    monkeypatch.setenv("ATHENSSHADE_LOCAL_ENGINE", "disabled")
    with TestClient(create_app(DEFAULT_DATASET_PATH)) as client:
        scenario = demo_scenario(100_000)
        plan_response = client.post("/api/savings", json=scenario)
        assert plan_response.status_code == 200
        plan_savings = plan_response.json()
        for location_id in ("kotzia", "school-120", "avdi"):
            response = client.post(f"/api/locations/{location_id}/plan-card", json=scenario)
            assert response.status_code == 200
            card = response.json()["savings"]
            plan_item = next(row for row in plan_savings["items"] if row["location_id"] == location_id)
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
