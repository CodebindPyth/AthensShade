import json
from pathlib import Path

from app.siting import assess_siting, load_siting


def test_known_plaza_anchor_and_shelter_capacity() -> None:
    site = load_siting()["avdi"]
    assert site.geometry["type"] == "Polygon"
    assert site.source_url.host == "www.openstreetmap.org"
    assert site.available_area_m2 > 2_000
    assert site.road_distance_m >= 12
    assert assess_siting("avdi", "tree_planting").status == "candidate"
    assert assess_siting("avdi", "shade_structure", 220).status == "candidate"
    assert assess_siting("avdi", "shade_structure", site.available_area_m2).status == "insufficient_space"


def test_confirmed_underground_parking_requires_tree_root_space_study() -> None:
    planting = assess_siting("kotzia", "tree_planting")
    assert planting.status == "unverified"
    assert planting.evidence is not None
    assert planting.evidence.constraint_source_url is not None
    assert planting.evidence.constraint_source_url.host == "www.daem.gr"
    assert assess_siting("kotzia", "shade_structure", 420).status == "candidate"


def test_unverified_and_roadway_references_are_not_candidates(tmp_path: Path) -> None:
    assert assess_siting("kerameikos", "shade_structure", 400).status == "unverified"
    missing = tmp_path / "unknown.json"
    assert assess_siting("avdi", "tree_planting", snapshot_path=missing).status == "unverified"
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"roadway_reference_ids": ["x"]}), encoding="utf-8")
    assert assess_siting("x", "shade_structure", snapshot_path=blocked).status == "road_conflict"
