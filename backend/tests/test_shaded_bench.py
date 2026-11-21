from pathlib import Path

from app.analysis import AthensAnalysis
from app.bench_scenarios import REFERENCE
from app.models import Dataset, OptimizeRequest
from app.optimizer import optimize


def test_shade_and_rest_plan_uses_verified_heat_and_reports_indicative_units() -> None:
    path = Path(__file__).resolve().parents[2] / "data" / "processed" / "athens.json"
    analysis = AthensAnalysis(Dataset.model_validate_json(path.read_bytes()))
    options = {"budget_eur": 100_000, "include_inspection": True, "priority_only": True}

    plan = optimize(analysis, OptimizeRequest(**options, strategy="shade_and_rest"))
    assert plan.status == "optimal"
    assert plan.total_cost_eur <= plan.budget_eur
    assert {item.type for item in plan.selected} >= {"tree_planting", "shade_structure", "shaded_bench", "green_roof"}
    assert all(item.priority_band == "high" for item in plan.selected)

    benches = [item for item in plan.selected if item.type == "shaded_bench"]
    assert sum(item.shade_impact.unit_count for item in benches if item.shade_impact) == 12
    assert all(item.feasibility == "requires_site_inspection" for item in benches)
    assert all(item.cost_source_id == REFERENCE.id and item.cost_status == "indicative" for item in benches)
    assert {item.location_id for item in benches} == {"kotzia", "kerameikos", "ramnes"}
    assert any(source.id == REFERENCE.id for source in analysis.dataset.sources)

    thermal = next(item for item in plan.thermal_impact if item.type == "shaded_bench")
    assert thermal.cooling_min_c is None and thermal.cooling_max_c is None

    baseline = optimize(analysis, OptimizeRequest(**options))
    assert all(item.type != "shaded_bench" for item in baseline.selected)
