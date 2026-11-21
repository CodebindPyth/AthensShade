from collections import defaultdict
from decimal import Decimal
from functools import lru_cache

from ortools.sat.python import cp_model

from .analysis import AthensAnalysis
from .ground_options import tree_variants
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

EAST_ATHENS_LONGITUDE = 23.741
WEST_ATHENS_LONGITUDE = 23.724
WESTERN_PLANTING_SITES = frozenset({"avdi", "dourouti", "koumoundourou", "ramnes"})


class OptimizationError(Exception):
    """The solver could not produce a usable plan."""


def optimize(analysis: AthensAnalysis, request: OptimizeRequest) -> Plan:
    return _cached_plan(analysis, request.budget_eur, request.include_inspection, request.strategy, request.priority_only)


@lru_cache(maxsize=32)
def _cached_plan(
    analysis: AthensAnalysis, budget_eur: Decimal, include_inspection: bool, strategy: PlanStrategy, priority_only: bool,
) -> Plan:
    eligible = {"verified"}
    if include_inspection:
        eligible.add("requires_site_inspection")

    candidates = sorted(
        (
            row for row in analysis.dataset.interventions
            if row.feasibility in eligible
            and (not priority_only or analysis.locations[row.location_id].priority_band == "high")
        ),
        key=lambda row: row.id,
    )
    affordable = [
        variant for row in candidates for variant in tree_variants(row)
        if variant.cost_eur <= budget_eur
    ]
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
            options, costs, densities, int(budget_eur * 100), strategy,
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
        budget_eur=float(budget_eur),
        total_cost_eur=float(total_cost),
        remaining_budget_eur=float(budget_eur - total_cost),
        modeled_benefit=round(sum(row.modeled_benefit for row in picks), 3),
        selected=picks,
        status=status,
        include_inspection=include_inspection,
        strategy=strategy,
        priority_only=priority_only,
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
    selected = [model.new_bool_var(f"{option.id}:{index}") for index, option in enumerate(options)]
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
    tree_counts = [
        option.shade_impact.unit_count if option.type == "tree_planting" and option.shade_impact else 0
        for option in options
    ]
    shelter_counts = [
        option.shade_impact.unit_count if option.type == "shade_structure" and option.shade_impact else 0
        for option in options
    ]
    screened = any(option.siting and option.siting.get("anchors") for option in options)
    # Freeze each proven optimum before considering the next objective.
    objectives = [hotspot_count]
    if strategy in {"tree_priority", "shade_and_rest"}:
        objectives.insert(0, cp_model.LinearExpr.weighted_sum(selected, tree_counts))
    if screened:
        counts = [cp_model.LinearExpr.weighted_sum(selected, values) for values in (tree_counts, shelter_counts)]
        coverage = [model.new_bool_var(name) for name in ("adds_trees", "adds_shelters")]
        for count, used in zip(counts, coverage, strict=True):
            model.add(count >= 1).only_enforce_if(used)
            model.add(count == 0).only_enforce_if(used.Not())
        if strategy == "balanced":
            ground_sites = cp_model.LinearExpr.weighted_sum(
                selected, [int(bool(trees or shelters)) for trees, shelters in zip(tree_counts, shelter_counts, strict=True)],
            )
            tree_sites = cp_model.LinearExpr.weighted_sum(selected, [int(count > 0) for count in tree_counts])
            mixed_sites = model.new_int_var(0, len(by_location), "neighborhood_mix")
            model.add_min_equality(mixed_sites, [tree_sites, 2 * counts[1]])
            longitudes = [((option.siting or {}).get("evidence") or {}).get("longitude") for option in options]
            eastern_tree_counts = [
                trees if longitude is not None and longitude >= EAST_ATHENS_LONGITUDE else 0
                for trees, longitude in zip(tree_counts, longitudes, strict=True)
            ]
            western_tree_counts = [
                trees if longitude is not None and longitude < WEST_ATHENS_LONGITUDE else 0
                for trees, longitude in zip(tree_counts, longitudes, strict=True)
            ]
            east_tree_sites = cp_model.LinearExpr.weighted_sum(selected, [int(units > 0) for units in eastern_tree_counts])
            east_coverage = model.new_int_var(0, 5, "eastern_tree_coverage")
            model.add_min_equality(east_coverage, [east_tree_sites, 5])
            east_units = model.new_int_var(0, 60, "eastern_tree_units")
            model.add_min_equality(east_units, [cp_model.LinearExpr.weighted_sum(selected, eastern_tree_counts), 60])
            west_units = model.new_int_var(0, 32, "western_tree_units")
            model.add_min_equality(west_units, [cp_model.LinearExpr.weighted_sum(selected, western_tree_counts), 32])
            western_planting_sites = cp_model.LinearExpr.weighted_sum(selected, [
                int(trees > 0 and option.location_id in WESTERN_PLANTING_SITES)
                for option, trees in zip(options, western_tree_counts, strict=True)
            ])
            # Keep the east planting incentive and reward reopening screened western
            # candidate sites before allocating the entire budget to a few groups.
            balanced_score = (
                counts[0] + 16 * counts[1] + 40 * ground_sites + 15 * mixed_sites
                + 68 * east_coverage + 2 * east_units + 68 * western_planting_sites + 2 * west_units
            )
            objectives = [sum(coverage), balanced_score, hotspot_count]
        elif strategy in {"tree_priority", "shade_and_rest"}:
            objectives.extend([sum(coverage), counts[1]])
        else:
            objectives.append(sum(coverage))
    else:
        objectives.append(population_exposure)
    if strategy == "immediate_shade":
        immediate_footprints = [
            round(option.shade_impact.estimated_min_m2 * 100)
            if option.shade_impact and option.shade_impact.horizon == "after_installation"
            else 0
            for option in options
        ]
        objectives.append(cp_model.LinearExpr.weighted_sum(selected, immediate_footprints))
    if screened:
        objectives.append(population_exposure)
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
            model.clear_hints()
            for var in selected:
                model.add_hint(var, solver.boolean_value(var))
        elif result == cp_model.UNKNOWN and best is not None:
            return best, "feasible"
        else:
            raise OptimizationError(f"Solver returned {solver.status_name(result)}")

    if best is None:
        raise OptimizationError("No plan was produced")
    return best, "optimal"
