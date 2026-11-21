import json
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from app import air
from app.main import create_app


def test_ckan_uses_actual_utc_measurement_and_skips_invalid_temperatures(monkeypatch):
    older = {"station_id": 67, "timestamp": "2026-11-21T08:00:00", "temperature": 19.7, "humidity": 55}
    newer = dict(older, timestamp="2026-11-21T09:00:00", temperature=21.49, humidity=104)

    def get(url, *, params, timeout):
        assert url == air.DATASTORE
        assert params["resource_id"] == air.RESOURCE
        assert set(json.loads(params["filters"])["station_id"]) == set(air.PILOT_STATIONS)
        assert timeout == 5
        rows = [newer, older, dict(older, station_id=102, temperature=True), dict(older, station_id=103, temperature=None)]
        return httpx.Response(
            200, json={"success": True, "result": {"records": rows}}, request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(air.httpx, "get", get)
    result = air.fetch_measurements()
    assert set(result) == {67}
    assert result[67].observed_at == datetime(2026, 11, 21, 9, tzinfo=UTC)
    assert result[67].temperature_c == 21.49
    assert result[67].humidity_pct is None


def test_feed_preserves_snapshot_and_uses_api_cache(monkeypatch, tmp_path):
    older = air.Measurement(station_id=67, observed_at="2026-11-20T09:00:00Z", temperature_c=19)
    newer = air.Measurement(station_id=67, observed_at="2026-11-21T09:00:00Z", temperature_c=21.49)
    snapshot = tmp_path / "air.json"
    snapshot.write_bytes(air.MEASUREMENTS.dump_json([older]))
    seen = []
    now = [1.0]
    monkeypatch.setattr(air, "monotonic", lambda: now[0])

    def fetch():
        seen.append(True)
        if len(seen) == 2:
            return {67: newer}
        raise httpx.ConnectError("test outage")

    monkeypatch.setattr(air, "fetch_measurements", fetch)
    feed = air.AirFeed(snapshot)
    assert feed.latest().readings[0].origin == "snapshot"
    assert feed.latest().readings[0].observed_at == older.observed_at
    assert len(seen) == 1
    now[0] += 61
    assert feed.latest().readings[0].origin == "api"
    now[0] += 61
    cached = feed.latest().readings[0]
    assert (cached.origin, cached.observed_at, cached.location_id) == ("cache", newer.observed_at, "attiki")


def test_air_route_survives_missing_main_dataset(monkeypatch, tmp_path):
    measurement = air.Measurement(station_id=67, observed_at="2026-11-21T09:00:00Z", temperature_c=21.49)
    monkeypatch.setattr(air, "fetch_measurements", lambda: {67: measurement})
    with TestClient(create_app(tmp_path / "missing.json")) as client:
        response = client.get("/api/air-observations")
    assert response.status_code == 200
    assert next(row for row in response.json()["readings"] if row["station_id"] == 67)["origin"] == "api"
