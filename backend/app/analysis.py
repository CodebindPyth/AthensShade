from collections import defaultdict
from statistics import quantiles

from .bench_scenarios import add_shaded_bench_scenarios
from .models import (
    Dataset,
    ExplainedIntervention,
    Intervention,
    Location,
    LocationAnalysis,
    PriorityBand,
    RankedLocation,
    ShadeImpact,
)

TREE_DEFICIT_THRESHOLD_PERCENT = 15


class AthensAnalysis:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        # Both the map and priority rule use the same temperature distribution when available.
        temperatures = [float(feature.properties["temperature_c"]) for feature in dataset.heat.features]
        if not temperatures:
            temperatures = [location.heat_c for location in dataset.locations if location.heat_c is not None]

        self.heat_bounds = (min(temperatures), max(temperatures)) if temperatures else None
        self.hotspot_threshold = self.heat_bounds[1] if self.heat_bounds else None
        if len(temperatures) > 1:
            self.hotspot_threshold = quantiles(temperatures, n=4, method="inclusive")[2]

        self.locations = {location.id: self.rank(location) for location in dataset.locations}
        self.dataset = add_shaded_bench_scenarios(dataset, self.locations)
        self.interventions_by_location: dict[str, list[Intervention]] = defaultdict(list)
        for intervention in self.dataset.interventions:
            self.interventions_by_location[intervention.location_id].append(intervention)

    def rank(self, location: Location) -> RankedLocation:
        hotspot = (
            location.heat_c >= self.hotspot_threshold
            if location.heat_c is not None and self.hotspot_threshold is not None
            else None
        )
        tree_deficit = (
            location.canopy_percent < TREE_DEFICIT_THRESHOLD_PERCENT
            if location.canopy_percent is not None
            else None
        )
        shade_deficit = {"deficit": True, "present": False, "unknown": None}[location.shade_status]
        priority: PriorityBand = "unknown"
        if hotspot and (tree_deficit or shade_deficit):
            priority = "high"
        elif hotspot is False or (hotspot is True and tree_deficit is False and shade_deficit is False):
            priority = "standard"

        score = None
        if location.heat_c is not None and self.heat_bounds is not None:
            lower, upper = self.heat_bounds
            normalized = (location.heat_c - lower) / (upper - lower) if upper > lower else 1
            temperature_score = 60 * min(1, max(0, normalized))
            score = round(temperature_score + 25 * (tree_deficit is True) + 15 * (shade_deficit is True))

        return RankedLocation.model_validate(location.model_dump() | {
            "priority_band": priority,
            "priority_score": score,
            "heat_hotspot": hotspot,
            "tree_deficit": tree_deficit,
            "shade_deficit": shade_deficit,
        })

    def describe(self, location: RankedLocation) -> str:
        if location.priority_band == "high":
            evidence = []
            if location.tree_deficit:
                evidence.append(f"δενδροκάλυψη {location.canopy_percent:g}%")
            if location.shade_deficit:
                evidence.append("τεκμηριωμένη έλλειψη σκίασης")
            deficits = " και ".join(evidence)
            explanation = f"Υψηλή προτεραιότητα λόγω θερμοκρασίας {location.heat_c:g} °C και ένδειξης ελλείμματος ({deficits})."
            if location.population_density_per_km2 is not None:
                explanation += (
                    " Η εκτιμώμενη πληθυσμιακή πυκνότητα γύρω από το σημείο είναι "
                    f"{location.population_density_per_km2:.0f} κάτοικοι/χλμ²."
                )
            return explanation
        if location.heat_c is None:
            return "Εκκρεμεί διαθέσιμη μέτρηση θερμοκρασίας για το σημείο."
        if location.priority_band == "unknown":
            return "Το σημείο βρίσκεται σε θερμή ζώνη. Απαιτούνται περισσότερα στοιχεία για τη δενδροκάλυψη ή τη σκίαση."
        if location.heat_hotspot:
            return "Το σημείο βρίσκεται σε θερμή ζώνη και τα διαθέσιμα στοιχεία δείχνουν δενδροκάλυψη και σκίαση."
        return "Η καταγεγραμμένη θερμοκρασία του σημείου βρίσκεται κάτω από το όριο της θερμής ζώνης."

    def explain_intervention(self, intervention: Intervention) -> ExplainedIntervention:
        location = self.locations[intervention.location_id]
        feasibility = {
            "verified": "Υπάρχει τεκμηρίωση εφικτότητας για τη συγκεκριμένη παρέμβαση.",
            "requires_site_inspection": "Απαιτείται αυτοψία του χώρου πριν από οποιαδήποτε έγκριση.",
            "unsuitable": "Η παρέμβαση έχει χαρακτηριστεί ακατάλληλη για το συγκεκριμένο σημείο.",
        }[intervention.feasibility]
        cost = {
            "indicative": "Το κόστος είναι ενδεικτικό.",
            "verified": "Το κόστος συνοδεύεται από τεκμηρίωση.",
        }[intervention.cost_status]
        modeled_benefit = intervention.modeled_benefit
        if modeled_benefit is None:
            modeled_benefit = float(1 + (location.priority_score or 0))
        shade = intervention.shade_projection
        shade_impact = (
            ShadeImpact(
                unit_count=shade.unit_count,
                estimated_min_m2=round(shade.unit_count * shade.unit_projection_min_m2, 2),
                estimated_max_m2=round(shade.unit_count * shade.unit_projection_max_m2, 2),
                horizon=shade.horizon,
                assumption=shade.assumption,
            )
            if shade else None
        )
        return ExplainedIntervention(
            id=intervention.id,
            location_id=intervention.location_id,
            type=intervention.type,
            cost_eur=float(intervention.cost_eur),
            modeled_benefit=modeled_benefit,
            benefit_basis="supplied_model" if intervention.modeled_benefit is not None else "priority_heuristic",
            feasibility=intervention.feasibility,
            cost_source_id=intervention.cost_source_id,
            cost_status=intervention.cost_status,
            rationale=intervention.rationale,
            explanation=f"{self.describe(location)} {feasibility} {cost}",
            priority_band=location.priority_band,
            shade_impact=shade_impact,
            greened_roof_area_m2=intervention.greened_roof_area_m2,
        )

    def location_analysis(self, location_id: str) -> LocationAnalysis:
        location = self.locations[location_id]
        explanation = self.describe(location)
        if location.plantings_count is not None:
            explanation += f" Η διαθέσιμη καταγραφή για την περιοχή αναφέρει {location.plantings_count} φυτεύσεις."
        elif location.planting_records_count:
            explanation += (
                f" Ο δημοτικός χάρτης έχει {location.planting_records_count} καταγραφές σε ακτίνα 100 μ. "
                "Το ακριβές πλήθος δέντρων παραμένει άγνωστο."
            )
        elif location.planting_documented:
            explanation += " Υπάρχει τεκμηρίωση προηγούμενων φυτεύσεων στην περιοχή, με άγνωστο πλήθος."
        return LocationAnalysis(
            location=location,
            interventions=[
                self.explain_intervention(intervention)
                for intervention in self.interventions_by_location.get(location_id, [])
            ],
            explanation=explanation,
        )
