"""Calculate a labeled annual spending scenario for selected municipal works."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel

from .models import ExplainedIntervention, InterventionType


class SavingsItem(BaseModel):
    intervention_id: str
    location_id: str
    type: InterventionType
    gross_annual_eur: float
    annual_maintenance_eur: float
    net_annual_eur: float
    assumptions: list[str]
    benefit: str | None = None


class SavingsScenario(BaseModel):
    source: Literal["hypothetical_scenario"] = "hypothetical_scenario"
    gross_annual_eur: float
    annual_maintenance_eur: float
    net_annual_eur: float
    items: list[SavingsItem]


ENERGY_KWH_PER_ROOF_M2 = Decimal(25)
ENERGY_EUR_PER_KWH = Decimal("0.20")
SEASONAL_RENTAL_PER_SHELTER_EUR = Decimal(4800)
SEASONAL_SETUP_PER_BENCH_EUR = Decimal(500)
MAINTENANCE_FRACTION = Decimal("0.02")

_LOCAL_BENEFITS: dict[InterventionType, str] = {
    "tree_planting": (
        "Η ώριμη κόμη δροσίζει τοπικά και, αν σκιάζει κλιματιζόμενο δημοτικό κτίριο, "
        "μπορεί να μειώσει την κατανάλωση ψύξης το καλοκαίρι."
    ),
    "shade_structure": (
        "Το μόνιμο σκίαστρο περιορίζει την άμεση έκθεση στον ήλιο για τους πεζούς και τον "
        "εξοπλισμό από κάτω. Αν καλύπτει την ίδια ανάγκη, μπορεί να αντικαταστήσει την προσωρινή σκίαση."
    ),
    "shaded_bench": (
        "Η μικρότερη έκθεση στην υπεριώδη ακτινοβολία μπορεί να επιβραδύνει το ξεθώριασμα "
        "και τη φθορά του φινιρίσματος στο παγκάκι."
    ),
    "green_roof": (
        "Το φυτεμένο δώμα μπορεί να μειώσει τη ζέστη που περνά από την οροφή "
        "και τις ανάγκες καλοκαιρινής ψύξης του κτιρίου."
    ),
    "greenery": "Η βλάστηση μπορεί να βελτιώσει το μικροκλίμα μέσω σκιάς και εξατμισοδιαπνοής.",
}


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _gross_savings(item: ExplainedIntervention) -> tuple[Decimal, str]:
    if item.type == "green_roof":
        if item.greened_roof_area_m2 is None:
            return Decimal(0), "Χρειάζεται εκτίμηση της επιφάνειας του δώματος για να υπολογιστεί εξοικονόμηση."
        area = Decimal(str(item.greened_roof_area_m2))
        return (
            area * ENERGY_KWH_PER_ROOF_M2 * ENERGY_EUR_PER_KWH,
            "Υποθέτουμε 25 kWh λιγότερη κατανάλωση ψύξης ανά m² δώματος τον χρόνο, "
            "με τιμή 0,20 €/kWh. Χρειάζονται μετρήσεις σε συγκρίσιμες συνθήκες πριν και μετά.",
        )

    if item.type in {"shade_structure", "shaded_bench"} and item.shade_impact is None:
        return Decimal(0), "Χρειάζεται εκτίμηση της ποσότητας για να υπολογιστεί εξοικονόμηση."
    units = item.shade_impact.unit_count if item.shade_impact else 0
    if item.type == "shade_structure":
        return (
            units * SEASONAL_RENTAL_PER_SHELTER_EUR,
            "Υποθέτουμε ότι κάθε μόνιμο σκίαστρο αντικαθιστά υφιστάμενη εποχική μίσθωση "
            "και εγκατάσταση προσωρινής σκίασης αξίας 4.800 € τον χρόνο.",
        )
    if item.type == "shaded_bench":
        return (
            units * SEASONAL_SETUP_PER_BENCH_EUR,
            "Υποθέτουμε ότι κάθε σκιασμένο παγκάκι αντικαθιστά υφιστάμενη εποχική "
            "δαπάνη 500 € τον χρόνο για προσωρινό εξοπλισμό καθιστικού και σκίασης στην ίδια θέση.",
        )
    if item.type == "tree_planting":
        return (
            Decimal(0),
            "Το βασικό σενάριο υπολογίζει 0 € άμεσης εξοικονόμησης. Με ώριμη κόμη, "
            "ένα εναλλακτικό παράδειγμα είναι 1.200 € τον χρόνο, εφόσον τα δέντρα "
            "αντικαθιστούν τεκμηριωμένη εποχική μίσθωση σκίασης στην ίδια θέση.",
        )
    return Decimal(0), "Υποθέτουμε 0 € άμεσης εξοικονόμησης για τη διαμόρφωση πρασίνου."


def calculate_savings(interventions: list[ExplainedIntervention]) -> SavingsScenario:
    total_gross = total_maintenance = Decimal(0)
    items: list[SavingsItem] = []
    for intervention in interventions:
        gross, assumption = _gross_savings(intervention)
        gross = _cents(gross)
        maintenance = _cents(Decimal(str(intervention.cost_eur)) * MAINTENANCE_FRACTION)
        total_gross += gross
        total_maintenance += maintenance
        items.append(SavingsItem(
            intervention_id=intervention.id,
            location_id=intervention.location_id,
            type=intervention.type,
            gross_annual_eur=float(gross),
            annual_maintenance_eur=float(maintenance),
            net_annual_eur=float(gross - maintenance),
            assumptions=[assumption, "Υποθέτουμε πρόσθετη ετήσια συντήρηση ίση με 2% του αρχικού κόστους."],
            benefit=_LOCAL_BENEFITS.get(intervention.type),
        ))

    return SavingsScenario(
        gross_annual_eur=float(total_gross),
        annual_maintenance_eur=float(total_maintenance),
        net_annual_eur=float(total_gross - total_maintenance),
        items=items,
    )
