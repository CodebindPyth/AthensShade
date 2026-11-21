"""Build the facts and verification steps available to a plan brief."""

from dataclasses import dataclass

from .analysis import AthensAnalysis
from .models import ExplainedIntervention, InterventionType, Plan, RankedLocation


@dataclass(frozen=True, slots=True)
class BriefFact:
    id: str
    text: str
    topic: str


@dataclass(frozen=True, slots=True)
class BriefSource:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class BriefEvidence:
    summary: str
    priorities: tuple[BriefFact, ...]
    next_steps: tuple[BriefFact, ...]
    evidence: tuple[BriefSource, ...]


INTERVENTION_LABELS: dict[InterventionType, str] = {
    "tree_planting": "Φύτευση δέντρων",
    "shade_structure": "Εγκατάσταση σκιάστρου",
    "shaded_bench": "Σκιασμένα παγκάκια",
    "greenery": "Διαμόρφωση πρασίνου",
    "green_roof": "Φυτεμένο δώμα",
}
INSPECTION_CHECKS: dict[InterventionType, str] = {
    "tree_planting": "τον χώρο για τις ρίζες, τα υπόγεια δίκτυα και τη δυνατότητα άρδευσης",
    "shade_structure": "τον χώρο στήριξης, τη ζώνη σκιάς και την προσβασιμότητα",
    "shaded_bench": "τη σκιά στο κάθισμα, την ελεύθερη όδευση και τον χώρο δίπλα για αμαξίδιο",
    "greenery": "τη διαθέσιμη επιφάνεια, το έδαφος και τη δυνατότητα άρδευσης",
    "green_roof": "τη φέρουσα ικανότητα, τη στεγάνωση και την απορροή του δώματος",
}


def _number(value: float) -> str:
    integer, fraction = f"{value:,.2f}".split(".")
    fraction = fraction.rstrip("0")
    return integer.replace(",", ".") + (f",{fraction}" if fraction else "")


def _range(lower: float, upper: float) -> str:
    return _number(lower) if lower == upper else f"{_number(lower)}–{_number(upper)}"


def _site_fact(pick: ExplainedIntervention, site: RankedLocation, index: int) -> BriefFact:
    rationale = [f"{site.name} · {INTERVENTION_LABELS[pick.type]}. Αρχικό κόστος {_number(pick.cost_eur)} €."]
    if site.priority_band == "high":
        if site.heat_c is not None:
            rationale.append(f"Η θέση είναι στη θερμότερη ζώνη, με ιστορική θερμοκρασία επιφάνειας {_number(site.heat_c)} °C.")
        if site.tree_deficit and site.canopy_percent is not None:
            rationale.append(f"Η εκτιμώμενη δενδροκάλυψη είναι {_number(site.canopy_percent)}%.")
        if site.shade_deficit:
            rationale.append("Υπάρχει τεκμηριωμένη έλλειψη σκίασης.")
        if site.population_density_per_km2 is not None:
            rationale.append(f"Η γύρω πληθυσμιακή πυκνότητα εκτιμάται σε {_number(site.population_density_per_km2)} κατοίκους/χλμ².")
    priority_topic = " · υψηλή προτεραιότητα" if site.priority_band == "high" else ""
    return BriefFact(f"site-{index}", " ".join(rationale), INTERVENTION_LABELS[pick.type] + priority_topic)


def _impact_facts(plan: Plan) -> list[BriefFact]:
    facts: list[BriefFact] = []
    shade = plan.shade_impact
    if shade.after_installation.max_m2 > 0:
        area = _range(shade.after_installation.min_m2, shade.after_installation.max_m2)
        facts.append(BriefFact(
            "immediate-shade",
            f"Οι παρεμβάσεις άμεσης σκίασης εκτιμάται ότι δίνουν {area} m² δυνητικής σκιάς μετά την εγκατάσταση.",
            "Έκταση σκιάς μετά την εγκατάσταση",
        ))
    if shade.at_tree_maturity.max_m2 > 0:
        area = _range(shade.at_tree_maturity.min_m2, shade.at_tree_maturity.max_m2)
        facts.append(BriefFact(
            "mature-shade",
            f"Τα δέντρα εκτιμάται ότι δίνουν {area} m² δυνητικής σκιάς όταν ωριμάσουν.",
            "Έκταση σκιάς από ώριμα δέντρα",
        ))
    if plan.greened_roof_area_m2 > 0:
        facts.append(BriefFact(
            "roof-area",
            f"Η προτεινόμενη επιφάνεια φυτεμένων δωμάτων είναι {_number(plan.greened_roof_area_m2)} m².",
            "Έκταση φυτεμένων δωμάτων",
        ))
    for impact in plan.thermal_impact:
        if impact.cooling_min_c is not None and impact.cooling_max_c is not None:
            degrees = _range(impact.cooling_min_c, impact.cooling_max_c)
            facts.append(BriefFact(
                f"cooling-{impact.type}",
                f"{impact.metric}. Ενδεικτική μείωση {degrees} °C σε συγκρίσιμες καλοκαιρινές συνθήκες.",
                f"Εκτίμηση ψύξης σκιασμένου δαπέδου · {INTERVENTION_LABELS[impact.type]}",
            ))
    return facts


