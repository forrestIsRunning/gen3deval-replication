# Command Log

## 1. Install

```bash
cd /Users/xiaoxia/Projects/experiments/gen3deval-replication
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. Sample Public Dataset

```bash
python scripts/prepare_objaverse_sample.py --num-assets 120
```

## 3. Download Assets

```bash
python scripts/download_objaverse_assets.py --manifest data/processed/manifest_120.jsonl
```

## 4. Render

Install Blender first. On macOS:

```bash
brew install --cask blender
```

Then run:

```bash
blender -b --python scripts/render_blender.py -- \
  --manifest data/processed/manifest_120.jsonl \
  --output-dir data/renders \
  --views 4
```

## 5. Build Pairs

```bash
python scripts/build_pairs.py --manifest data/processed/manifest_120.jsonl --max-pairs 180
```

## 6. Evaluate

```bash
python scripts/evaluate_pairwise.py --pairs data/processed/pairs.jsonl
```

## 7. Aggregate and Visualize

```bash
python scripts/aggregate_elo.py --comparisons data/results/comparisons.jsonl
python scripts/visualize_results.py
```
