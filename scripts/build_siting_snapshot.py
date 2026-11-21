"""Compile conservative pilot siting polygons from OpenStreetMap XML.

Install requirements-data.txt and run from the repository root. Use --raw to
keep the downloaded OSM XML separate from the checked-in derived snapshot.
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from numpy import round as round_coordinates
from pyproj import Transformer
from shapely import make_valid, maximum_inscribed_circle, transform, union_all
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import polygonize
from shapely.strtree import STRtree


OSM_API = "https://api.openstreetmap.org/api/0.6"
BBOXES = {
    "avdi": "23.7175,37.9805,23.7225,37.985",
    "kotzia": "23.7245,37.980,23.731,37.9845",
    "west": "23.710,37.977,23.718,37.9875",
    "koumoundourou": "23.7166,37.9773,23.7250,37.9841",
    "omonoia": "23.7250,37.9820,23.7370,37.9904",
    "syntagma": "23.7285,37.9712,23.7375,37.9795",
    "neos-kosmos": "23.7190,37.9500,23.731,37.961",
    "abelokipi": "23.7495,37.9823,23.7627,37.9912",
    "goudi": "23.763,37.9788,23.775,37.989",
    "kolonos": "23.7110,37.9890,23.7215,37.9980",
    "petralona": "23.7010,37.9590,23.7150,37.9705",
    "platonos-perimeter": "23.7101,37.9853,23.7139,37.9890",
    "athanaton-perimeter": "23.7725,37.9832,23.7776,37.9871",
    "pangrati-north": "23.7390,37.9695,23.7525,37.9786",
    "center-perimeter": "23.7282,37.9777,23.7327,37.9840",
    "petralona-perimeter": "23.7130,37.9634,23.7168,37.9690",
    "larissis-perimeter": "23.7197,37.9898,23.7232,37.9936",
    "orthodoxias-perimeter": "23.7108,37.9967,23.7139,38.0000",
}
ATHENS_RED_SURFACE_TEMPERATURE_C = 40.0
# Pair city-named sites with matching OSM public-square features. For the
# place=square ways, exclude vehicle routes before considering the interior.
AREAS = {
    "avdi": ("way", "765267680"),
    "dourouti": ("way", "765267679"),
    "kerameikos": ("relation", "2875650"),
    "kotzia": ("relation", "12250112"),
    "koumoundourou": ("way", "23216567"),
    "ramnes": ("way", "101515240"),
    "siting-akadimia-platonos": ("way", "101404642"),
    "siting-amalias-merkouri": ("way", "68528388"),
    "siting-athanaton": ("way", "117872478"),
    "siting-agion-theodoron": ("relation", "3781524"),
    "siting-dikaiosynis": ("relation", "19039361"),
    "siting-dimitri-mpei": ("relation", "17265605"),
    "siting-elpidos": ("way", "68528386"),
    "siting-evangelikis-scholis": ("way", "98192082"),
    "siting-filomousou": ("way", "830721001"),
    "siting-filopappou": ("way", "300633205"),
    "siting-ious": ("relation", "10775537"),
    "siting-kardamati": ("way", "67760292"),
    "siting-karytsi": ("relation", "10580279"),
    "siting-kolokotroni": ("relation", "19040139"),
    "siting-larissis": ("way", "281021503"),
    "siting-lavriou": ("way", "712402629"),
    "siting-machis-analatou": ("way", "101016060"),
    "siting-mitropoleos": ("relation", "9917015"),
    "siting-omonoia": ("relation", "12317186"),
    "siting-orthodoxias": ("way", "51396738"),
    "siting-paidon": ("way", "100838691"),
    "siting-pantazopoulou": ("way", "49014638"),
    "siting-syntagma": ("relation", "16363966"),
    "siting-voutie": ("way", "68528408"),
    "siting-goudi-army-park": ("way", "489448986"),
    "siting-chorofylakis": ("way", "32111469"),
    "siting-rigillis": ("way", "319859811"),
}
STASY_STATIONS = "https://www.stasy.gr/wp-content/uploads/2025/10/25PROC017683325.pdf"
UNDERGROUND_CONSTRAINTS = {
    "kotzia": (
        "Κάτω από την πλατεία υπάρχει δημοτικός σταθμός στάθμευσης. "
        "Η στήριξη σκιάστρου απαιτεί έλεγχο φέρουσας πλάκας.",
        "https://www.daem.gr/ypogeia-parking/",
    ),
    "kerameikos": (
        "Ο σταθμός Μετρό Κεραμεικός βρίσκεται στην πλατεία. Απαιτείται έλεγχος των "
        "υπόγειων εγκαταστάσεων και των προσβάσεων του σταθμού πριν από στήριξη.",
        STASY_STATIONS,
    ),
    "siting-larissis": (
        "Η πλατεία εξυπηρετεί τον Σταθμό Λαρίσης. Απαιτείται έλεγχος υπόγειων εγκαταστάσεων "
        "και ελεύθερης πρόσβασης στον σταθμό πριν από στήριξη.",
        STASY_STATIONS,
    ),
    "siting-omonoia": (
        "Κάτω από την πλατεία λειτουργεί σταθμός Μετρό. Απαιτείται μελέτη στήριξης "
        "και έλεγχος ελεύθερης πρόσβασης στον σταθμό.",
        STASY_STATIONS,
    ),
    "siting-syntagma": (
        "Κάτω από την πλατεία λειτουργεί σταθμός Μετρό. Απαιτείται μελέτη στήριξης, "
        "έλεγχος ελεύθερης πρόσβασης και συντονισμός με τις υπάρχουσες επεμβάσεις.",
        STASY_STATIONS,
    ),
}
MAIN_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "busway"}
CAR_ROADS = MAIN_ROADS | {"unclassified", "residential", "service", "track", "living_street", "road"}
FOOT_ROADS = {"footway", "pedestrian", "steps", "path", "cycleway"}
RESTRICTED_ACCESS = {"private", "customers", "no", "permit"}
VEHICLE_ACCESS = {"yes", "permissive", "designated", "destination", "delivery"}
OBSTACLE_AREAS = {
    "amenity": {"fountain", "parking"},
    "leisure": {"playground", "pitch", "outdoor_seating", "sports_centre"},
    "natural": {"water", "wood"},
    "landuse": {"forest"},
}
TO_METERS = Transformer.from_crs(4326, 2100, always_xy=True).transform
TO_LON_LAT = Transformer.from_crs(2100, 4326, always_xy=True).transform


def tags(element):
    return {item.attrib["k"]: item.attrib["v"] for item in element.findall("tag")}


def existing_or_download(path, url):
    if not path.is_file():
        request = Request(url, headers={"User-Agent": "AthensShade pilot mapping snapshot"})
        with urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    return ElementTree.parse(path).getroot()


def load_geometry(raw):
    nodes, ways, relations = {}, {}, {}

    def add_root(root):
        for kind, index in (("node", nodes), ("way", ways), ("relation", relations)):
            index.update((item.attrib["id"], item) for item in root.findall(kind))

    for name, bbox in BBOXES.items():
        add_root(existing_or_download(raw / f"siting-{name}.osm", f"{OSM_API}/map?bbox={bbox}"))
    # The bounded map response usually includes the whole polygon. Retrieve
    # any relation members that extend out of the requested tiles.
    for kind, key in AREAS.values():
        if kind != "relation":
            continue
        relation = relations.get(key)
        if relation is None or any(
            item.attrib["ref"] not in ways
            for item in relation.findall("member")
            if item.attrib["type"] == "way"
        ):
            add_root(existing_or_download(
                raw / f"siting-relation-{key}.osm", f"{OSM_API}/relation/{key}/full",
            ))

    xy = {
        key: TO_METERS(float(n.attrib["lon"]), float(n.attrib["lat"]))
        for key, n in nodes.items()
    }
    lines = {}
    for key, way in ways.items():
        ids = [n.attrib["ref"] for n in way.findall("nd")]
        if len(ids) >= 2 and all(node_id in xy for node_id in ids):
            lines[key] = LineString([xy[node_id] for node_id in ids])
    return nodes, xy, ways, relations, lines


def public_area(attributes):
    highway = attributes.get("highway", "").removesuffix("_link")
    if (
        highway in CAR_ROADS
        or attributes.get("access") in RESTRICTED_ACCESS
        or any(attributes.get(key) in VEHICLE_ACCESS for key in ("motorcar", "motor_vehicle", "vehicle"))
    ):
        return False
    return (
        attributes.get("place") == "square"
        or (highway in {"footway", "pedestrian"} and (
            attributes.get("area") == "yes" or attributes.get("type") == "multipolygon"
        ))
        or attributes.get("area:highway") in {"footway", "pedestrian"}
        or (attributes.get("leisure") == "park" and bool(attributes.get("name")))
    )


def area_geometry(kind, key, ways, relations, lines):
    if kind == "way":
        way = ways[key]
        attributes = tags(way)
        line = lines[key]
        if not public_area(attributes) or not line.is_ring:
            raise ValueError(f"OSM way {key} is no longer a closed public pedestrian area")
        return make_valid(Polygon(line)), way

    relation = relations[key]
    attributes = tags(relation)
    if not public_area(attributes):
        raise ValueError(f"OSM relation {key} is no longer a public pedestrian area")

    def rings(role):
        members = [
            lines[m.attrib["ref"]] for m in relation.findall("member")
            if m.attrib["type"] == "way" and m.attrib.get("role", "") in role
        ]
        return union_all(list(polygonize(members)))

    return make_valid(rings({"", "outer"}).difference(rings({"inner"}))), relation


def road_setback(attributes):
    highway = attributes.get("highway", "").removesuffix("_link")
    # Screen conservatively when a traffic lane width is absent. These buffers
    # are decision thresholds, never observations of roadway width.
    basic = 12.0 if highway in MAIN_ROADS else 6.0
    measured = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(?:m)?", attributes.get("width", ""))
    return max(basic, float(measured[1]) / 2 + 2) if measured else basic


def masks(nodes, xy, ways, lines):
    roads = []
    road_masks = []
    obstacle_masks = []
    for key, line in lines.items():
        attributes = tags(ways[key])
        highway = attributes.get("highway", "").removesuffix("_link")
        carries_vehicles = highway in CAR_ROADS or (
            highway in FOOT_ROADS
            and any(attributes.get(k) in VEHICLE_ACCESS for k in ("motorcar", "motor_vehicle", "vehicle"))
        )
        if carries_vehicles:
            roads.append(line)
            road_masks.append(line.buffer(road_setback(attributes)))
            if attributes.get("area") == "yes" and line.is_ring:
                road_masks.append(Polygon(line).buffer(2))
        if line.is_ring and attributes.get("area:highway", "").removesuffix("_link") in CAR_ROADS:
            road_masks.append(make_valid(Polygon(line)).buffer(2))
        if (attributes.get("railway") in {"tram", "rail", "light_rail"}
                and attributes.get("tunnel") not in {"yes", "building_passage"}):
            road_masks.append(line.buffer(5))
        if highway in FOOT_ROADS and attributes.get("area") != "yes":
            # Leave a schematic corridor around mapped paths.
            obstacle_masks.append(line.buffer(1.5))
        obstacle = (
            attributes.get("building") not in {None, "no"}
            or attributes.get("access") in RESTRICTED_ACCESS
            or any(attributes.get(k) in values for k, values in OBSTACLE_AREAS.items())
        )
        if obstacle and line.is_ring:
            obstacle_masks.append(Polygon(line).buffer(1.5))
    for key, node in nodes.items():
        attributes = tags(node)
        if (
            attributes.get("natural") == "tree"
            or attributes.get("amenity") in {"fountain", "bench"}
            or attributes.get("railway") == "subway_entrance"
            or attributes.get("barrier") in {"gate", "bollard", "lift_gate"}
        ):
            obstacle_masks.append(Point(*xy[key]).buffer(2))
    return STRtree(roads), STRtree(road_masks), STRtree(obstacle_masks)


def nearby_geometries(index, geometry, predicate="intersects"):
    return index.geometries.take(index.query(geometry, predicate=predicate))


def clear_geometry(area, road_masks, obstacle_masks):
    safe = area.buffer(-3)
    for index in (road_masks, obstacle_masks):
        safe = safe.difference(union_all(nearby_geometries(index, safe)))
    return safe


def red_atlas_cells(city):
    return STRtree([
        transform(make_valid(shape(feature["geometry"])), TO_METERS, interleaved=False)
        for feature in city["heat"]["features"]
        if feature["properties"]["temperature_c"] >= ATHENS_RED_SURFACE_TEMPERATURE_C
    ])


def output_coordinates(x, y):
    lon, lat = TO_LON_LAT(x, y)
    return round_coordinates(lon, 7), round_coordinates(lat, 7)


def compile_snapshot(atlas_path, raw, snapshot_date):
    city = json.loads(atlas_path.read_text(encoding="utf-8"))
    sites = {row["id"]: row for row in city["locations"]}
    nodes, xy, ways, relations, lines = load_geometry(raw)
    roads, road_masks, obstacle_masks = masks(nodes, xy, ways, lines)
    hot_cells = red_atlas_cells(city)
    city_limits = union_all([
        transform(make_valid(shape(feature["geometry"])), TO_METERS, interleaved=False)
        for feature in city["context"]["features"] if feature["properties"].get("kind") == "district"
    ])
    # The adjacent sculpture gallery has its own venue and managed grounds.
    gallery, _ = area_geometry("way", "489448988", ways, relations, lines)
    # /map includes whole OSM ways crossing a tile boundary. Only the area
    # within the requested tiles has surrounding street and obstacle coverage.
    coverage = union_all([
        transform(box(*map(float, bbox.split(","))), TO_METERS, interleaved=False)
        for bbox in BBOXES.values()
    ]).buffer(-25)
    candidates = {}
    blocked = []
    for site_id, (kind, key) in AREAS.items():
        site = sites.get(site_id)
        reference = (
            Point(*TO_METERS(site["longitude"], site["latitude"]))
            if site else None
        )
        area, element = area_geometry(kind, key, ways, relations, lines)
        if area.is_empty or (reference is not None and area.distance(reference) > 75):
            # A same-name OSM square can be a different public space.
            if reference is not None and len(nearby_geometries(road_masks, reference)):
                blocked.append(site_id)
            continue
        area = area.intersection(coverage).intersection(city_limits)
        if site_id == "siting-goudi-army-park":
            area = area.difference(gallery)
        safe = clear_geometry(area, road_masks, obstacle_masks)
        safe = safe.intersection(union_all(nearby_geometries(hot_cells, safe)))
        # Preserve the traffic and heat-cell boundaries following simplification
        # and rounding at seven decimal places for the web map.
        safe = safe.buffer(-0.25).simplify(0.15, preserve_topology=True)
        parts = [p for p in getattr(safe, "geoms", [safe]) if p.geom_type == "Polygon" and p.area >= 25]
        valid = [(p, maximum_inscribed_circle(p, tolerance=0.1)) for p in parts]
        valid = [(p, circle) for p, circle in valid if circle.length >= 2]
        if not valid:
            if reference is not None and len(nearby_geometries(road_masks, reference)):
                blocked.append(site_id)
            continue
        usable, circle = max(valid, key=lambda pair: (pair[0].area, pair[1].length))
        anchor = Point(circle.coords[0])
        lon, lat = TO_LON_LAT(anchor.x, anchor.y)
        candidates[site_id] = {
            "latitude": round(lat, 7),
            "longitude": round(lon, 7),
            "mapped_space": tags(element).get("name") or (site and site["name"]) or f"OSM {kind}/{key}",
            "available_area_m2": round(usable.area, 1),
            "edge_clearance_m": round(circle.length, 1),
            "road_distance_m": round(roads.geometries[roads.nearest(anchor)].distance(anchor), 1),
            "source_url": f"https://www.openstreetmap.org/{kind}/{key}",
            "osm_version": int(element.attrib["version"]),
            "geometry": mapping(transform(usable, output_coordinates, interleaved=False)),
        }
        if site_id in UNDERGROUND_CONSTRAINTS:
            note, url = UNDERGROUND_CONSTRAINTS[site_id]
            candidates[site_id].update(constraint_note=note, constraint_source_url=url)
    return {
        "source": "© OpenStreetMap contributors",
        "attribution_url": "https://www.openstreetmap.org/copyright",
        "snapshot_date": snapshot_date.isoformat(),
        "candidates": candidates,
        "roadway_reference_ids": sorted(blocked),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/siting"))
    parser.add_argument("--atlas", type=Path, default=Path("data/processed/athens.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/athens-siting.json"))
    parser.add_argument("--snapshot-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    args.raw.mkdir(parents=True, exist_ok=True)
    result = compile_snapshot(args.atlas, args.raw, args.snapshot_date)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for site_id, candidate in result["candidates"].items():
        print(site_id, candidate["available_area_m2"], candidate["edge_clearance_m"], candidate["road_distance_m"])


if __name__ == "__main__":
    main()