def _verification_steps(plan: Plan, analysis: AthensAnalysis) -> tuple[BriefFact, ...]:
    inspection_steps: dict[InterventionType, BriefFact] = {}
    for pick in plan.selected:
        if pick.feasibility == "requires_site_inspection" and pick.type not in inspection_steps:
            site = analysis.locations[pick.location_id]
            inspection_steps[pick.type] = BriefFact(
                f"inspect-{pick.type}",
                f"Πριν από την έγκριση, ελέγξτε με αυτοψία {INSPECTION_CHECKS[pick.type]} στη θέση «{site.name}».",
                f"Αυτοψία πριν από την έγκριση · {INTERVENTION_LABELS[pick.type]}",
            )
    if inspection_steps:
        return tuple(inspection_steps.values())
    first_site = analysis.locations[plan.selected[0].location_id]
    return (BriefFact(
        "record-baseline",
        f"Καταγράψτε την υφιστάμενη σκιά και τη θερμοκρασία επιφάνειας στη θέση «{first_site.name}» πριν από την παρέμβαση.",
        "Αρχική αποτύπωση σκιάς και θερμοκρασίας",
    ),)


def _sources(plan: Plan, analysis: AthensAnalysis) -> tuple[BriefSource, ...]:
    site_sources = {
        source_id
        for pick in plan.selected
        for source_id in analysis.locations[pick.location_id].source_ids
    }
    cost_sources = {pick.cost_source_id for pick in plan.selected}
    references = {
        str(source.url): BriefSource(source.title, str(source.url))
        for source in analysis.dataset.sources
        if source.url and (
            source.id in cost_sources or
            (source.id in site_sources and source.kind in {"heat", "canopy", "population", "locations", "schools"})
        )
    }
    for impact in plan.thermal_impact:
        if impact.evidence_url:
            url = str(impact.evidence_url)
            references.setdefault(url, BriefSource(f"Θερμική μελέτη · {INTERVENTION_LABELS[impact.type]}", url))
    return tuple(references.values())


def _empty_plan(plan: Plan, analysis: AthensAnalysis) -> BriefEvidence:
    if plan.status == "no_affordable_interventions":
        summary = f"Ο προϋπολογισμός των {_number(plan.budget_eur)} € δεν επαρκεί για επιλέξιμη παρέμβαση."
        next_step = BriefFact(
            "check-budget",
            "Συγκρίνετε το κόστος των υποψήφιων παρεμβάσεων με τον διαθέσιμο προϋπολογισμό.",
            "Έλεγχος ορίου προϋπολογισμού",
        )
    elif not plan.include_inspection and any(
        intervention.feasibility == "requires_site_inspection" for intervention in analysis.dataset.interventions
    ):
        summary = "Το πλάνο δεν περιλαμβάνει επιλεγμένες παρεμβάσεις. Υπάρχουν θέσεις που απαιτούν αυτοψία."
        next_step = BriefFact(
            "include-inspections",
            "Ενεργοποιήστε τη συμπερίληψη θέσεων προς αυτοψία για ένα διερευνητικό πλάνο.",
            "Συμπερίληψη θέσεων προς αυτοψία",
        )
    else:
        summary = "Το πλάνο δεν περιλαμβάνει επιλεγμένες παρεμβάσεις."
        next_step = BriefFact(
            "review-candidates",
            "Ελέγξτε την τεχνική τεκμηρίωση εφικτότητας των υποψήφιων θέσεων.",
            "Έλεγχος τεχνικής εφικτότητας",
        )
    return BriefEvidence(summary, (), (next_step,), ())


def build_brief_evidence(plan: Plan, analysis: AthensAnalysis) -> BriefEvidence:
    if not plan.selected:
        return _empty_plan(plan, analysis)

    count = len(plan.selected)
    intervention_count = "1 παρέμβαση" if count == 1 else f"{count} παρεμβάσεις"
    cost_label = "ενδεικτικό κόστος" if any(pick.cost_status == "indicative" for pick in plan.selected) else "κόστος"
    summary = (
        f"Το πλάνο περιλαμβάνει {intervention_count} με {cost_label} "
        f"{_number(plan.total_cost_eur)} € από προϋπολογισμό {_number(plan.budget_eur)} €."
    )
    if any(pick.feasibility == "requires_site_inspection" for pick in plan.selected):
        summary += " Οι θέσεις προς αυτοψία χρειάζονται τεχνικό έλεγχο πριν από την έγκριση."
    site_facts = [
        _site_fact(pick, analysis.locations[pick.location_id], index)
        for index, pick in enumerate(plan.selected[:8], start=1)
    ]
    priorities = tuple(site_facts[:1] + _impact_facts(plan) + site_facts[1:])
    return BriefEvidence(summary, priorities, _verification_steps(plan, analysis), _sources(plan, analysis))
