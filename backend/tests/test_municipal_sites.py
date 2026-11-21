from pathlib import Path

from app.models import Dataset
from app.municipal_sites import add_municipal_sites


def test_municipal_premises_use_documented_hot_cells_without_adding_costed_works():
    root = Path(__file__).resolve().parents[2]
    dataset = Dataset.model_validate_json((root / "data/processed/athens.json").read_text(encoding="utf-8"))
    result = add_municipal_sites(dataset, 40.45)
    sites = {site.id: site for site in result.locations}

    for site_id, atlas_temperature in {
        "municipal-city-hall": 41.42,
        "municipal-serafeio": 40.70,
        "municipal-technopolis": 41.50,
        "municipal-school-63-lykeio": 42.33,
    }.items():
        site = sites[site_id]
        assert site.heat_c == atlas_temperature
        assert site.municipal_asset["temperature_scope"] == "atlas_cell"
        assert site.municipal_asset["source_url"].startswith("https://")
        assert site.shade_status == "unknown"
    assert sites["municipal-city-hall"].municipal_asset["heritage"]
    assert sites["municipal-school-63-lykeio"].municipal_asset["kind"] == "school"
    assert sites["school-120"].municipal_asset["temperature_scope"] == "existing_100m_estimate"
    assert result.interventions == dataset.interventions
    assert add_municipal_sites(result, 40.45) == result
