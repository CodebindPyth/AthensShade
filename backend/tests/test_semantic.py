from fastapi.testclient import TestClient

from app import main
from app.semantic import ModelUnavailable, SemanticResult, keyword_search


def test_greek_lexical_lookup_preserves_citations():
    result, *_ = keyword_search("Πότε αποσβένεται η επένδυση και πόσο κοστίζει η συντήρηση;")
    assert "Ευρωπαϊκή Επιτροπή" in result.title
    assert result.url.startswith("https://ec.europa.eu/")
    assert not keyword_search("πρωτάθλημα ποδοσφαίρου")


def test_evidence_endpoint_uses_model_then_identifies_fallback(monkeypatch):
    record = SemanticResult("Τεκμήριο", "Επαληθευμένο περιεχόμενο", "https://example.org")
    monkeypatch.setattr(main, "semantic_search", lambda query: [record])
    with TestClient(main.create_app()) as client:
        response = client.post("/api/evidence-search", json={"query": "  σχολική ταράτσα  "})
        assert response.status_code == 200
        assert response.json() == {"method": "semantic", "results": [dict(
            title=record.title, description=record.description, url=record.url,
        )]}

        def unavailable(query):
            raise ModelUnavailable("Model offline")

        monkeypatch.setattr(main, "semantic_search", unavailable)
        response = client.post("/api/evidence-search", json={"query": "απόσβεση επένδυσης"})
        assert response.status_code == 200
        assert response.json()["method"] == "keywords"
        assert "Ευρωπαϊκή Επιτροπή" in response.json()["results"][0]["title"]
        for query in ("   ", "x" * 301):
            assert client.post("/api/evidence-search", json={"query": query}).status_code == 422
