import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import monotonic
from typing import Annotated, Literal

import httpx
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError

from .models import Source

LOGGER = logging.getLogger(__name__)
DATASTORE = "https://opendata.cityofathens.gr/api/3/action/datastore_search"
RESOURCE = "a84cabca-bd0c-434d-8bee-21c082183442"
SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "processed" / "air-stations.json"
REGISTRY = "https://opendata.cityofathens.gr/dataset/env-stations-registry"
AIR_SOURCE = Source(
    id="athens-air-stations",
    title="Athens Smart Neighbourhood · Ωριαίες μετρήσεις αέρα",
    url="https://data.gov.gr/data-service/cityofathens-ds-415dd022213b",
    period="Τελευταία διαθέσιμη καταγραφή ανά σταθμό",
    kind="air_observation",
    license="CC BY 4.0",
)
# The registry joins station IDs to named places. Map anchors are the matching
# municipal pilot sites, not instrument coordinates.
PILOT_STATIONS = {
    67: ("attiki", "Πλατεία Αττικής"),
    102: ("fokionos", "Φωκίωνος Νέγρη"),
    103: ("agios-panteleimonas", "Πλατεία Αγίου Παντελεήμονα"),
    107: ("amerikis", "Πλατεία Αμερικής"),
    110: ("avdi", "Πλατεία Αυδή / Δημοτική Πινακοθήκη"),
}
Temperature = Annotated[float, Field(ge=-70, le=70, allow_inf_nan=False)]
Humidity = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class Measurement(BaseModel):
    station_id: int
    observed_at: AwareDatetime
    temperature_c: Temperature
    humidity_pct: Humidity | None = None


class AirReading(Measurement):
    location_id: str
    station_name: str
    origin: Literal["api", "cache", "snapshot"]


class AirResponse(BaseModel):
    readings: list[AirReading]
    source_url: str
    registry_url: str


MEASUREMENTS = TypeAdapter(list[Measurement])


def fetch_measurements() -> dict[int, Measurement]:
    response = httpx.get(
        DATASTORE,
        params={
            "resource_id": RESOURCE,
            "limit": 200,
            "sort": "interval_timestamp desc",
            "fields": "station_id,timestamp,temperature,humidity",
            "filters": json.dumps({"station_id": list(PILOT_STATIONS)}),
            "include_total": "false",
        },
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") if isinstance(payload, dict) and payload.get("success") else None
    rows = result.get("records") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Invalid Athens Smart Neighbourhood response")

    latest: dict[int, Measurement] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("station_id")) is not int:
            continue
        station_id = row["station_id"]
        timestamp = row.get("timestamp")
        temperature = row.get("temperature")
        if station_id not in PILOT_STATIONS or not isinstance(timestamp, str) or type(temperature) not in (int, float):
            continue
        # CKAN emits UTC timestamps without a suffix for these fields.
        try:
            observed_at = datetime.fromisoformat(timestamp)
            observed_at = observed_at.replace(tzinfo=UTC) if observed_at.tzinfo is None else observed_at.astimezone(UTC)
            humidity = row.get("humidity")
            measurement = Measurement(
                station_id=station_id,
                observed_at=observed_at,
                temperature_c=temperature,
                humidity_pct=humidity if type(humidity) in (int, float) and 0 <= humidity <= 100 else None,
            )
        except (ValueError, TypeError):
            continue
        if station_id not in latest or measurement.observed_at > latest[station_id].observed_at:
            latest[station_id] = measurement
    return latest


class AirFeed:
    def __init__(self, snapshot: Path = SNAPSHOT) -> None:
        self._lock = Lock()
        self._expires = 0.0
        self._response: list[AirReading] = []
        self._cached: dict[int, Measurement] = {}
        try:
            self._snapshot = {row.station_id: row for row in MEASUREMENTS.validate_json(snapshot.read_bytes())}
        except (OSError, ValidationError):
            self._snapshot = {}

    def latest(self) -> AirResponse:
        with self._lock:
            if monotonic() >= self._expires:
                self._refresh()
            return AirResponse(
                readings=self._response,
                source_url="https://opendata.cityofathens.gr/dataset/env-all-stations",
                registry_url=REGISTRY,
            )

    def _refresh(self) -> None:
        try:
            fresh = fetch_measurements()
        except (httpx.HTTPError, ValueError) as exc:
            LOGGER.info("Athens Smart Neighbourhood data unavailable: %s", type(exc).__name__)
            fresh = {}

        readings: list[AirReading] = []
        for station_id, (location_id, name) in PILOT_STATIONS.items():
            candidates = [
                ("api", fresh.get(station_id)),
                ("cache", self._cached.get(station_id)),
                ("snapshot", self._snapshot.get(station_id)),
            ]
            available = [(origin, measurement) for origin, measurement in candidates if measurement is not None]
            if not available:
                continue
            origin, measurement = max(available, key=lambda item: item[1].observed_at)
            if origin == "api":
                self._cached[station_id] = measurement
            readings.append(AirReading(
                **measurement.model_dump(), location_id=location_id, station_name=name, origin=origin,
            ))

        self._response = readings
        self._expires = monotonic() + (600 if len(fresh) == len(PILOT_STATIONS) else 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the Athens municipal air-observation snapshot.")
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    target = parser.parse_args().output
    latest = fetch_measurements()
    if latest.keys() != PILOT_STATIONS.keys():
        parser.exit(1, "Incomplete station coverage. The previous snapshot was kept.\n")
    body = MEASUREMENTS.dump_json([latest[site] for site in PILOT_STATIONS], indent=2) + b"\n"
    with NamedTemporaryFile(dir=target.parent, delete=False) as file:
        pending = Path(file.name)
        try:
            file.write(body)
        except OSError:
            file.close()
            pending.unlink(missing_ok=True)
            raise
    try:
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
