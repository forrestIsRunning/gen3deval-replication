# Next Steps

## Short-Term

1. Install Blender and run the render step.
2. Run `evaluate_pairwise.py --limit 5` to validate API format and latency.
3. Inspect `data/results/comparisons.jsonl` for malformed model outputs.
4. Run the full pair list.

## Better Reproduction

To get closer to the paper, replace Objaverse category prompts with actual
text-to-3D method outputs:

- rows should share the same prompt;
- each method should produce one asset per prompt;
- pair builder should compare every method pair per prompt;
- aggregate ELO by method instead of by individual asset.

## Model Choices

Recommended VLM judges from your available list:

- `qwen3-vl-235b-a22b-thinking`: best default for careful visual judging;
- `qwen3-vl-235b-a22b-instruct`: faster non-thinking variant;
- `qwen2.5-vl-7b-instruct`: cheap smoke tests.

For coding and maintenance, use `gpt-5.5`, `gpt-5.4`, or `gpt-5.3-codex`.
