"""Build Greek map labels where official neighborhood polygons meet red atlas cells."""

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from shapely import STRtree, from_wkt, make_valid
from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = "0283af02-7783-4688-897b-7153da7ed2fd"
API = f"https://opendata.cityofathens.gr/api/3/action/datastore_search?resource_id={RESOURCE}&limit=200"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Use a saved answer from the official datastore.")
    parser.add_argument("--threshold", type=float, default=40)
    args = parser.parse_args()

    if args.snapshot:
        payload = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    else:
        with urlopen(API, timeout=30) as response:
            payload = json.load(response)
    atlas = json.loads((ROOT / "data/processed/athens.json").read_text(encoding="utf-8"))
    hot_features = [
        feature for feature in atlas["heat"]["features"]
        if (feature["properties"].get("temperature_c") or -273) >= args.threshold
    ]
    grid = STRtree([shape(feature["geometry"]) for feature in hot_features])
    labels = []
    for record in payload["result"]["records"]:
        if record["status"] != 1 or not record["polygon_geo"]:
            continue
        name = record["name"].strip()
        area = make_valid(from_wkt(record["polygon_geo"]))
        center = area.centroid
        candidates = []
        for index in grid.query(area, predicate="intersects"):
            overlap = area.intersection(grid.geometries[index])
            if overlap.area > 0:
                candidates.append((overlap, int(index)))
        if not name or not candidates:
            continue
        min_overlap = max(overlap.area for overlap, _ in candidates) * 0.60
        overlap, index = min(
            (pair for pair in candidates if pair[0].area >= min_overlap),
            key=lambda pair: pair[0].distance(center),
        )
        anchor = overlap.representative_point()
        label = {
            "name": name,
            "latitude": round(anchor.y, 7),
            "longitude": round(anchor.x, 7),
            "heat_c": hot_features[index]["properties"]["temperature_c"],
        }
        labels.append((area.area, label))

    labels.sort(key=lambda entry: (-entry[0], entry[1]["name"]))
    output = ROOT / "frontend/lib/hot-neighborhoods.json"
    rows = [json.dumps(label, ensure_ascii=False) for _, label in labels]
    output.write_text("[\n  " + ",\n  ".join(rows) + "\n]\n", encoding="utf-8")
    print(f"Wrote {len(rows)} labels at or above {args.threshold:g} C to {output.name}")


if __name__ == "__main__":
    main()
