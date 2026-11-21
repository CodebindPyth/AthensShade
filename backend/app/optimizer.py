from collections import defaultdict
from decimal import Decimal

from ortools.sat.python import cp_model

from .analysis import AthensAnalysis
from .models import (
    ExplainedIntervention,
    FootprintRange,
    OptimizeRequest,
    Plan,
    PlanShadeImpact,
    PlanStatus,
    PlanStrategy,
    ShadeHorizon,
)
from .thermal import project_thermal_impact


class OptimizationError(Exception):
    """The solver could not produce a usable plan."""


def optimize(analysis: AthensAnalysis, request: OptimizeRequest) -> Plan:
    eligible = {"verified"}
    if request.include_inspection:
        eligible.add("requires_site_inspection")

    candidates = sorted(
        (
            row for row in analysis.dataset.interventions
            if row.feasibility in eligible
            and (not request.priority_only or analysis.locations[row.location_id].priority_band == "high")
        ),
        key=lambda row: row.id,
    )
    affordable = [row for row in candidates if row.cost_eur <= request.budget_eur]
    status: PlanStatus
    picks: list[ExplainedIntervention] = []
    total_cost = Decimal()
    selected_densities: list[float] = []

    if not candidates:
        status = "no_eligible_interventions"
    elif not affordable:
        status = "no_affordable_interventions"
    else:
        costs = [int(row.cost_eur * 100) for row in affordable]
        options = [analysis.explain_intervention(row) for row in affordable]
        densities = [
            analysis.locations[option.location_id].population_density_per_km2
            if option.priority_band == "high"
            else None
            for option in options
        ]
        selected_indices, status = solve(
            options, costs, densities, int(request.budget_eur * 100), request.strategy,
        )
        selected_indices.sort(key=lambda index: (
            options[index].priority_band != "high",
            -(densities[index] or 0),
            -options[index].modeled_benefit,
            options[index].id,
        ))
        picks = [options[index] for index in selected_indices]
        total_cost = sum((affordable[index].cost_eur for index in selected_indices), start=Decimal())
        selected_densities = [densities[index] for index in selected_indices if densities[index] is not None]

    return Plan(
        dataset_version=analysis.dataset.dataset_version,
        budget_eur=float(request.budget_eur),
        total_cost_eur=float(total_cost),
        remaining_budget_eur=float(request.budget_eur - total_cost),
        modeled_benefit=round(sum(row.modeled_benefit for row in picks), 3),
        selected=picks,
        status=status,
        include_inspection=request.include_inspection,
        strategy=request.strategy,
        priority_only=request.priority_only,
        priority_site_count=sum(row.priority_band == "high" for row in picks),
        shade_impact=summarize_shade(picks),
        greened_roof_area_m2=round(sum(row.greened_roof_area_m2 or 0 for row in picks), 2),
        population_exposure_proxy=round(sum(selected_densities), 3),
        population_priority_sites_with_data=len(selected_densities),
        thermal_impact=project_thermal_impact(picks),
    )


def summarize_shade(picks: list[ExplainedIntervention]) -> PlanShadeImpact:
    impact = [pick.shade_impact for pick in picks if pick.shade_impact is not None]

    def footprint(horizon: ShadeHorizon) -> FootprintRange:
        contributions = [item for item in impact if item.horizon == horizon]
        return FootprintRange(
            min_m2=round(sum(item.estimated_min_m2 for item in contributions), 2),
            max_m2=round(sum(item.estimated_max_m2 for item in contributions), 2),
        )

    return PlanShadeImpact(
        after_installation=footprint("after_installation"),
        at_tree_maturity=footprint("at_tree_maturity"),
        unestimated_count=len(picks) - len(impact),
    )


def solve(
    options: list[ExplainedIntervention],
    costs: list[int],
    densities: list[float | None],
    budget_cents: int,
    strategy: PlanStrategy,
) -> tuple[list[int], PlanStatus]:
    model = cp_model.CpModel()
    selected = [model.new_bool_var(option.id) for option in options]
    by_location: dict[str, list[cp_model.IntVar]] = defaultdict(list)
    for var, option in zip(selected, options, strict=True):
        by_location[option.location_id].append(var)
    for alternatives in by_location.values():
        if len(alternatives) > 1:
            model.add_at_most_one(alternatives)

    total_cost = cp_model.LinearExpr.weighted_sum(selected, costs)
    model.add(total_cost <= budget_cents)

    hotspot_count = cp_model.LinearExpr.weighted_sum(
        selected, [int(option.priority_band == "high") for option in options],
    )
    population_exposure = cp_model.LinearExpr.weighted_sum(
        selected, [round((density or 0) * 1000) for density in densities],
    )
    total_benefit = cp_model.LinearExpr.weighted_sum(
        selected, [round(option.modeled_benefit * 1000) for option in options],
    )
    order = cp_model.LinearExpr.weighted_sum(selected, range(1, len(selected) + 1))
    # Freeze each proven optimum before considering the next objective.
    objectives = [hotspot_count]
    if strategy in {"tree_priority", "shade_and_rest"}:
        tree_counts = [
            option.shade_impact.unit_count if option.type == "tree_planting" and option.shade_impact else 0
            for option in options
        ]
        objectives.insert(0, cp_model.LinearExpr.weighted_sum(selected, tree_counts))
    objectives.append(population_exposure)
    if strategy == "immediate_shade":
        immediate_footprints = [
            round(option.shade_impact.estimated_min_m2 * 100)
            if option.shade_impact and option.shade_impact.horizon == "after_installation"
            else 0
            for option in options
        ]
        objectives.append(cp_model.LinearExpr.weighted_sum(selected, immediate_footprints))
    objectives.extend([total_benefit, -total_cost, -order])
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_deterministic_time = 0.5
    best: list[int] | None = None
    for expression in objectives:
        model.maximize(expression)
        result = solver.solve(model)
        if result in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best = [index for index, var in enumerate(selected) if solver.boolean_value(var)]
            if result == cp_model.FEASIBLE:
                return best, "feasible"
            model.add(expression == solver.value(expression))
        elif result == cp_model.UNKNOWN and best is not None:
            return best, "feasible"
        else:
            raise OptimizationError(f"Solver returned {solver.status_name(result)}")

    if best is None:
        raise OptimizationError("No plan was produced")
    return best, "optimal"
