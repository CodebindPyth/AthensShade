from collections import defaultdict
from statistics import quantiles

from .ground_options import (
    TREE_DEFICIT_THRESHOLD_PERCENT,
    TREE_SPACING_M,
    add_ground_sites,
    ground_cost,
    tree_anchors,
    tree_rationale,
)
from .models import (
    Dataset,
    ExplainedIntervention,
    GeoJSONFeature,
    Intervention,
    Location,
    LocationAnalysis,
    PriorityBand,
    RankedLocation,
    ShadeImpact,
)
from .municipal_sites import _point_feature, add_municipal_sites
from .siting import assess_siting

ATHENS_STREET_SOURCES = {"athens-sites", "athens-atlas", "copernicus-canopy"}
ATHENS_RED_SURFACE_TEMPERATURE_C = 40.0


def screen_ground_intervention(
    intervention: Intervention, location: Location, red_cells: list[GeoJSONFeature],
) -> Intervention:
    assessment = assess_siting(intervention.location_id, intervention.type)
    evidence = assessment.evidence
    shade = intervention.shade_projection
    if assessment.status != "candidate" or evidence is None:
        return intervention.model_copy(update={
            "feasibility": "unsuitable",
            "siting": assessment.model_dump(mode="json", exclude={"evidence": {"geometry"}}),
        })

    if _point_feature(red_cells, evidence.longitude, evidence.latitude) is None:
        assessment = assessment.model_copy(update={
            "status": "unverified",
            "message": "Η χαρτογραφημένη θέση δεν εμπίπτει στην κόκκινη ζώνη του δημοτικού άτλαντα.",
        })
        return intervention.model_copy(update={
            "feasibility": "unsuitable", "siting": assessment.model_dump(mode="json"),
        })

    updates = {"feasibility": "requires_site_inspection"}
    anchors: list[dict[str, float]] = []
    if intervention.type == "tree_planting" and shade:
        capacity = min(shade.unit_count, int(evidence.available_area_m2 // TREE_SPACING_M ** 2))
        if capacity and location.canopy_percent is not None and location.canopy_percent < TREE_DEFICIT_THRESHOLD_PERCENT:
            anchors = tree_anchors(evidence, red_cells, capacity)
        if anchors:
            count = len(anchors)
            updates.update(
                cost_eur=ground_cost("tree_planting", count),
                cost_status="indicative",
                shade_projection=shade.model_copy(update={"unit_count": count}),
                rationale=tree_rationale(evidence.model_dump(), count),
            )
        else:
            updates["feasibility"] = "unsuitable"
            assessment = assessment.model_copy(update={
                "status": "insufficient_space",
                "message": "Ο έλεγχος δεν βρήκε αρκετό χώρο στην κόκκινη ζώνη με τεκμηριωμένο έλλειμμα δέντρων.",
            })

    if intervention.type == "shade_structure" and shade:
        original_area = shade.unit_count * shade.unit_projection_max_m2
        # Preserve a 2 m margin around a square footprint in the clear radius at the mapped center.
        clearance = max(0, evidence.edge_clearance_m - 2)
        area = int(min(original_area, evidence.available_area_m2 / 2, 2 * clearance ** 2))
        assessment = assess_siting(intervention.location_id, intervention.type, area)
        if area >= 16 and assessment.status == "candidate":
            anchors = [{"latitude": evidence.latitude, "longitude": evidence.longitude}]
            updates.update(
                cost_eur=ground_cost("shade_structure", area),
                cost_status="indicative",
                shade_projection=shade.model_copy(update={
                    "unit_count": 1, "unit_projection_min_m2": area, "unit_projection_max_m2": area,
                }),
                rationale=(
                    f"Σκίαστρο {area} m² μέσα σε {evidence.available_area_m2:.0f} m² χαρτογραφημένου χώρου πεζών. "
                    f"Το κέντρο απέχει {evidence.road_distance_m:.0f} μ. από τον κοντινότερο καταγεγραμμένο άξονα οχημάτων "
                    f"και {evidence.edge_clearance_m:.1f} μ. από το όριο της ζώνης. "
                    "Η αυτοψία ελέγχει τη θεμελίωση, τον άνεμο, τον προσανατολισμό και την ελεύθερη όδευση."
                    + (f" {evidence.constraint_note}" if evidence.constraint_note else "")
                ),
            )
        else:
            updates["feasibility"] = "unsuitable"
            if assessment.status == "candidate":
                assessment = assessment.model_copy(update={
                    "status": "insufficient_space",
                    "message": "Το χαρτογραφημένο σημείο δεν αφήνει αρκετό χώρο για στήριξη και διέλευση.",
                })
    updates["siting"] = {**assessment.model_dump(mode="json"), "anchors": anchors}
    return intervention.model_copy(update=updates)


class AthensAnalysis:
    def __init__(self, dataset: Dataset) -> None:
        # Both the map and priority rule use the same temperature distribution when available.
        temperatures = [float(feature.properties["temperature_c"]) for feature in dataset.heat.features]
        if not temperatures:
            temperatures = [location.heat_c for location in dataset.locations if location.heat_c is not None]

        self.heat_bounds = (min(temperatures), max(temperatures)) if temperatures else None
        self.hotspot_threshold = self.heat_bounds[1] if self.heat_bounds else None
        if len(temperatures) > 1:
            self.hotspot_threshold = quantiles(temperatures, n=4, method="inclusive")[2]
        athens_street_data = ATHENS_STREET_SOURCES.issubset(source.id for source in dataset.sources)
        if temperatures and athens_street_data:
            self.hotspot_threshold = ATHENS_RED_SURFACE_TEMPERATURE_C

        dataset = add_municipal_sites(dataset, self.hotspot_threshold)
        if self.hotspot_threshold is not None and athens_street_data:
            dataset = add_ground_sites(dataset, self.hotspot_threshold)
            red_cells = [feature for feature in dataset.heat.features
                         if float(feature.properties["temperature_c"]) > 35
                         and float(feature.properties["temperature_c"]) >= self.hotspot_threshold]
            by_id = {location.id: location for location in dataset.locations}
            dataset = dataset.model_copy(update={"interventions": [
                screen_ground_intervention(item, by_id[item.location_id], red_cells)
                if item.type in {"tree_planting", "shade_structure", "greenery"} and item.feasibility != "unsuitable"
                else item
                for item in dataset.interventions
            ]})
        self.dataset = dataset
        self.locations = {location.id: self.rank(location) for location in dataset.locations}
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
            siting=intervention.siting,
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
