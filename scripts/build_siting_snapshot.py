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

from pyproj import Transformer
from shapely import make_valid, maximum_inscribed_circle, transform, union_all
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import polygonize


OSM_API = "https://api.openstreetmap.org/api/0.6"
BBOXES = {
    "avdi": "23.7175,37.9805,23.7225,37.985",
    "kotzia": "23.7245,37.980,23.731,37.9845",
    "west": "23.710,37.977,23.718,37.9875",
}
# Pair city-named sites with matching OSM public-square features. For the
# place=square ways, exclude vehicle routes before considering the interior.
AREAS = {
    "avdi": ("way", "765267680"),
    "dourouti": ("way", "765267679"),
    "kerameikos": ("relation", "2901516"),
    "kotzia": ("relation", "12250112"),
    "ramnes": ("way", "101515240"),
}
UNDERGROUND_CONSTRAINTS = {
    "kotzia": (
        "Κάτω από την πλατεία υπάρχει δημοτικός σταθμός στάθμευσης. "
        "Η στήριξη σκιάστρου απαιτεί έλεγχο φέρουσας πλάκας.",
        "https://www.daem.gr/ypogeia-parking/",
    ),
}
MAIN_ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "busway"}
CAR_ROADS = MAIN_ROADS | {"unclassified", "residential", "service", "track", "living_street", "road"}
FOOT_ROADS = {"footway", "pedestrian", "steps", "path", "cycleway"}
OBSTACLE_AREAS = {
    "amenity": {"fountain", "parking"},
    "leisure": {"playground", "pitch", "outdoor_seating", "sports_centre"},
    "natural": {"water"},
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
    roots = [
        existing_or_download(raw / f"siting-{name}.osm", f"{OSM_API}/map?bbox={bbox}")
        for name, bbox in BBOXES.items()
    ]
    roots.extend(
        existing_or_download(raw / f"siting-relation-{key}.osm", f"{OSM_API}/relation/{key}/full")
        for kind, key in AREAS.values() if kind == "relation"
    )
    nodes = {n.attrib["id"]: n for root in roots for n in root.findall("node")}
    xy = {
        key: TO_METERS(float(n.attrib["lon"]), float(n.attrib["lat"]))
        for key, n in nodes.items()
    }
    ways = {w.attrib["id"]: w for root in roots for w in root.findall("way")}
    relations = {r.attrib["id"]: r for root in roots for r in root.findall("relation")}
    lines = {}
    for key, way in ways.items():
        ids = [n.attrib["ref"] for n in way.findall("nd")]
        if len(ids) >= 2 and all(node_id in xy for node_id in ids):
            lines[key] = LineString([xy[node_id] for node_id in ids])
    return nodes, xy, ways, relations, lines


def area_geometry(kind, key, ways, relations, lines):
    if kind == "way":
        way = ways[key]
        attributes = tags(way)
        line = lines[key]
        if attributes.get("place") != "square" or not line.is_ring:
            raise ValueError(f"OSM way {key} is no longer a closed square")
        return make_valid(Polygon(line)), way

    relation = relations[key]
    attributes = tags(relation)
    if attributes.get("highway") != "pedestrian":
        raise ValueError(f"OSM relation {key} is no longer a pedestrian area")

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
        if highway in CAR_ROADS:
            roads.append(line)
            road_masks.append(line.buffer(road_setback(attributes)))
            if attributes.get("area") == "yes" and line.is_ring:
                road_masks.append(Polygon(line).buffer(2))
        if highway in FOOT_ROADS and attributes.get("area") != "yes":
            # Leave a schematic corridor around mapped paths.
            obstacle_masks.append(line.buffer(1.5))
        obstacle = (
            attributes.get("building") not in {None, "no"}
            or attributes.get("access") in {"private", "customers", "no"}
            or any(attributes.get(k) in values for k, values in OBSTACLE_AREAS.items())
        )
        if obstacle and line.is_ring:
            obstacle_masks.append(Polygon(line).buffer(1.5))
    for key, node in nodes.items():
        attributes = tags(node)
        if attributes.get("natural") == "tree" or attributes.get("amenity") in {"fountain", "bench"}:
            obstacle_masks.append(Point(*xy[key]).buffer(2))
    return union_all(roads), union_all(road_masks), union_all(obstacle_masks)


def compile_snapshot(atlas_path, raw, snapshot_date):
    city = json.loads(atlas_path.read_text(encoding="utf-8"))
    sites = {row["id"]: row for row in city["locations"]}
    nodes, xy, ways, relations, lines = load_geometry(raw)
    roads, road_masks, obstacle_masks = masks(nodes, xy, ways, lines)
    candidates = {}
    blocked = []
    for site_id, (kind, key) in AREAS.items():
        site = sites[site_id]
        reference = Point(*TO_METERS(site["longitude"], site["latitude"]))
        area, element = area_geometry(kind, key, ways, relations, lines)
        if area.is_empty or area.distance(reference) > 75:
            # A same-name OSM square can be a different public space.
            if road_masks.covers(reference):
                blocked.append(site_id)
            continue
        safe = area.buffer(-3).difference(road_masks).difference(obstacle_masks)
        parts = [p for p in getattr(safe, "geoms", [safe]) if p.geom_type == "Polygon" and p.area >= 25]
        valid = [(p, maximum_inscribed_circle(p, tolerance=0.1)) for p in parts]
        valid = [(p, circle) for p, circle in valid if circle.length >= 2]
        if not valid:
            if road_masks.covers(reference):
                blocked.append(site_id)
            continue
        usable, circle = max(valid, key=lambda pair: (pair[0].area, pair[1].length))
        anchor = Point(circle.coords[0])
        lon, lat = TO_LON_LAT(anchor.x, anchor.y)
        candidates[site_id] = {
            "latitude": round(lat, 7),
            "longitude": round(lon, 7),
            "mapped_space": tags(element).get("name", site["name"]),
            "available_area_m2": round(usable.area, 1),
            "edge_clearance_m": round(circle.length, 1),
            "road_distance_m": round(roads.distance(anchor), 1),
            "source_url": f"https://www.openstreetmap.org/{kind}/{key}",
            "osm_version": int(element.attrib["version"]),
            "geometry": mapping(transform(usable.simplify(0.2, preserve_topology=True), TO_LON_LAT, interleaved=False)),
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
