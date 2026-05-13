# Paper Notes

Paper: arXiv:2504.08125, "Gen3DEval: Using vLLMs for Automatic Evaluation of
Generated 3D Objects".

## What the Paper Does

Gen3DEval evaluates generated 3D objects with a vision-language model. It
compares two 3D assets at a time and decides which is better on:

- appearance;
- surface quality;
- text fidelity.

The input is multi-view rendering. For each object, the paper samples four
views from a 360-degree orbit. RGB views are used for appearance and text
fidelity. Surface-normal views are used for surface quality.

After all pairwise comparisons are done, the paper aggregates wins into ELO
ratings and ranks 3D generation methods.

## What Is Not Public

The paper uses private Meta artist-created meshes, private human preference
annotations, and a fine-tuned Gen3DEval model. Those pieces prevent exact
weight-level reproduction.

## What We Reproduce Here

This repo reproduces the evaluation pipeline:

1. public 3D assets from Objaverse-LVIS;
2. 4-view RGB and normal rendering;
3. pairwise VLM judging through an OpenAI-compatible LiteLLM endpoint;
4. structured JSON judgments;
5. ELO ranking;
6. CSV and PNG visualization artifacts.

The result is a scalable evaluation pipeline that can be reused for real
text-to-3D or image-to-3D model outputs.
