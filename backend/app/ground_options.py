"""Build indicative interventions inside the road-screened pedestrian geometry."""

from collections.abc import Sequence
from decimal import Decimal
from math import ceil, cos, floor, radians

from .models import Dataset, GeoJSONFeature, Intervention, Location, ShadeProjection, Source
from .municipal_sites import _inside_ring, _point_feature
from .siting import SitingEvidence, load_siting

TREE_SPACING_M = 5
TREE_GRID_INSET_M = 1.5
TREE_DEFICIT_THRESHOLD_PERCENT = 15
TREE_COST_SOURCE = "athens-tree-tender"
SHADE_COST_SOURCE = "athens-shade-tender"
SITING_SOURCE = Source(
    id="osm-pedestrian-siting",
    title="Χώροι πεζών και δρόμοι · OpenStreetMap",
    url="https://www.openstreetmap.org/copyright",
    period="Χαρτογραφικό στιγμιότυπο",
    kind="siting",
    license="ODbL",
)


def ground_cost(kind: str, units: int) -> Decimal:
    if kind == "tree_planting":
        return Decimal(8_000 + 300 * units)
    return Decimal(12_000) + Decimal("69.43") * units


def add_ground_sites(dataset: Dataset, threshold: float | None) -> Dataset:
    if threshold is None:
        return dataset
    source_ids = {source.id for source in dataset.sources}
    if not {TREE_COST_SOURCE, SHADE_COST_SOURCE}.issubset(source_ids):
        return dataset

    existing = {location.id: location for location in dataset.locations}
    locations = dict(existing)
    interventions = list(dataset.interventions)
    for site_id, evidence in load_siting().items():
        heat = _point_feature(dataset.heat.features, evidence.longitude, evidence.latitude)
        if heat is None:
            continue
        temperature = float(heat.properties["temperature_c"])
        known = existing.get(site_id)
        if known is None and (not site_id.startswith("siting-") or temperature <= 35 or temperature < threshold):
            continue

        canopy = _point_feature(dataset.trees.features, evidence.longitude, evidence.latitude, "canopy") if dataset.trees else None
        district = _point_feature(dataset.context.features, evidence.longitude, evidence.latitude, "district") if dataset.context else None
        provenance = [SITING_SOURCE.id, heat.properties["source_id"]]
        for feature in (canopy, district):
            if feature and (source_id := feature.properties.get("source_id")) in source_ids:
                provenance.append(source_id)
        values = {
            "latitude": evidence.latitude,
            "longitude": evidence.longitude,
            "heat_c": temperature,
            "canopy_percent": canopy.properties.get("canopy_percent") if canopy else None,
        }
        if known:
            locations[site_id] = known.model_copy(update=values | {
                "source_ids": list(dict.fromkeys([*known.source_ids, *provenance])),
            })
            continue

        location = Location(
            id=site_id,
            name=evidence.mapped_space,
            district=district.properties["name"] if district else "Δήμος Αθηναίων",
            shade_status="unknown",
            source_ids=list(dict.fromkeys(provenance)),
            **values,
        )
        locations[site_id] = location
        interventions.extend(new_pedestrian_options(location, evidence))

    if locations == existing:
        return dataset
    sources = list(dataset.sources)
    if SITING_SOURCE.id not in source_ids:
        sources.append(SITING_SOURCE)
    return Dataset.model_validate(dataset.model_dump() | {
        "locations": list(locations.values()), "interventions": interventions, "sources": sources,
    })


