from decimal import Decimal
from itertools import combinations
from math import cos, hypot, radians

from fastapi.testclient import TestClient

from app.analysis import ATHENS_RED_SURFACE_TEMPERATURE_C
from app.main import DEFAULT_DATASET_PATH, create_app, load_dataset
from app.models import OptimizeRequest
from app.municipal_sites import _inside_ring, _point_feature
from app.optimizer import EAST_ATHENS_LONGITUDE, WEST_ATHENS_LONGITUDE, WESTERN_PLANTING_SITES, optimize


def test_ground_options_use_screened_geometry_and_respect_capacity():
    stat = DEFAULT_DATASET_PATH.stat()
    analysis = load_dataset(DEFAULT_DATASET_PATH, stat.st_mtime_ns, stat.st_size)
    request = {"include_inspection": True, "priority_only": True, "strategy": "balanced"}
    basic = optimize(analysis, OptimizeRequest(budget_eur=20_000, **request))
    plan = optimize(analysis, OptimizeRequest(budget_eur=200_000, **request))
    assert plan.total_cost_eur <= plan.budget_eur
    assert len({item.location_id for item in plan.selected}) == len(plan.selected)
    assert len(plan.selected) > len(basic.selected)
    assert {"tree_planting", "shade_structure"} <= {item.type for item in plan.selected}
    assert any(item.type == "tree_planting" and item.siting["evidence"]["longitude"] >= EAST_ATHENS_LONGITUDE for item in plan.selected)
    assert sum(item.shade_impact.unit_count for item in plan.selected if item.type == "tree_planting") > sum(
        item.shade_impact.unit_count for item in basic.selected if item.type == "tree_planting"
    )
    assert analysis.hotspot_threshold == ATHENS_RED_SURFACE_TEMPERATURE_C
    for item in plan.selected:
        if item.type not in {"tree_planting", "shade_structure"}:
            continue
        assert item.feasibility == "requires_site_inspection"
        assert item.siting["status"] == "candidate"
        evidence = item.siting["evidence"]
        assert evidence["geometry"]["type"] == "Polygon"
        assert evidence["road_distance_m"] > 6
        assert evidence["mapped_space"]
        outer_ring, *holes = evidence["geometry"]["coordinates"]
        anchors = item.siting["anchors"]
        assert len(anchors) == item.shade_impact.unit_count
        for anchor in anchors:
            longitude, latitude = anchor["longitude"], anchor["latitude"]
            assert _inside_ring(outer_ring, longitude, latitude)
            assert not any(_inside_ring(hole, longitude, latitude) for hole in holes)
            heat = _point_feature(analysis.dataset.heat.features, longitude, latitude)
            assert heat and heat.properties["temperature_c"] >= analysis.hotspot_threshold
        for first, second in combinations(anchors, 2):
            delta_x = (first["longitude"] - second["longitude"]) * cos(radians(first["latitude"]))
            delta_y = first["latitude"] - second["latitude"]
            assert hypot(delta_x, delta_y) * 111_195 >= 4.98
    kotzia = analysis.location_analysis("kotzia")
    tree = next(item for item in kotzia.interventions if item.type == "tree_planting")
    assert tree.feasibility == "unsuitable"
    assert tree.siting["evidence"]["constraint_source_url"].startswith("https://www.daem.gr/")


def test_ground_plan_separates_installation_from_site_works_allowance():
    stat = DEFAULT_DATASET_PATH.stat()
    analysis = load_dataset(DEFAULT_DATASET_PATH, stat.st_mtime_ns, stat.st_size)
    plan = optimize(analysis, OptimizeRequest(
        budget_eur=100_000, include_inspection=True, priority_only=True, strategy="balanced",
    ))
    installation = sum(Decimal(str(item.cost_eur)) for item in plan.selected)
    remaining = Decimal(str(plan.remaining_budget_eur))

    assert installation == Decimal(str(plan.total_cost_eur))
    assert installation + remaining == Decimal("100000.00")
    assert Decimal("0") < Decimal(str(plan.site_works_allowance_eur)) <= remaining
    assert sum(item.shade_impact.unit_count for item in plan.selected if item.type == "tree_planting") == 47
    assert sum(item.shade_impact.unit_count for item in plan.selected if item.type == "shade_structure") == 1


def test_municipal_advice_is_grounded_in_registered_heat_site(monkeypatch):
    monkeypatch.setenv("ATHENSSHADE_LOCAL_ENGINE", "disabled")
    with TestClient(create_app(DEFAULT_DATASET_PATH)) as client:
        locations = client.get("/api/locations").json()["locations"]
        site = next(row for row in locations if row["id"] == "municipal-school-63-lykeio")
        assert site["heat_hotspot"]
        response = client.get("/api/locations/municipal-school-63-lykeio/municipal-advice")
        assert response.status_code == 200
        assert response.json()["recommendation"] in site["municipal_asset"]["notes"]
        assert set(response.json()["studies"]) == {"tree_planting", "green_roof"}
        for kind in ("police", "fire", "hospital", "kep", "court"):
            public_site = next(row for row in locations if (row["municipal_asset"] or {}).get("kind") == kind)
            advice = client.get(f"/api/locations/{public_site['id']}/municipal-advice")
            assert advice.status_code == 200
            assert set(advice.json()["studies"]) == {"tree_planting", "green_roof"}
        assert client.get("/api/locations/avdi/municipal-advice").status_code == 404


def test_balanced_plan_combines_eastern_and_original_western_tree_sites():
    stat = DEFAULT_DATASET_PATH.stat()
    analysis = load_dataset(DEFAULT_DATASET_PATH, stat.st_mtime_ns, stat.st_size)
    plan = optimize(analysis, OptimizeRequest(
        budget_eur=150_000, include_inspection=True, priority_only=True, strategy="balanced",
    ))

    trees = [item for item in plan.selected if item.type == "tree_planting"]
    west = [item for item in trees if item.siting["evidence"]["longitude"] < WEST_ATHENS_LONGITUDE]
    east = [item for item in trees if item.siting["evidence"]["longitude"] >= EAST_ATHENS_LONGITUDE]

    assert plan.total_cost_eur <= plan.budget_eur
    assert WESTERN_PLANTING_SITES <= {item.location_id for item in west}
    assert {"siting-goudi-army-park", "siting-rigillis"} <= {item.location_id for item in east}
    assert len(east) >= 5
    assert sum(item.shade_impact.unit_count for item in east) >= 60
    assert sum(item.shade_impact.unit_count for item in west) >= 30
