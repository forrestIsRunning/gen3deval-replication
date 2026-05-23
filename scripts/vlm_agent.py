from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent, UserContent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

OutputT = TypeVar("OutputT")


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".glb":
        return "model/gltf-binary"
    return "application/octet-stream"


def image_content(path: Path) -> BinaryContent:
    return BinaryContent(
        data=path.read_bytes(),
        media_type=_media_type(path),
        identifier=path.name,
    )


def build_openai_agent(
    model_name: str,
    base_url: str,
    api_key: str,
    instructions: str,
    output_type: type[OutputT],
    temperature: float,
    max_tokens: int,
) -> Agent[None, OutputT]:
    model = OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url.rstrip("/"), api_key=api_key),
        settings=ModelSettings(temperature=temperature, max_tokens=max_tokens),
    )
    return Agent(
        model=model,
        output_type=output_type,
        instructions=instructions,
        retries=1,
        defer_model_check=True,
    )


def run_structured(
    *,
    model_name: str,
    base_url: str,
    api_key: str,
    instructions: str,
    output_type: type[OutputT],
    user_content: list[UserContent],
    temperature: float,
    max_tokens: int,
) -> OutputT:
    agent = build_openai_agent(
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        instructions=instructions,
        output_type=output_type,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    result = agent.run_sync(user_prompt=user_content)
    return result.output
