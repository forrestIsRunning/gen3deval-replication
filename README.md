# Gen3DEval Replication Pipeline

This directory is a practical replication scaffold for arXiv:2504.08125,
"Gen3DEval: Using vLLMs for Automatic Evaluation of Generated 3D Objects".

The original paper trains a specialized vLLM with private artist-created
meshes and human preference data. This project reproduces the evaluation
pipeline with public data and your OpenAI-compatible LiteLLM models:

1. sample 100+ public Objaverse-LVIS 3D assets;
2. render each asset from 4 RGB views and 4 normal-map views;
3. ask a VLM to compare asset pairs on appearance, surface quality, and text fidelity;
4. aggregate pairwise wins with ELO;
5. export CSV/JSON results and PNG visualizations.

## Quick Start

Use Python 3.11 if possible. Some 3D packages lag behind Python 3.14.

```bash
cd /Users/xiaoxia/Projects/experiments/gen3deval-replication
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and put your LiteLLM key there.

Prepare a 120-object public dataset manifest:

```bash
python scripts/prepare_objaverse_sample.py --num-assets 120
```

Download the selected GLB files:

```bash
python scripts/download_objaverse_assets.py --manifest data/processed/manifest_120.jsonl
```

Render with Blender 4.x:

```bash
blender -b --python scripts/render_blender.py -- \
  --manifest data/processed/manifest_120.jsonl \
  --output-dir data/renders \
  --views 4
```

Run a small VLM smoke test:

```bash
python scripts/build_pairs.py --manifest data/processed/manifest_120.jsonl --max-pairs 12
python scripts/evaluate_pairwise.py --pairs data/processed/pairs.jsonl --limit 3
python scripts/aggregate_elo.py --comparisons data/results/comparisons.jsonl
python scripts/visualize_results.py
```

For a full run, remove `--limit 3`.

## Important Limits

This is a faithful pipeline replication, not a weight-level reproduction.
The paper's training data and fine-tuned Gen3DEval weights are not public.
Here, `qwen3-vl-235b-a22b-thinking` or another supported VLM acts as the
judge. The output is still useful as a scalable 3D model evaluation pipeline:
it produces auditable pairwise decisions, ELO rankings, and visual reports.

Read the step-by-step notes in `docs/`.
