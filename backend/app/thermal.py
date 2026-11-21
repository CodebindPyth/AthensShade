"""Apply field benchmarks to comparable summer surfaces in the selected plan."""

from collections import defaultdict
from dataclasses import dataclass
from math import fsum

from .models import ExplainedIntervention, InterventionType, ThermalImpact


@dataclass(frozen=True)
class Evidence:
    metric: str
    description: str
    url: str | None = None
    cooling_c: tuple[float, float] | None = None


EVIDENCE: dict[InterventionType, Evidence] = {
    "tree_planting": Evidence(
        metric="Θερμοκρασία δαπέδου κάτω από ώριμη κόμη",
        description=(
            "Σενάριο για επιφάνειες που σκιάζονται το μεσημέρι, σε ζεστή καλοκαιρινή ημέρα. "
            "Στο Μαρούσι μετρήθηκε διαφορά 11,6 °C στο σκυρόδεμα, 15,2 °C σε πλακόστρωτους "
            "διαδρόμους και 17,8 °C στην άσφαλτο, έναντι αντίστοιχων επιφανειών στον ήλιο. "
            "Η προβολή προϋποθέτει ώριμη κόμη και συγκρίσιμη επιφάνεια και σκίαση."
        ),
        url="https://doi.org/10.3390/land11112042",
        cooling_c=(11.6, 17.8),
    ),
    "shade_structure": Evidence(
        metric="Θερμοκρασία δαπέδου κάτω από σκίαστρο",
        description=(
            "Σενάριο μεσημεριανής ψύξης βασισμένο σε θερμογραφικές μετρήσεις σε δρόμους "
            "της Κόρδοβας σε καθαρή καλοκαιρινή ημέρα. Δύο τύποι υφασμάτινου σκιάστρου "
            "έδωσαν μέγιστες μειώσεις 9,2 και 13,2 °C σε συγκρίσιμες πλάκες γρανίτη. "
            "Η εφαρμογή του εύρους προϋποθέτει παρόμοιο υλικό, ηλιακή έκθεση και σκίαση."
        ),
        url="https://doi.org/10.1016/j.scs.2020.102458",
        cooling_c=(9.2, 13.2),
    ),
    "green_roof": Evidence(
        metric="Θερμοκρασία εξωτερικής επιφάνειας δώματος",
        description=(
            "Σε μελέτη εντατικού φυτεμένου δώματος γραφείου στην Αθήνα αναφέρθηκε "
            "θερμοκρασία επιφάνειας έως 15 °C χαμηλότερη από συμβατικό δώμα. "
            "Για τα προτεινόμενα σχολικά δώματα απαιτούνται στοιχεία για τη μόνωση, "
            "το υπόστρωμα και την άρδευση ώστε να εκτιμηθεί η μεταβολή."
        ),
        url="https://www.sciencedirect.com/science/article/pii/S0378778815003540",
    ),
    "greenery": Evidence(
        metric="Θερμοκρασία επιφάνειας χώρου πρασίνου",
        description=(
            "Για την εκτίμηση ψύξης χρειάζονται η υφιστάμενη κάλυψη, ο τύπος βλάστησης, "
            "η σκίαση και οι συνθήκες άρδευσης στη θέση."
        ),
    ),
}


def surface_area(item: ExplainedIntervention) -> tuple[float, float] | None:
    if item.type in ("tree_planting", "shade_structure") and item.shade_impact is not None:
        return item.shade_impact.estimated_min_m2, item.shade_impact.estimated_max_m2
    if item.type == "green_roof" and item.greened_roof_area_m2 is not None:
        return item.greened_roof_area_m2, item.greened_roof_area_m2
    return None


def project_thermal_impact(picks: list[ExplainedIntervention]) -> list[ThermalImpact]:
    by_type: dict[InterventionType, list[ExplainedIntervention]] = defaultdict(list)
    for pick in picks:
        by_type[pick.type].append(pick)

    impacts: list[ThermalImpact] = []
    for intervention_type, items in by_type.items():
        evidence = EVIDENCE[intervention_type]
        area_ranges = [area for item in items if (area := surface_area(item)) is not None]
        total_cost = round(fsum(item.cost_eur for item in items), 2)
        min_area = max_area = min_unit_cost = max_unit_cost = None
        if len(area_ranges) == len(items):
            min_area = round(fsum(lower for lower, _ in area_ranges), 2)
            max_area = round(fsum(upper for _, upper in area_ranges), 2)
            if min_area > 0:
                min_unit_cost = round(total_cost / max_area, 2)
                max_unit_cost = round(total_cost / min_area, 2)

        modeled_cooling = evidence.cooling_c if max_area is not None and max_area > 0 else None
        cooling_min, cooling_max = modeled_cooling or (None, None)
        impacts.append(ThermalImpact(
            type=intervention_type,
            area_min_m2=min_area,
            area_max_m2=max_area,
            installation_cost_eur=total_cost,
            cost_per_m2_min_eur=min_unit_cost,
            cost_per_m2_max_eur=max_unit_cost,
            cooling_min_c=cooling_min,
            cooling_max_c=cooling_max,
            metric=evidence.metric,
            evidence=evidence.description,
            evidence_url=evidence.url,
            location_ids=list(dict.fromkeys(item.location_id for item in items)),
        ))
    return impacts
