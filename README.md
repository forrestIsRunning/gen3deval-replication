# Gen3DEval Replication

最小可运行的 3D 评测 POC。

## 运行

```bash
uv sync
cp .env.example .env
uv run uvicorn web.app:app --host 127.0.0.1 --port 7860 --reload
```

Opik 是必需依赖，`.env` 里必须有 `OPIK_BASE_URL`、`OPIK_PROJECT_NAME`、`OPIK_WORKSPACE`。

## 核心流程

1. 准备 manifest。
2. 渲染 RGB / Normal。
3. 计算几何指标。
4. 跑 VLM 评分。

## 入口

- 前端: `http://127.0.0.1:7860`
- 评分: `uv run python scripts/score_assets.py --manifest data/processed/manifest_render10.jsonl --limit 1`
