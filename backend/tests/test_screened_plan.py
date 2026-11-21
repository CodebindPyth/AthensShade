from fastapi.testclient import TestClient

from app.main import DEFAULT_DATASET_PATH, create_app, load_dataset
from app.models import OptimizeRequest
from app.optimizer import optimize


def test_ground_options_use_screened_geometry_and_respect_capacity():
    stat = DEFAULT_DATASET_PATH.stat()
    analysis = load_dataset(DEFAULT_DATASET_PATH, stat.st_mtime_ns, stat.st_size)
    plan = optimize(analysis, OptimizeRequest(
        budget_eur=150_000, include_inspection=True, priority_only=True, strategy="tree_priority",
    ))
    trees = [item for item in plan.selected if item.type == "tree_planting"]
    assert sum(item.shade_impact.unit_count for item in trees) == 86
    assert {item.location_id for item in trees} == {"avdi", "dourouti", "ramnes"}
    for item in plan.selected:
        if item.type == "green_roof":
            continue
        assert item.feasibility == "requires_site_inspection"
        assert item.siting["status"] == "candidate"
        assert item.siting["evidence"]["geometry"]["type"] == "Polygon"
        assert item.siting["evidence"]["road_distance_m"] > 6
    kotzia = analysis.location_analysis("kotzia")
    tree = next(item for item in kotzia.interventions if item.type == "tree_planting")
    assert tree.feasibility == "unsuitable"
    assert tree.siting["evidence"]["constraint_source_url"].startswith("https://www.daem.gr/")


def test_municipal_advice_is_grounded_in_registered_heat_site(monkeypatch):
    monkeypatch.setenv("ATHENSSHADE_LOCAL_ENGINE", "disabled")
    with TestClient(create_app(DEFAULT_DATASET_PATH)) as client:
        locations = client.get("/api/locations").json()["locations"]
        site = next(row for row in locations if row["id"] == "municipal-school-63-lykeio")
        assert site["heat_hotspot"]
        response = client.get("/api/locations/municipal-school-63-lykeio/municipal-advice")
        assert response.status_code == 200
        assert response.json()["recommendation"] in site["municipal_asset"]["notes"]
        assert client.get("/api/locations/avdi/municipal-advice").status_code == 404