def new_pedestrian_options(location: Location, evidence: SitingEvidence) -> list[Intervention]:
    result = []
    tree_capacity = int(evidence.available_area_m2 // TREE_SPACING_M ** 2)
    if tree_capacity > 0 and location.canopy_percent is not None and location.canopy_percent < TREE_DEFICIT_THRESHOLD_PERCENT:
        result.append(Intervention(
            id=f"{location.id}-tree_planting",
            location_id=location.id,
            type="tree_planting",
            cost_eur=ground_cost("tree_planting", tree_capacity),
            feasibility="requires_site_inspection",
            cost_source_id=TREE_COST_SOURCE,
            cost_status="indicative",
            rationale="Σενάριο φύτευσης στη χαρτογραφημένη ζώνη, με επιτόπιο έλεγχο.",
            shade_projection=ShadeProjection(
                unit_count=tree_capacity,
                unit_projection_min_m2=7.1,
                unit_projection_max_m2=19.6,
                horizon="at_tree_maturity",
                assumption="Ενδεικτική οριζόντια προβολή ώριμης κόμης διαμέτρου 3–5 μ. ανά δέντρο. Η επικάλυψη μπορεί να μειώσει τη συνολική σκιά.",
            ),
        ))
    result.append(Intervention(
        id=f"{location.id}-shade_structure",
        location_id=location.id,
        type="shade_structure",
        cost_eur=ground_cost("shade_structure", 120),
        feasibility="requires_site_inspection",
        cost_source_id=SHADE_COST_SOURCE,
        cost_status="indicative",
        rationale="Σενάριο σκιάστρου σε χαρτογραφημένο χώρο πεζών, με επιτόπιο έλεγχο.",
        shade_projection=ShadeProjection(
            unit_count=1,
            unit_projection_min_m2=120,
            unit_projection_max_m2=120,
            horizon="after_installation",
            assumption="Ενδεικτική οριζόντια επιφάνεια σκιάστρου. Η πραγματική σκιά μεταβάλλεται με τη θέση του ήλιου και τη σχεδίαση.",
        ),
    ))
    return result


def tree_anchors(
    evidence: SitingEvidence,
    red_cells: Sequence[GeoJSONFeature],
    capacity: int,
) -> list[dict[str, float]]:
    geometry = evidence.geometry
    if geometry.get("type") != "Polygon":
        return []
    polygon = geometry.get("coordinates") or []
    if not polygon or len(polygon[0]) < 3:
        return []

    meters_per_latitude = 111_195
    meters_per_longitude = meters_per_latitude * cos(radians(evidence.latitude))
    rings = [
        [((lon - evidence.longitude) * meters_per_longitude, (lat - evidence.latitude) * meters_per_latitude)
         for lon, lat in ring]
        for ring in polygon
    ]
    x_values, y_values = zip(*rings[0], strict=True)
    x_range = range(ceil(min(x_values) / TREE_SPACING_M), floor(max(x_values) / TREE_SPACING_M) + 1)
    y_range = range(ceil(min(y_values) / TREE_SPACING_M), floor(max(y_values) / TREE_SPACING_M) + 1)
    points = sorted(((x, y) for x in x_range for y in y_range), key=lambda point: (point[0] ** 2 + point[1] ** 2, point))
    anchors = []
    for x, y in points:
        x *= TREE_SPACING_M
        y *= TREE_SPACING_M
        if not _inside_ring(rings[0], x, y) or any(_inside_ring(ring, x, y) for ring in rings[1:]):
            continue
        if any(_distance_squared(x, y, start, end) < TREE_GRID_INSET_M ** 2
               for ring in rings for start, end in zip(ring, (*ring[1:], ring[0]), strict=True)):
            continue
        longitude = round(evidence.longitude + x / meters_per_longitude, 7)
        latitude = round(evidence.latitude + y / meters_per_latitude, 7)
        if _point_feature(red_cells, longitude, latitude) is not None:
            anchors.append({"latitude": latitude, "longitude": longitude})
            if len(anchors) >= capacity:
                break
    return anchors


def _distance_squared(x: float, y: float, start: tuple[float, float], end: tuple[float, float]) -> float:
    start_x, start_y = start
    segment_x, segment_y = end[0] - start_x, end[1] - start_y
    length_squared = segment_x ** 2 + segment_y ** 2
    ratio = ((x - start_x) * segment_x + (y - start_y) * segment_y) / length_squared if length_squared else 0
    ratio = max(0, min(1, ratio))
    return (x - start_x - ratio * segment_x) ** 2 + (y - start_y - ratio * segment_y) ** 2


def tree_variants(intervention: Intervention) -> list[Intervention]:
    shade = intervention.shade_projection
    if intervention.type != "tree_planting" or not shade or not (intervention.siting or {}).get("anchors"):
        return [intervention]
    anchors = intervention.siting["anchors"]
    quantities = sorted({min(4, len(anchors)), len(anchors), *range(8, len(anchors), 8)})
    return [intervention.model_copy(update={
        "cost_eur": ground_cost("tree_planting", quantity),
        "rationale": tree_rationale(intervention.siting["evidence"], quantity),
        "shade_projection": shade.model_copy(update={"unit_count": quantity}),
        "siting": {**intervention.siting, "anchors": anchors[:quantity]},
    }) for quantity in quantities]


def tree_rationale(evidence: dict, quantity: int) -> str:
    return (
        f"{quantity} δέντρα σε {evidence['available_area_m2']:.0f} m² χαρτογραφημένου χώρου πεζών. "
        f"Το σημείο αναφοράς απέχει {evidence['road_distance_m']:.0f} μ. από τον κοντινότερο καταγεγραμμένο άξονα οχημάτων. "
        f"Οι υποψήφιες θέσεις μέσα στη θερμή ζώνη απέχουν τουλάχιστον {TREE_SPACING_M} μ. μεταξύ τους. "
        "Η αυτοψία ελέγχει ριζικό χώρο, δίκτυα, άρδευση, υφιστάμενη βλάστηση και ελεύθερη όδευση."
    )
