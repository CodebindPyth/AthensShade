import json
import logging
import os
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from .investment import FinancialAssumptions, appraise_investment
from .models import ExplainedIntervention, InterventionType, RankedLocation

LOGGER = logging.getLogger(__name__)
Option = tuple[str, str, str]

_ACTION_GUIDANCE: dict[InterventionType, tuple[Option, Option]] = {
    "tree_planting": (
        ("rooting", "Verify rooting space and overhead and underground utility clearance",
         "Έλεγξε τον χώρο ριζοβολίας και τα υπόγεια δίκτυα πριν ορίσεις τις θέσεις φύτευσης."),
        ("watering", "Verify irrigation and care across hot summers",
         "Προϋπολόγισε πότισμα και φροντίδα μέχρι να εδραιωθούν τα δέντρα και να αναπτύξουν κόμη."),
    ),
    "green_roof": (
        ("structure", "Obtain roof structural load and waterproofing assessments",
         "Ζήτησε έλεγχο φέρουσας ικανότητας και στεγάνωσης πριν κοστολογηθεί η τελική επιφάνεια του δώματος."),
        ("energy", "Verify roof energy savings using bills or measured consumption",
         "Χρησιμοποίησε καταναλώσεις πριν και μετά για να εκτιμήσεις την πραγματική εξοικονόμηση του δώματος."),
    ),
    "shade_structure": (
        ("siting", "Verify pedestrian clearance and the hours when the canopy shades users",
         "Έλεγξε τη διέλευση πεζών και τη σκιά στις ώρες αιχμής πριν οριστεί η θέση του σκιάστρου."),
        ("maintenance", "Obtain maintenance quotes for the installed structure",
         "Ζήτησε κόστος συντήρησης και αντικατάστασης του σκιάστρου για τον οικονομικό υπολογισμό."),
    ),
    "greenery": (
        ("water", "Verify drainage and irrigation supply on site",
         "Επιβεβαίωσε την αποστράγγιση και τη δυνατότητα άρδευσης πριν οριστικοποιηθεί η φύτευση."),
        ("species", "Choose plants that match water availability and the local heat",
         "Επίλεξε είδη που ταιριάζουν στην τοπική ζέστη και στη διαθέσιμη άρδευση."),
    ),
}


class CardAssumptions(BaseModel):
    annual_savings_eur: float
    annual_maintenance_eur: float
    horizon_years: int
    discount_rate_pct: float
    savings_delay_years: int


class PlanCard(BaseModel):
    source: Literal["local_model", "verified_template"]
    model: str | None
    explanation: str
    assumptions: CardAssumptions
    simple_payback_year: int | None
    discounted_payback_year: int | None
    required_annual_savings_eur: float | None


class _GuidanceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str


