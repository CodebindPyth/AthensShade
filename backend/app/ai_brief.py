import json
import logging
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .brief_evidence import BriefEvidence, BriefFact

LOGGER = logging.getLogger(__name__)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"
Choice = tuple[str, str]


class EvidenceLink(BaseModel):
    title: str
    url: str


class CityBrief(BaseModel):
    source: Literal["hosted_model", "verified_template"]
    model: str | None
    summary: str
    priorities: list[str]
    next_step: str
    evidence: list[EvidenceLink]
    availability: Literal["available", "not_configured", "provider_unavailable"]


class BriefSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority_ids: list[str] = Field(min_length=1, max_length=3)
    next_step_id: str


def public_choices(facts: tuple[BriefFact, ...]) -> tuple[Choice, ...]:
    return tuple((fact.id, fact.topic) for fact in facts)


class BriefEditor:
    def __init__(self, api_key: str | None) -> None:
        self._key = api_key.strip() if api_key else ""
        self._select_cached = lru_cache(maxsize=32)(self._select)
        self._lock = Lock()
        self._retry_at = 0.0

    def edit(self, evidence: BriefEvidence, strategy: str) -> CityBrief:
        availability: Literal["available", "not_configured", "provider_unavailable"] = (
            "provider_unavailable" if self._key else "not_configured"
        )
        selected = None
        if self._key:
            with self._lock:
                if monotonic() >= self._retry_at:
                    try:
                        selected = self._select_cached(
                            strategy, public_choices(evidence.priorities), public_choices(evidence.next_steps),
                        )
                        availability = "available"
                    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                        self._retry_at = monotonic() + 30
                        LOGGER.info("Hosted planning brief unavailable: %s", type(exc).__name__)

        facts = {fact.id: fact.text for fact in evidence.priorities}
        steps = {fact.id: fact.text for fact in evidence.next_steps}
        return CityBrief(
            source="hosted_model" if selected else "verified_template",
            model=GROQ_MODEL if selected else None,
            summary=evidence.summary,
            priorities=[facts[key] for key in selected.priority_ids] if selected else list(facts.values())[:3],
            next_step=steps[selected.next_step_id] if selected else next(iter(steps.values())),
            evidence=[EvidenceLink(title=item.title, url=item.url) for item in evidence.evidence],
            availability=availability,
        )

    def _select(
        self, strategy: str, priorities: tuple[Choice, ...], steps: tuple[Choice, ...],
    ) -> BriefSelection:
        # The provider receives topic labels and opaque IDs. Only verified application text is rendered.
        priority_ids = [id_ for id_, _ in priorities]
        step_ids = [id_ for id_, _ in steps]
        options = {
            "goal": {
                "immediate_shade": "άμεση σκίαση",
                "tree_priority": "φύτευση περισσότερων δέντρων σε θερμές θέσεις",
                "shade_and_rest": "φύτευση περισσότερων δέντρων σε θερμές θέσεις",
            }.get(strategy, "ισορροπημένο πλάνο"),
            "priorities": dict(priorities),
            "verification_steps": dict(steps),
        }
        response = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": GROQ_MODEL,
                "reasoning_effort": "low",
                "max_completion_tokens": 600,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Choose 1–3 distinct priority identifiers, in order, and one verification step "
                            "for a municipal heat-adaptation briefing. Match the goal and prefer different "
                            "topics. Return only identifiers from the supplied options."
                        ),
                    },
                    {"role": "user", "content": json.dumps(options, ensure_ascii=False)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "city_brief_order",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "priority_ids": {
                                    "type": "array",
                                    "items": {"type": "string", "enum": priority_ids},
                                    "minItems": 1,
                                    "maxItems": 3,
                                },
                                "next_step_id": {"type": "string", "enum": step_ids},
                            },
                            "required": ["priority_ids", "next_step_id"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
            timeout=12,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]["content"]
        selection = BriefSelection.model_validate_json(message)
        chosen_ids = set(selection.priority_ids)
        if (
            len(chosen_ids) != len(selection.priority_ids)
            or chosen_ids.difference(priority_ids)
            or selection.next_step_id not in step_ids
        ):
            raise ValueError("Provider selected unknown or repeated briefing identifiers")
        return selection
