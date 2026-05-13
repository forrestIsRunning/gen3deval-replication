# Reproduction Plan

## Goal

Build a public-data Gen3DEval-style evaluation pipeline with at least 100
3D assets and reproducible outputs.

## Dataset

Use Objaverse-LVIS because it is public, large, and includes category labels.
The default manifest size is 120 assets. Each asset receives a prompt derived
from its LVIS category, for example:

`A high-quality 3D model of a wooden chair.`

For true text-to-3D benchmarking, replace the manifest with generated outputs
from multiple methods for the same prompt. The downstream evaluation scripts
do not need to change.

## Evaluation Design

The paper compares method outputs per prompt. For this public-data scaffold,
we compare assets within the same or related category. The pair builder creates
deterministic pairs and records prompt/category metadata.

Each pair is evaluated three times:

- appearance: RGB views, prompt hidden;
- surface: normal-map views, prompt hidden;
- text_fidelity: RGB views, prompt included.

The VLM must return JSON with `winner`, `confidence`, and `reason`.

## Outputs

- `data/processed/manifest_120.jsonl`: sampled assets;
- `data/renders/<uid>/rgb/*.png`: RGB views;
- `data/renders/<uid>/normal/*.png`: normal views;
- `data/processed/pairs.jsonl`: pair list;
- `data/results/comparisons.jsonl`: raw VLM judgments;
- `data/results/elo_scores.csv`: ELO scores by dimension;
- `data/results/*.png`: visual summaries.

## Scale Strategy

The pipeline is embarrassingly parallel:

- asset downloads can be parallelized by `objaverse`;
- Blender rendering can be sharded by manifest slices;
- VLM judging can be run with multiple workers or batched queues;
- ELO aggregation is cheap and deterministic.
