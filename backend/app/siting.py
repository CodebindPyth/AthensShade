"""Read and apply the offline pedestrian siting screen."""

from functools import lru_cache
from math import pi
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError


SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "athens-siting.json"
SitingStatus = Literal["candidate", "road_conflict", "insufficient_space", "unverified"]


class SitingEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    mapped_space: str
    available_area_m2: float = Field(gt=0)
    edge_clearance_m: float = Field(gt=0)
    road_distance_m: float = Field(gt=0)
    source_url: HttpUrl
    geometry: dict[str, Any]
    constraint_note: str | None = None
    constraint_source_url: HttpUrl | None = None


class SitingAssessment(BaseModel):
    status: SitingStatus
    message: str
    evidence: SitingEvidence | None = None


class SitingSnapshot(BaseModel):
    candidates: dict[str, SitingEvidence] = Field(default_factory=dict)
    roadway_reference_ids: set[str] = Field(default_factory=set)


@lru_cache(maxsize=4)
def _load_snapshot(path: Path) -> SitingSnapshot:
    try:
        return SitingSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, UnicodeError):
        # Missing or unreadable evidence must not allow a proposal inside a roadway.
        return SitingSnapshot()


def load_siting(path: Path = SNAPSHOT_PATH) -> dict[str, SitingEvidence]:
    return dict(_load_snapshot(path).candidates)


def assess_siting(
    location_id: str,
    intervention_type: str,
    shelter_shade_m2: float | None = None,
    *,
    snapshot_path: Path = SNAPSHOT_PATH,
) -> SitingAssessment:
    snapshot = _load_snapshot(snapshot_path)
    evidence = snapshot.candidates.get(location_id)
    if evidence is None:
        if location_id in snapshot.roadway_reference_ids:
            return SitingAssessment(
                status="road_conflict",
                message="Το σημείο αναφοράς είναι κοντά σε οδό οχημάτων και δεν εντοπίστηκε κατάλληλος χώρος πεζών.",
            )
        return SitingAssessment(
            status="unverified",
            message="Δεν διαθέτουμε ζώνη πεζών με επαρκή γεωμετρική τεκμηρίωση για τη χωροθέτηση.",
        )

    if intervention_type in {"tree_planting", "greenery"} and evidence.constraint_note:
        return SitingAssessment(
            status="unverified",
            message="Η φύτευση στο έδαφος χρειάζεται μελέτη ριζικού χώρου λόγω τεκμηριωμένης υπόγειας κατασκευής.",
            evidence=evidence,
        )

    minimum_area = 25.0
    minimum_edge_clearance = 2.0
    centered_area = evidence.available_area_m2
    if intervention_type == "shade_structure":
        minimum_area = max(36.0, shelter_shade_m2 or 0.0)
        minimum_edge_clearance = 3.0
        # Favor room around the mapped anchor as well as total usable area.
        centered_area = min(centered_area, pi * evidence.edge_clearance_m ** 2)
    if centered_area < minimum_area or evidence.edge_clearance_m < minimum_edge_clearance:
        return SitingAssessment(
            status="insufficient_space",
            message="Η τεκμηριωμένη ζώνη πεζών δεν καλύπτει το ελάχιστο γεωμετρικό όριο του σεναρίου.",
            evidence=evidence,
        )
    return SitingAssessment(
        status="candidate",
        message="Υποψήφια ζώνη σε χαρτογραφημένο χώρο πεζών, μετά από αποκλεισμό των γειτονικών οδών. "
        "Επιβεβαίωσε ελεύθερη διέλευση, δίκτυα και πραγματικές διαστάσεις στην αυτοψία.",
        evidence=evidence,
    )
