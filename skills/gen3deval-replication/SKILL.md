---
name: gen3deval-replication
description: Use this skill when working in the gen3deval-replication repo to run or modify the 3D evaluation pipeline, FastAPI dashboard, Objaverse manifests, Blender rendering, geometry metrics, and OpenAI-compatible VLM scoring.
metadata:
  short-description: Run and maintain the Gen3DEval-style 3D evaluation POC
---

# Gen3DEval Replication Skill

## Scope

This skill applies to `/Users/xiaoxia/Projects/experiments/gen3deval-replication`.

The project is a public-data Gen3DEval-style 3D evaluation pipeline:

- Objaverse-LVIS assets;
- geometry metrics from mesh files;
- Blender RGB/Normal multi-view renders;
- VLM scoring through LiteLLM/OpenAI-compatible chat completions;
- FastAPI dashboard with static frontend.

## Golden Rules

- Use `uv`; do not introduce plain `pip` or ad hoc virtualenv instructions.
- Do not commit `.env`, `data/results/`, `data/renders/`, downloaded PDFs, or Objaverse assets.
- Do not use mock data for scoring. VLM scores must come from real rendered images and real LiteLLM calls.
- Keep the current VLM model list to:
  - `qwen3-vl-235b-a22b-instruct`
  - `qwen3-vl-235b-a22b-thinking`
- Treat the frontend as a view over `manifest + uid + model`; charts must not silently mix unrelated models or datasets.
- Geometry metrics are computed directly; VLM is for semantic/visual fidelity; LLM is only for summarizing existing evidence.

## Environment

From the repo root:

```bash
uv sync
cp .env.example .env
```

Required `.env` keys:

```bash
LITELLM_BASE_URL=http://120.48.38.233:4000
LITELLM_API_KEY=your-key
GEN3D_VLM_MODEL=qwen3-vl-235b-a22b-thinking
```

If network access needs the local proxy:

```bash
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080
```

## Run Backend and Frontend

The frontend is served by FastAPI. There is no separate npm frontend server.

```bash
uv run uvicorn web.app:app --host 127.0.0.1 --port 7860 --reload
```

Open:

```text
http://127.0.0.1:7860
```

If port 7860 is busy:

```bash
lsof -nP -iTCP:7860 -sTCP:LISTEN
uv run uvicorn web.app:app --host 127.0.0.1 --port 7861 --reload
```

## Frontend Workflow

Use the UI in this order:

1. Select `Manifest`.
2. Select one asset `uid`.
3. Select VLM model.
4. Click `Run Selected VLM`.

Expected panels:

- 3D GLB preview;
- RGB/Normal multi-view renders;
- VLM multidimensional score chart;
- geometry face-count distribution;
- render verification table;
- computable geometry metrics table;
- arXiv method-to-implementation mapping.

## Manifests

- `data/processed/manifest_120.jsonl`: main 120 real assets.
- `data/processed/manifest_render10.jsonl`: 10 real assets with RGB/Normal renders; best for UI VLM testing.
- `data/processed/manifest_render1.jsonl`: one-asset debug manifest.
- `data/processed/manifest_smoke3.jsonl`: Blender smoke test.
- `data/processed/pairs_smoke3.jsonl`: pairwise/ELO smoke test, not a single-asset VLM manifest.
- `data/processed/sample_manifest.jsonl`: old demo; not official evaluation data.

## Data Pipeline

Prepare and download assets:

```bash
uv run python scripts/prepare_objaverse_sample.py --num-assets 120
uv run python scripts/download_objaverse_assets.py --manifest data/processed/manifest_120.jsonl
```

Compute geometry:

```bash
uv run python scripts/compute_geometry_metrics.py \
  --manifest data/processed/manifest_120.jsonl
```

Render with Blender:

```bash
blender -b --python scripts/render_blender.py -- \
  --manifest data/processed/manifest_render10.jsonl \
  --output-dir data/renders \
  --views 4
```

Analyze render success:

```bash
uv run python scripts/analyze_render_success.py \
  --manifest data/processed/manifest_render10.jsonl \
  --render-dir data/renders
```

Score with VLM:

```bash
uv run python scripts/score_assets.py \
  --manifest data/processed/manifest_render10.jsonl \
  --model qwen3-vl-235b-a22b-thinking
```

Use `--limit N` only for command-line batch debugging. The frontend should run selected assets by `uid`.

## Verification

Syntax checks:

```bash
uv run python -m py_compile web/app.py scripts/*.py
node --check web/static/app.js
```

API checks:

```bash
curl -s http://127.0.0.1:7860/api/models
curl -s 'http://127.0.0.1:7860/api/assets?manifest=data/processed/manifest_render10.jsonl'
curl -s 'http://127.0.0.1:7860/api/evaluation?manifest=data/processed/manifest_render10.jsonl&model=qwen3-vl-235b-a22b-thinking'
curl -s 'http://127.0.0.1:7860/api/views/fac949a2ce8f4a58aa5b61aa5ec8ed11'
```

GLB MIME check:

```bash
curl -D - -o /tmp/model.glb \
  http://127.0.0.1:7860/api/model/fac949a2ce8f4a58aa5b61aa5ec8ed11
```

Expected `content-type`:

```text
model/gltf-binary
```

## Troubleshooting

- `Missing LITELLM_API_KEY in .env`: add the key to `.env`; do not hardcode it.
- VLM score is skipped: check that `data/renders/<uid>/rgb` and `data/renders/<uid>/normal` exist.
- 3D preview fails: check `/api/model/{uid}` returns `model/gltf-binary` and the local `local_path` exists.
- Black or blank renders: inspect `scripts/render_blender.py`; current behavior normalizes scene geometry and uses Blender Workbench for visibility.
- Charts look inconsistent: verify the frontend calls `/api/evaluation?manifest=...&model=...` and filters by selected model.

## Reference Docs

Read only when needed:

- `docs/07_指标方法论.md` for metric trade-offs.
- `docs/08_文献综述与指标决策.md` for arXiv survey conclusions.
- `docs/11_manifest说明.md` for manifest meanings.
- `docs/12_前端评测上下文与可视化说明.md` for UI context and chart semantics.
