# LLM/VLM 观测与调试

本项目当前只保留 `Opik` 这一条观测链路。`scripts/score_assets.py` 和 `scripts/evaluate_pairwise.py` 都通过 `scripts/observability.py` 上报脱敏 trace，不再支持 LangSmith 或 Langfuse。

## 已接入的位置

- `scripts/score_assets.py`：单资产 VLM 多维评分，支持 prompt v1/v2 和 A/B test。
- `scripts/evaluate_pairwise.py`：pairwise 偏好判断。
- `scripts/observability.py`：Opik trace、低分 annotation queue、feedback scores。

trace 名称：

- `gen3d.vlm.score_asset.v1`
- `gen3d.vlm.score_asset.v2`
- `gen3d.vlm.pairwise_judge`

## 记录什么

会记录：

- `uid`、`category`、`model`、`prompt_variant`；
- 图片数量、目标 resize 尺寸、评测维度；
- HTTP 状态、耗时、结构化分数摘要；
- `issues` 数量、`strengths` 数量；
- 8 张渲染图 attachment；
- `.glb` 资产 attachment（如果 `local_path` 存在）。

不会记录：

- VLM 请求里的 base64 图片数据；
- `Authorization` header；
- `.env` 中的 key；
- 原始请求 payload 全量内容。

## 安装与配置

安装可选依赖：

```bash
uv sync --extra observability
```

在 `.env` 中配置：

```bash
OPIK_BASE_URL=http://localhost:5173/api
OPIK_PROJECT_NAME=gen3deval-replication
OPIK_WORKSPACE=default
```

## 单次评分

默认单跑使用 prompt v2：

```bash
uv run python scripts/score_assets.py \
  --manifest data/processed/manifest_render10.jsonl \
  --model qwen3-vl-235b-a22b-thinking \
  --limit 1
```

## A/B Test

`--ab-test` 会把同一批资产分别用 prompt v1 和 v2 运行，并在 Opik 中创建两个 experiment：

```bash
uv run python scripts/score_assets.py \
  --manifest data/processed/manifest_render10.jsonl \
  --limit 2 \
  --ab-test
```

在 Opik UI 中检查：

- dataset `score_assets`
- experiment `prompt_v1`
- experiment `prompt_v2`

## Human-in-the-loop

当 `overall < 6` 时，当前 trace 会自动：

- 推入 annotation queue `low-score-review`
- 记录 7 个维度的 feedback scores

这一步在 trace 上下文内部完成，依赖真实 trace id，不是离线补写。

## 调试原则

- 缺少 `opik` SDK 时，观测自动降级，不阻塞主流程。
- 观测失败不会中断评分，但需要通过 Opik UI 二次确认 queue 和 experiment 是否创建成功。
- 如果要排查低分样本，优先检查 trace attachments 是否包含 8 张图和对应 `.glb`。
