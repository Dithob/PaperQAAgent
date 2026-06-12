import respx
from httpx import Response

from app.models.schemas import LLMConfig
from app.services.llm_providers import chat, provider_templates


def test_provider_templates_cover_planned_providers() -> None:
    providers = {template.id for template in provider_templates()}
    assert {
        "openai",
        "azure_openai",
        "anthropic",
        "gemini",
        "deepseek",
        "qwen",
        "moonshot",
        "zhipu",
        "openrouter",
        "ollama",
        "custom_openai",
    }.issubset(providers)


@respx.mock
async def test_openai_compatible_payload_shape() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )
    config = LLMConfig(
        provider="openai",
        model="gpt-test",
        api_key="secret",
        base_url="https://api.openai.com/v1",
    )

    result = await chat(config, "System", "User")

    assert result.content == "OK"
    assert route.called
    payload = route.calls[0].request.content.decode("utf-8")
    assert "gpt-test" in payload
    assert "System" in payload
    assert "User" in payload
    assert "secret" not in payload
