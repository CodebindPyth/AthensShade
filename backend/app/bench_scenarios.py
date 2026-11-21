"""Derive a pilot intervention from Athens street locations in the real heat atlas."""

from decimal import Decimal

from .models import Dataset, Intervention, RankedLocation, ShadeProjection, Source

REFERENCE = Source(
    id="oraiokastro-shaded-seat-tender",
    title="Τιμολόγιο Δήμου Ωραιοκάστρου · Άρθρο 65",
    url="https://oraiokastro.gr/wp-content/uploads/2021/04/03_MELETH_TZAVELLA_20210429.pdf",
    period="2021",
    kind="cost",
    description="Ιστορική τιμή 1.800 € ανά ξύλινη πέργκολα με κάθισμα και εγκατάσταση.",
)
PILOT_LOCATIONS = ("kotzia", "kerameikos", "ramnes")
UNITS_PER_SITE = 4
REFERENCE_UNIT_EUR = Decimal("1800")
SITE_WORKS_ALLOWANCE_EUR = Decimal("1800")


def add_shaded_bench_scenarios(dataset: Dataset, locations: dict[str, RankedLocation]) -> Dataset:
    if not {"athens-sites", "athens-atlas", "copernicus-canopy"}.issubset(source.id for source in dataset.sources):
        return dataset

    known_ids = {item.id for item in dataset.interventions}
    proposals: list[Intervention] = []
    for location_id in PILOT_LOCATIONS:
        site = locations.get(location_id)
        intervention_id = f"{location_id}-shaded_bench"
        if site is None or not site.heat_hotspot or not site.tree_deficit or intervention_id in known_ids:
            continue
        proposals.append(Intervention(
            id=intervention_id,
            location_id=location_id,
            type="shaded_bench",
            cost_eur=UNITS_PER_SITE * REFERENCE_UNIT_EUR + SITE_WORKS_ALLOWANCE_EUR,
            feasibility="requires_site_inspection",
            cost_source_id=REFERENCE.id,
            cost_status="indicative",
            rationale=(
                "Demo προ ΦΠΑ: 4 σκιασμένα καθιστικά × 1.800 € από ιστορικό δημοτικό τιμολόγιο "
                "και 1.800 € ως ενδεικτική πρόβλεψη προσαρμογής της θέσης. "
                "Η αυτοψία ελέγχει τη σκίαση τις θερμές ώρες, την ελεύθερη όδευση πεζών, "
                "τα δίκτυα και τη δυνατότητα στήριξης."
            ),
            shade_projection=ShadeProjection(
                unit_count=UNITS_PER_SITE,
                unit_projection_min_m2=0,
                unit_projection_max_m2=0.96,
                horizon="after_installation",
                assumption=(
                    "Η ανώτερη τιμή είναι το ενδεικτικό οριζόντιο αποτύπωμα πέργκολας "
                    "1,20 × 0,80 μ. ανά καθιστικό. Χρειάζεται επιτόπιος έλεγχος για ώρες και έκταση πραγματικής σκίασης."
                ),
            ),
        ))
    if not proposals:
        return dataset

    sources = dataset.sources
    if all(item.id != REFERENCE.id for item in sources):
        sources = [*sources, REFERENCE]
    return dataset.model_copy(update={"sources": sources, "interventions": [*dataset.interventions, *proposals]})
