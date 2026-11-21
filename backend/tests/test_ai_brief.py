import json

import httpx

from app import ai_brief
from app.brief_evidence import BriefEvidence, BriefFact, BriefSource


EVIDENCE = BriefEvidence(
    summary="Δημοτικό κόστος 96.796,60 €.",
    priorities=(
        BriefFact("priority-a", "Σκίαση 220 m² κοντά στην Πλατεία Αυδή.", "άμεση σκίαση"),
        BriefFact("priority-b", "Εκτίμηση 460 m² φυτεμένου δώματος.", "φυτεμένα δώματα"),
    ),
    next_steps=(BriefFact("verify-a", "Επιβεβαίωσε τις διαθέσιμες θέσεις.", "αυτοψία"),),
    evidence=(BriefSource("Δήμος Αθηναίων", "https://www.cityofathens.gr/"),),
)


def test_missing_key_renders_verified_brief_without_network(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("The no-key demo must not call a hosted model")

    monkeypatch.setattr(ai_brief.httpx, "post", unexpected)
    result = ai_brief.BriefEditor(None).edit(EVIDENCE, "balanced")
    assert (result.source, result.availability) == ("verified_template", "not_configured")
    assert result.priorities == [fact.text for fact in EVIDENCE.priorities]


def test_hosted_model_ranks_ids_and_only_receives_topics(monkeypatch):
    requests = []

    def post(url, *, headers, json, timeout):
        requests.append(json)
        assert url == ai_brief.GROQ_URL
        assert headers["Authorization"] == "Bearer test-only-key"
        assert json["response_format"]["json_schema"]["strict"] is True
        content = json["messages"][1]["content"]
        assert "άμεση σκίαση" in content and "φυτεμένα δώματα" in content
        assert all(value not in content for value in ("96.796", "220", "460", "Αυδή", "cityofathens"))
        return provider_response({"priority_ids": ["priority-b", "priority-a"], "next_step_id": "verify-a"})

    monkeypatch.setattr(ai_brief.httpx, "post", post)
    editor = ai_brief.BriefEditor("test-only-key")
    result = editor.edit(EVIDENCE, "immediate_shade")
    assert (result.source, result.availability, result.model) == ("hosted_model", "available", ai_brief.GROQ_MODEL)
    assert result.priorities == [EVIDENCE.priorities[1].text, EVIDENCE.priorities[0].text]
    assert result.next_step == EVIDENCE.next_steps[0].text
    assert result.summary == EVIDENCE.summary
    assert editor.edit(EVIDENCE, "immediate_shade") == result
    assert len(requests) == 1


def test_unknown_model_claims_and_quota_failure_keep_verified_text(monkeypatch):
    for response in (
        provider_response({"priority_ids": ["fake"], "next_step_id": "verify-a"}),
        provider_response({"priority_ids": ["priority-a", "priority-a"], "next_step_id": "verify-a"}),
        httpx.Response(429, request=httpx.Request("POST", ai_brief.GROQ_URL)),
    ):
        monkeypatch.setattr(ai_brief.httpx, "post", lambda *args, **kwargs: response)
        result = ai_brief.BriefEditor("test-only-key").edit(EVIDENCE, "balanced")
        assert result.source == "verified_template" and result.availability == "provider_unavailable"
        assert result.priorities == [fact.text for fact in EVIDENCE.priorities]


def provider_response(answer):
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps(answer)}}]},
        request=httpx.Request("POST", ai_brief.GROQ_URL),
    )
