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


def _new_client():
    opik, _, _, _ = _import_opik()
    _ensure_configured()
    project = _require_env("OPIK_PROJECT_NAME")
    workspace = _require_env("OPIK_WORKSPACE")
    base_url = _require_env("OPIK_BASE_URL")
    return opik.Opik(
        project_name=project,
        workspace=workspace,
        host=base_url,
        batching=False,
    )


def _attachment_specs(image_paths: list[Path] | None, glb_path: Path | None) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for path in image_paths or []:
        if not path.exists():
            continue
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        specs.append({"path": str(path), "file_name": path.name, "content_type": mime})
    if glb_path and glb_path.exists():
        specs.append({
            "path": str(glb_path),
            "file_name": glb_path.name,
            "content_type": "model/gltf-binary",
        })
    return specs


def _status_ok(**extra: Any) -> dict[str, Any]:
    return {"ok": True, **extra}


def _status_err(exc: BaseException, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": safe_error(exc), **extra}


def trace_vlm_call(
    name: str,
    safe_input: dict[str, Any],
    operation: Callable[[], T],
    output_summary: Callable[[T, float], dict[str, Any]],
    after_trace: Callable[[str, T], Any] | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    image_paths: list[Path] | None = None,
    glb_path: Path | None = None,
    observability_sink: Callable[[dict[str, Any]], None] | None = None,
) -> T:
    """Trace a VLM call to Opik without blocking the VLM request on backend instability."""
    _import_opik()
    project = _require_env("OPIK_PROJECT_NAME")
    attachments = _attachment_specs(image_paths, glb_path)
    trace_metadata = {**(metadata or {}), "model": model} if model else dict(metadata or {})
    trace_tags = [model] if model else []
    obs: dict[str, Any] = {
        "enabled": True,
        "project": project,
        "trace_id": None,
        "trace": _status_ok(skipped=True),
        "span": _status_ok(skipped=True),
        "attachments": _status_ok(attempted=len(attachments), uploaded=0, failed=[]),
        "flush": _status_ok(skipped=True),
        "post_trace": _status_ok(skipped=True),
    }

    def publish() -> None:
        if observability_sink is not None:
            observability_sink(obs)

    def run_operation() -> tuple[T, dict[str, Any]]:
        started = time.perf_counter()
        result = operation()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return result, output_summary(result, elapsed_ms)

    client = None
    trace = None
    span = None
    try:
        client = _new_client()
        trace = client.trace(
            name=name,
            input=safe_input,
            metadata=trace_metadata,
            tags=trace_tags,
            project_name=project,
        )
        obs["trace_id"] = trace.id
        obs["trace"] = _status_ok(trace_id=trace.id)
        if model:
            span = trace.span(
                name=name,
                type="llm",
                input=safe_input,
                metadata={"model": model},
                model=model,
            )
            obs["span"] = _status_ok()
    except Exception as exc:
        obs["trace"] = _status_err(exc)
        result, _ = run_operation()
        publish()
        return result

    try:
        result, summary = run_operation()
    except Exception as exc:
        if span is not None:
            try:
                span.end(model=model, error_info=safe_error(exc))
            except Exception as span_exc:
                obs["span"] = _status_err(span_exc)
        try:
            trace.end(
                metadata=trace_metadata,
                tags=trace_tags,
                error_info=safe_error(exc),
            )
        except Exception as trace_exc:
            obs["trace"] = _status_err(trace_exc, trace_id=obs["trace_id"])
        if client is not None:
            try:
                client.end(timeout=30, flush=True)
                obs["flush"] = _status_ok()
            except Exception as flush_exc:
                obs["flush"] = _status_err(flush_exc)
        publish()
        raise

    if span is not None:
        try:
            span.end(model=model, output={"ok": True, **summary})
        except Exception as exc:
            obs["span"] = _status_err(exc)
    try:
        trace.end(
            metadata=trace_metadata,
            tags=trace_tags,
            output={"ok": True, **summary},
        )
        obs["trace"] = _status_ok(trace_id=trace.id)
    except Exception as exc:
        obs["trace"] = _status_err(exc, trace_id=obs["trace_id"])

    if client is not None:
        try:
            client.end(timeout=30, flush=True)
            obs["flush"] = _status_ok()
        except Exception as exc:
            obs["flush"] = _status_err(exc)

    if obs["trace_id"] and attachments:
        upload_client = client.get_attachment_client()
        failed: list[dict[str, Any]] = []
        uploaded = 0
        for attachment in attachments:
            try:
                upload_client.upload_attachment(
                    project_name=project,
                    entity_type="trace",
                    entity_id=obs["trace_id"],
                    file_path=attachment["path"],
                    file_name=attachment["file_name"],
                    mime_type=attachment["content_type"],
                )
                uploaded += 1
            except Exception as exc:
                failed.append({
                    "file_name": attachment["file_name"],
                    "path": attachment["path"],
                    "error": safe_error(exc),
                })
        obs["attachments"] = {
            "ok": len(failed) == 0,
            "attempted": len(attachments),
            "uploaded": uploaded,
            "failed": failed,
        }

    if after_trace and obs["trace_id"]:
        try:
            post_trace = after_trace(obs["trace_id"], result)
            obs["post_trace"] = _status_ok(result=post_trace)
        except Exception as exc:
            obs["post_trace"] = _status_err(exc)

    publish()
    return result


def push_to_annotation_queue(
    trace_id: str,
    overall_score: float,
    threshold: float = 6.0,
    queue_name: str = "low-score-review",
) -> dict[str, Any]:
    """Push current trace to annotation queue if overall score is below threshold."""
    if overall_score >= threshold:
        return _status_ok(skipped=True, reason="score_above_threshold")
    opik, _, _, _ = _import_opik()
    project = _require_env("OPIK_PROJECT_NAME")
    client = _new_client()

    full_name = f"{project}:{queue_name}"
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
            return _status_err(RuntimeError(f"Failed to create or find annotation queue: {full_name}"))

    try:
        client.rest_client.annotation_queues.add_items_to_annotation_queue(
            id=queue.id,
            ids=[trace_id],
        )
        client.end(timeout=30, flush=True)
        return _status_ok(queue_id=queue.id, queue_name=full_name, trace_id=trace_id)
    except Exception as exc:
        return _status_err(exc, queue_id=queue.id, queue_name=full_name, trace_id=trace_id)


def log_feedback_scores(trace_id: str, scores: dict[str, float]) -> dict[str, Any]:
    """Log per-dimension feedback scores to the current trace."""
    _import_opik()
    project = _require_env("OPIK_PROJECT_NAME")
    client = _new_client()
    try:
        client.log_traces_feedback_scores(
            project_name=project,
            scores=[{"id": trace_id, "name": dim, "value": val} for dim, val in scores.items()],
        )
        client.end(timeout=30, flush=True)
        return _status_ok(trace_id=trace_id, count=len(scores))
    except Exception as exc:
        return _status_err(exc, trace_id=trace_id, count=len(scores))
