"""Join a small set of documented public premises to the municipal heat atlas."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from hashlib import sha1

from .models import Dataset, GeoJSONFeature, Location, Source
from .public_facilities import PUBLIC_FACILITIES


@dataclass(frozen=True)
class PublicPremise:
    id: str
    name: str
    latitude: float
    longitude: float
    source: Source
    coordinates_url: str
    notes: tuple[str, ...]
    heritage: bool = False


SCHOOL_OPTIONS = (
    "Φύτευση στην αυλή, σε σημεία με επαρκές έδαφος, άρδευση και ελεύθερη διέλευση.",
    "Σκίαστρα σε κατάλληλο τμήμα της αυλής, μετά από μέτρηση και έλεγχο των οδεύσεων.",
    "Φυτεμένο δώμα ή αναρριχώμενα σε ανεξάρτητο πλέγμα. Έλεγχος φορτίων, στεγάνωσης και συντήρησης.",
)

PREMISES = (
    PublicPremise(
        id="municipal-city-hall",
        name="Δημαρχιακό Μέγαρο Αθηνών",
        latitude=37.981909,
        longitude=23.727152,
        source=Source(
            id="athens-municipal-hall", title="Δήμος Αθηναίων · Δημαρχιακό Μέγαρο",
            url="https://www.cityofathens.gr/deltio-typoy/dimos-athinaion-150-chronia-dimarchiako-me/",
            period="Δημοτική τεκμηρίωση", kind="municipal_sites",
        ),
        coordinates_url="https://www.wikidata.org/wiki/Q755347",
        heritage=True,
        notes=(
            "Σε ιστορικό κτίριο εξετάζονται αναστρέψιμες λύσεις, όπως κινητές ζαρντινιέρες σε επιτρεπόμενο χώρο.",
            "Ανεξάρτητο πράσινο πλέγμα μόνο όπου ο χώρος και οι εγκρίσεις το επιτρέπουν.",
        ),
    ),
    PublicPremise(
        id="municipal-serafeio",
        name="Σεράφειο Δήμου Αθηναίων",
        latitude=37.97665,
        longitude=23.70675,
        source=Source(
            id="athens-municipal-serafeio", title="Σεράφειο · Επίσημη τοποθεσία",
            url="https://serafio.gr/ela-sto-serafeio/topothesia/",
            period="Δημοτική τεκμηρίωση", kind="municipal_sites",
        ),
        coordinates_url="https://unece.org/sites/default/files/2023-04/UNECE%20Forum%20PPPs-Athens%202023-Information%20Guide%20to%20registered%20participants.pdf",
        notes=(
            "Φυτεμένο δώμα, μετά από έλεγχο διαθέσιμης επιφάνειας, φορτίων, στεγάνωσης και άρδευσης.",
            "Αναρριχώμενα σε ανεξάρτητο πλέγμα με ζαρντινιέρες, με ελεύθερες εισόδους και οδεύσεις.",
        ),
    ),
    PublicPremise(
        id="municipal-technopolis",
        name="Τεχνόπολη Δήμου Αθηναίων",
        latitude=37.977106,
        longitude=23.713461,
        source=Source(
            id="athens-municipal-technopolis", title="Δήμος Αθηναίων · Βιομηχανικό Μουσείο Φωταερίου",
            url="https://www.cityofathens.gr/place/viomichaniko-moyseio-fotaerioy/",
            period="Δημοτική τεκμηρίωση", kind="municipal_sites",
        ),
        coordinates_url="https://www.wikidata.org/wiki/Q38284041",
        heritage=True,
        notes=(
            "Εξέτασε κινητή φύτευση με αναρριχώμενα ή αναστρέψιμη σκίαση στον εγκεκριμένο προαύλιο χώρο.",
            "Η έγκριση του ιστορικού χώρου και οι διαδρομές εκδηλώσεων και διαφυγής προηγούνται της χωροθέτησης.",
        ),
    ),
)

CURATED_SCHOOL_ID = "municipal-school-63-lykeio"
CURATED_SCHOOL_NAME = "63ο ΓΕΝΙΚΟ ΛΥΚΕΙΟ ΑΘΗΝΩΝ"


def _inside_ring(ring: Sequence[Sequence[float]], longitude: float, latitude: float) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, (*ring[1:], ring[0])):
        if (y1 > latitude) != (y2 > latitude):
            boundary_x = x1 + (x2 - x1) * (latitude - y1) / (y2 - y1)
            if longitude < boundary_x:
                inside = not inside
    return inside


def _point_feature(
    features: Sequence[GeoJSONFeature],
    longitude: float,
    latitude: float,
    kind: str | None = None,
) -> GeoJSONFeature | None:
    for feature in features:
        if kind is not None and feature.properties.get("kind") != kind:
            continue
        geometry = feature.geometry or {}
        coordinates = geometry.get("coordinates", [])
        if geometry.get("type") == "Polygon":
            polygons = [coordinates]
        elif geometry.get("type") == "MultiPolygon":
            polygons = coordinates
        else:
            continue
        for polygon in polygons:
            if polygon and polygon[0] and _inside_ring(polygon[0], longitude, latitude):
                if not any(ring and _inside_ring(ring, longitude, latitude) for ring in polygon[1:]):
                    return feature
    return None


def _asset_notes(kind: str, source: Source, notes: Sequence[str], scope: str, **extra: object) -> dict:
    return {
        "kind": kind,
        "source_url": str(source.url),
        "source_label": source.title,
        "notes": list(notes),
        "temperature_scope": scope,
        **extra,
    }


def _school_locations(dataset: Dataset, source: Source, threshold: float, existing: list[Location]):
    """Match official public school points to actual red atlas cells; index by geographic bins."""
    red_bins: dict[tuple[int, int], list[GeoJSONFeature]] = {}
    for cell in dataset.heat.features:
        value = cell.properties.get("temperature_c")
        if not isinstance(value, (float, int)) or value < threshold or value <= 35:
            continue
        geom = cell.geometry or {}
        if geom.get("type") != "Polygon":
            continue
        ring = geom["coordinates"][0]
        xs, ys = zip(*[(point[0], point[1]) for point in ring])
        for x in range(int(min(xs) * 100), int(max(xs) * 100) + 1):
            for y in range(int(min(ys) * 100), int(max(ys) * 100) + 1):
                red_bins.setdefault((x, y), []).append(cell)

    known = {(round(row.longitude, 5), round(row.latitude, 5)) for row in existing if row.municipal_asset}
    for feature in dataset.context.features if dataset.context else ():
        properties = feature.properties
        geom = feature.geometry or {}
        if properties.get("kind") != "school" or properties.get("source_id") != source.id or geom.get("type") != "Point":
            continue
        name = properties.get("name")
        if not name:
            continue
        lon, lat = geom["coordinates"][:2]
        position = round(lon, 5), round(lat, 5)
        if position in known:
            continue
        cell = _point_feature(red_bins.get((int(lon * 100), int(lat * 100)), []), lon, lat)
        if cell is None:
            continue
        known.add(position)
        key = sha1(f"{lon:.6f},{lat:.6f}".encode()).hexdigest()[:12]
        district = _point_feature(dataset.context.features, lon, lat, "district")
        yield Location(
            id=f"school-atlas-{key}", name=name, latitude=lat, longitude=lon,
            district=district.properties["name"] if district else "Δήμος Αθηναίων",
            heat_c=float(cell.properties["temperature_c"]), canopy_percent=None,
            shade_status="unknown", source_ids=[source.id, cell.properties["source_id"]],
            municipal_asset=_asset_notes("school", source, SCHOOL_OPTIONS, "atlas_cell", advisory_only=True),
        )


def _candidate(
    dataset: Dataset,
    threshold: float,
    id_: str,
    name: str,
    latitude: float,
    longitude: float,
    source: Source,
    municipal_asset: dict,
) -> Location | None:
    heat = _point_feature(dataset.heat.features, longitude, latitude)
    if heat is None:
        return None
    temperature = float(heat.properties["temperature_c"])
    if not isfinite(temperature) or temperature < threshold:
        return None

    canopy = _point_feature(dataset.trees.features, longitude, latitude, "canopy") if dataset.trees else None
    district = _point_feature(dataset.context.features, longitude, latitude, "district") if dataset.context else None
    source_ids = [source.id, heat.properties["source_id"]]
    for feature in (canopy, district):
        if feature and (source_id := feature.properties.get("source_id")) and source_id not in source_ids:
            source_ids.append(source_id)
    return Location(
        id=id_, name=name,
        district=district.properties.get("name", "") if district else "",
        latitude=latitude, longitude=longitude, heat_c=temperature,
        canopy_percent=canopy.properties.get("canopy_percent") if canopy else None,
        shade_status="unknown", source_ids=source_ids, municipal_asset=municipal_asset,
    )


def add_municipal_sites(dataset: Dataset, hotspot_threshold: float | None) -> Dataset:
    """Add documented study locations, leaving their street footprint and costs unclaimed."""
    schools = next((source for source in dataset.sources if source.id == "athens-schools" and source.url), None)
    if hotspot_threshold is None:
        return dataset
    locations = [
        location.model_copy(update={
            "municipal_asset": _asset_notes("school", schools, SCHOOL_OPTIONS, "existing_100m_estimate"),
        })
        if schools and schools.id in location.source_ids and not location.municipal_asset else location
        for location in dataset.locations
    ]
    existing_ids = {location.id for location in locations}
    sources = list(dataset.sources)
    source_ids = {source.id for source in sources}
    if "athens-atlas" not in source_ids:
        return dataset
    for premise in PREMISES:
        if premise.id in existing_ids:
            continue
        candidate = _candidate(
            dataset, hotspot_threshold, premise.id, premise.name, premise.latitude, premise.longitude, premise.source,
            _asset_notes(
                "building", premise.source, premise.notes, "atlas_cell",
                coordinates_url=premise.coordinates_url, heritage=premise.heritage,
            ),
        )
        if candidate:
            locations.append(candidate)
            if premise.source.id not in source_ids:
                sources.append(premise.source)
                source_ids.add(premise.source.id)

    if schools and dataset.context and CURATED_SCHOOL_ID not in existing_ids:
        school = next((
            feature for feature in dataset.context.features
            if feature.properties.get("kind") == "school"
            and feature.properties.get("name") == CURATED_SCHOOL_NAME
            and (feature.geometry or {}).get("type") == "Point"
        ), None)
        if school and school.geometry:
            longitude, latitude = school.geometry["coordinates"][:2]
            candidate = _candidate(
                dataset, hotspot_threshold, CURATED_SCHOOL_ID, CURATED_SCHOOL_NAME, latitude, longitude, schools,
                _asset_notes(
                    "school", schools, SCHOOL_OPTIONS, "atlas_cell",
                    coordinates_url="https://63lyk-athin.att.sch.gr/?page_id=2",
                ),
            )
            if candidate:
                locations.append(candidate)

    if schools and dataset.context:
        locations.extend(_school_locations(dataset, schools, hotspot_threshold, locations))

    for premise in PUBLIC_FACILITIES:
        if premise.id in existing_ids:
            continue
        candidate = _candidate(
            dataset, hotspot_threshold, premise.id, premise.name, premise.latitude, premise.longitude, premise.source,
            _asset_notes(
                premise.kind, premise.source, premise.notes, "atlas_cell",
                coordinates_url=premise.coordinates_url, agency=premise.agency, address=premise.address,
                advisory_only=True,
            ),
        )
        if candidate and candidate.heat_c > 35:
            locations.append(candidate)
            if premise.source.id not in source_ids:
                sources.append(premise.source)
                source_ids.add(premise.source.id)

    return Dataset.model_validate(dataset.model_dump() | {
        "locations": [location.model_dump() for location in locations],
        "sources": [source.model_dump() for source in sources],
    })
