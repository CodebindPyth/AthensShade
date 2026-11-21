from itertools import combinations
from math import cos, hypot, radians

from fastapi.testclient import TestClient

from app.analysis import ATHENS_RED_SURFACE_TEMPERATURE_C
from app.main import DEFAULT_DATASET_PATH, create_app, load_dataset
from app.models import OptimizeRequest
from app.municipal_sites import _inside_ring, _point_feature
from app.optimizer import optimize


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
