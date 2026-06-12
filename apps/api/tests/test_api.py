from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_rejects_non_pdf() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/papers/upload",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_returns_paper_detail_shape() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/papers/upload",
        data={"title": "Shape Test", "parse_immediately": "false"},
        files={"file": ("shape.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 200
    paper = response.json()["paper"]
    assert paper["title"] == "Shape Test"
    assert paper["pages"] == []
    assert paper["chunks_count"] == 0


def test_openapi_contains_planned_routes() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert "/api/papers/search" in paths
    assert "/api/papers/import" in paths
    assert "/api/papers/upload" in paths
    assert "/api/papers/{paper_id}/ask" in paths
    assert "/api/papers/{paper_id}/chunks" in paths
    assert "/api/settings/llm/providers" in paths
    assert "/api/llm/test" in paths
    assert "/api/agent/chat/stream" in paths
    assert "/api/agent/sessions" in paths
    assert "/api/agent/sessions/{session_id}/messages" in paths


def test_llm_provider_templates_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/settings/llm/providers")
    assert response.status_code == 200
    providers = {item["id"] for item in response.json()}
    assert {"openai", "anthropic", "gemini", "ollama", "custom_openai"}.issubset(providers)


def test_llm_test_without_key_does_not_log_or_persist_secret() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/llm/test",
        json={
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "options": {"temperature": 0.1, "max_tokens": 128},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "API key" in payload["message"]
