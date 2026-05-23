# Gen3DEval Replication

3D 生成评测平台。

## 启动

```bash
uv sync
cp .env.example .env
uv run uvicorn web.app:app --host 127.0.0.1 --port 7860 --reload
```

## 本地 Opik

```bash
cp .env.opik.example .env.opik
docker compose --env-file .env.opik -f docker-compose.opik.yml up -d
```

## 数据集

- `data/processed/manifest_120.jsonl`
- `data/processed/manifest_render10.jsonl`
- `data/processed/manifest_render1.jsonl`
- `data/processed/manifest_smoke3.jsonl`
- `data/processed/pairs_smoke3.jsonl`

## 评测

```bash
uv run python scripts/score_assets.py --manifest data/processed/manifest_render10.jsonl --limit 1
uv run python scripts/evaluate_pairwise.py --pairs data/processed/pairs_smoke3.jsonl --limit 1
```

## 前端

```text
http://127.0.0.1:7860
```