class LocalPlanCardEditor:
    def __init__(self) -> None:
        self._engine = os.getenv("ATHENSSHADE_LOCAL_ENGINE", "ollama")
        default_port = "8080" if self._engine == "llama_cpp" else "11434"
        self._port = os.getenv("ATHENSSHADE_LOCAL_PORT", default_port)
        default_model = "qwen2.5-0.5b" if self._engine == "llama_cpp" else "qwen2.5:0.5b"
        self._model = os.getenv("ATHENSSHADE_LOCAL_MODEL", default_model).strip()
        self._enabled = (
            self._engine in {"ollama", "llama_cpp"}
            and self._port.isascii()
            and self._port.isdecimal()
            and len(self._port) <= 5
            and 1 <= int(self._port) <= 65535
            and bool(self._model)
        )
        self._select_cached = lru_cache(maxsize=128)(self._select)
        self._lock = Lock()
        self._retry_at = 0.0

    def build(self, site: RankedLocation, items: list[ExplainedIntervention], strategy: str) -> PlanCard:
        # This classroom-style scenario is deliberately independent of historical or forecast savings.
        capital = sum((Decimal(str(item.cost_eur)) for item in items), start=Decimal(0))
        assumptions = FinancialAssumptions(
            annual_savings_eur=Decimal("2000.00"),
            annual_maintenance_eur=(capital * Decimal("0.02")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP,
            ),
            horizon_years=20,
            discount_rate_pct=Decimal("3"),
        )
        appraisal = appraise_investment(capital, assumptions)
        requires_inspection = any(item.feasibility == "requires_site_inspection" for item in items)
        context = (
            ("inspection", "Commission an on-site feasibility inspection first",
             "Ξεκίνα με αυτοψία για να επιβεβαιώσεις ότι η προτεινόμενη παρέμβαση χωρά και είναι εφαρμόσιμη.")
            if requires_inspection else
            ("budget", "Substitute real operating figures before reporting a payback",
             "Χρησιμοποίησε πραγματικές προσφορές, έξοδα συντήρησης και ετήσιες εξοικονομήσεις για την απόσβεση.")
        )
        options = {
            key: (label, text)
            for item in items
            for key, label, text in (*_ACTION_GUIDANCE[item.type], context)
        }
        scenario = json.dumps({
            "site": site.name,
            "hotspot": site.heat_hotspot,
            "tree_deficit": site.tree_deficit,
            "shade_deficit": site.shade_deficit,
            "site_inspection_required": requires_inspection,
            "goal": strategy,
            "actions": sorted({item.type for item in items}),
        }, ensure_ascii=False)
        choice = None
        if self._enabled:
            with self._lock:
                if monotonic() >= self._retry_at:
                    try:
                        choice = self._select_cached(
                            scenario, tuple((key, value[0]) for key, value in options.items()),
                        )
                    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                        self._retry_at = monotonic() + 15
                        LOGGER.info("Local planning model unavailable: %s", type(exc).__name__)

        # The model selects a relevant verified instruction. All rendered text and figures are controlled here.
        focus = choice or next(iter(options))
        return PlanCard(
            source="local_model" if choice else "verified_template",
            model=self._model if choice else None,
            explanation=f"{site.name}: {options[focus][1]}",
            assumptions=CardAssumptions(
                annual_savings_eur=float(assumptions.annual_savings_eur),
                annual_maintenance_eur=float(assumptions.annual_maintenance_eur),
                horizon_years=assumptions.horizon_years,
                discount_rate_pct=float(assumptions.discount_rate_pct),
                savings_delay_years=assumptions.savings_delay_years,
            ),
            simple_payback_year=appraisal.simple_payback_year,
            discounted_payback_year=appraisal.discounted_payback_year,
            required_annual_savings_eur=appraisal.required_annual_savings_eur,
        )

    def _select(self, scenario: str, options: tuple[tuple[str, str], ...]) -> str:
        system = (
            "Select the best next field verification or financial evidence step for the supplied "
            "heat adaptation site. Choose only one supplied focus ID. Return a JSON object with "
            "one 'focus' field."
        )
        choices = dict(options)
        prompt = f"Site data: {scenario}\nAvailable focus IDs: {json.dumps(choices)}"
        schema = {
            "type": "object",
            "properties": {"focus": {"type": "string", "enum": list(choices)}},
            "required": ["focus"],
            "additionalProperties": False,
        }
        shared = {"model": self._model, "stream": False}
        if self._engine == "llama_cpp":
            path = "/v1/chat/completions"
            payload = {
                **shared,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "site_focus", "schema": schema}},
                "temperature": 0,
                "max_tokens": 64,
            }
        else:
            path = "/api/generate"
            payload = {
                **shared,
                "system": system,
                "prompt": prompt,
                "format": schema,
                "options": {"temperature": 0, "num_predict": 64},
            }
        result = httpx.post(
            f"http://127.0.0.1:{self._port}{path}",
            json=payload,
            timeout=httpx.Timeout(15, connect=1),
            trust_env=False,
            follow_redirects=False,
        )
        result.raise_for_status()
        body = result.json()
        message = body["choices"][0]["message"]["content"] if self._engine == "llama_cpp" else body["response"]
        selected = _GuidanceSelection.model_validate_json(message)
        if selected.focus not in choices:
            raise ValueError("Local model selected an unknown focus")
        return selected.focus
