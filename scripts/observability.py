#!/usr/bin/env python3
"""Opik observability for Gen3DEval VLM evaluation calls.

Provides tracing with image/3D attachments, feedback scores,
and automatic annotation queue routing for low-score assets.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
_configured = False


def safe_error(exc: BaseException) -> dict[str, str]:
    return {"type": exc.__class__.__name__, "message": str(exc)[:500]}


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required Opik setting: {name}")
    return value


def _import_opik():
    try:
        import opik
        from opik import Attachment, opik_context, track
    except ImportError as exc:
        raise RuntimeError("Opik is required. Run `uv sync` before scoring.") from exc
    return opik, track, opik_context, Attachment


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    opik, _, _, _ = _import_opik()
    base_url = _require_env("OPIK_BASE_URL")
    workspace = _require_env("OPIK_WORKSPACE")
    opik.configure(url_override=base_url, use_local=True, workspace=workspace, force=True)
    _configured = True


def trace_vlm_call(
    name: str,
    safe_input: dict[str, Any],
    operation: Callable[[], T],
    output_summary: Callable[[T, float], dict[str, Any]],
    after_trace: Callable[[str, T], None] | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    image_paths: list[Path] | None = None,
    glb_path: Path | None = None,
) -> T:
    """Trace a VLM call to Opik with image/3D attachments."""
    opik, track, opik_context, Attachment = _import_opik()
    _ensure_configured()
    project = _require_env("OPIK_PROJECT_NAME")

    @track(name=name, project_name=project)
    def _traced_op(input_data: dict) -> dict:
        attachments = []
        for p in (image_paths or []):
            if p.exists():
                mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
                attachments.append(Attachment(data=str(p), file_name=p.name, content_type=mime))
        if glb_path and glb_path.exists():
            attachments.append(Attachment(
                data=str(glb_path), file_name=glb_path.name, content_type="model/gltf-binary",
            ))

        started = time.perf_counter()
        result = operation()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        summary = output_summary(result, elapsed_ms)

        if attachments:
            opik_context.update_current_trace(attachments=attachments)
        opik_context.update_current_trace(
            metadata={**(metadata or {}), "model": model} if model else (metadata or {}),
            tags=[model] if model else [],
        )
        opik_context.update_current_span(model=model, output={"ok": True, **summary})
        trace_data = opik_context.get_current_trace_data()
        if after_trace and trace_data is not None and trace_data.id:
            after_trace(trace_data.id, result)
        return result

    out = _traced_op(input_data=safe_input)
    opik.flush_tracker()
    return out


def push_to_annotation_queue(
    trace_id: str,
    overall_score: float,
    threshold: float = 6.0,
    queue_name: str = "low-score-review",
) -> None:
    """Push current trace to annotation queue if overall score is below threshold."""
    if overall_score >= threshold:
        return
    opik, _, _, _ = _import_opik()
    _ensure_configured()
    project = _require_env("OPIK_PROJECT_NAME")

    # Build annotation queue name from project
    full_name = f"{project}:{queue_name}"
    client = opik.Opik()
    try:
        queue = client.create_traces_annotation_queue(
            name=full_name,
            description=f"Assets with overall < {threshold} for human review",
            project_name=project,
        )
    except Exception:
        queues = client.get_traces_annotation_queues(project_name=project)
        queue = next((q for q in queues if q.name == full_name), None)
        if queue is None:
            raise RuntimeError(f"Failed to create or find annotation queue: {full_name}")

    import httpx
    base_url = _require_env("OPIK_BASE_URL")
    response = httpx.put(
        f"{base_url.rstrip('/')}/v1/private/annotation_queue/{queue.id}/items",
        json={"trace_ids": [trace_id], "project_name": project},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    response.raise_for_status()


def log_feedback_scores(trace_id: str, scores: dict[str, float]) -> None:
    """Log per-dimension feedback scores to the current trace."""
    opik, _, _, _ = _import_opik()
    _ensure_configured()
    project = _require_env("OPIK_PROJECT_NAME")
    client = opik.Opik()
    client.log_traces_feedback_scores(
        project_name=project,
        scores=[{"id": trace_id, "name": dim, "value": val} for dim, val in scores.items()],
    )
