# LLM/VLM 观测与调试

本项目强制依赖 `Opik`。`scripts/score_assets.py` 和 `scripts/evaluate_pairwise.py` 都通过 `scripts/observability.py` 上报脱敏 trace，不再支持 LangSmith 或 Langfuse。

模型调用层当前使用 `Pydantic AI + TypedDict`：

- 不再手写 `requests.post(.../chat/completions)`；
- 不再依赖正则/`json.loads` 从自由文本里抠 JSON；
- 输出类型由 `scripts/vlm_types.py` 中的 `TypedDict` 定义；
- LiteLLM / OpenAI-compatible 适配由 `scripts/vlm_agent.py` 统一处理。

当前实现采用“主流程优先、观测分层降级”策略：

- VLM 请求成功时，评分结果仍然会写入本地结果文件；
- Opik trace、attachment、annotation queue、feedback score 各自独立写入；
- 某个观测子步骤返回 500 时，不再中断整条评分；
- 每条结果会新增 `observability` 字段，明确记录 trace / attachment / queue / feedback / flush 的成功或失败。

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
uv sync
```

在 `.env` 中配置：

```bash
OPIK_BASE_URL=http://localhost:5173/api
OPIK_PROJECT_NAME=gen3deval-replication
OPIK_WORKSPACE=default
```

如果本机没有可用的 Opik，可直接使用仓库内置编排：

```bash
cp .env.opik.example .env.opik
docker compose --env-file .env.opik -f docker-compose.opik.yml up -d
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

当 `overall < 6` 时，当前 trace 会尝试自动：

- 推入 annotation queue `low-score-review`
- 记录 7 个维度的 feedback scores

这一步依赖真实 trace id，不是离线补写。如果后端返回 500，失败信息会保存在结果里的 `observability.post_trace`。

## 调试原则

- 缺少 `opik` SDK 或 `OPIK_*` 配置时，主流程直接失败。
- queue、feedback、attachment、flush 失败都应显式记录到结果里的 `observability` 字段。
- 如果要排查低分样本，优先检查 trace attachments 是否包含 8 张图和对应 `.glb`。
