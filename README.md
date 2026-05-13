# Gen3DEval Replication

这是一个基于公开 3D 数据和 OpenAI 协议 VLM 的 3D 模型评测 POC。目标不是复现论文私有权重，而是复现一条可扩展、可审计的评测 pipeline：

- 真实 Objaverse-LVIS 3D 资产；
- 可计算几何指标；
- Blender 多视角 RGB/Normal 渲染；
- VLM 多维评分；
- 前端 3D 预览、渲染验证、几何分布和多维指标可视化；
- arXiv 方法论到当前实现的映射说明。

## 环境

推荐使用 `uv` 管理 Python。

```bash
cd /Users/xiaoxia/Projects/experiments/gen3deval-replication
uv sync
cp .env.example .env
```

编辑 `.env`：

```bash
LITELLM_BASE_URL=http://120.48.38.233:4000
LITELLM_API_KEY=your-key
GEN3D_VLM_MODEL=qwen3-vl-235b-a22b-thinking
```

如果本机需要代理，可在命令前设置：

```bash
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080
```

## 启动后端和前端

本项目的前端是 FastAPI 静态页面，不需要单独 npm 构建。启动后端后，前端同一个地址访问。

```bash
cd /Users/xiaoxia/Projects/experiments/gen3deval-replication
uv run uvicorn web.app:app --host 127.0.0.1 --port 7860 --reload
```

浏览器打开：

```text
http://127.0.0.1:7860
```

如果端口被占用：

```bash
lsof -nP -iTCP:7860 -sTCP:LISTEN
```

需要换端口时：

```bash
uv run uvicorn web.app:app --host 127.0.0.1 --port 7861 --reload
```

## 前端怎么用

前端核心上下文是：

1. 选择 `Manifest`；
2. 选择具体 3D `资产`；
3. 选择 `VLM`；
4. 点击 `Run Selected VLM`。

如果 `多视角渲染` 显示 `RGB 尚未渲染` 或 `Normal 尚未渲染`，不能直接做 VLM 评测。VLM 必须看真实 RGB/Normal 证据图，否则评分没有依据。此时先点击 `Render Selected`，等 Blender 渲染完成后再运行 `Run Selected VLM`。

当前支持的 VLM：

- `qwen3-vl-235b-a22b-instruct`
- `qwen3-vl-235b-a22b-thinking`

前端展示内容：

- `3D 预览`：直接加载真实 GLB；
- `多视角渲染`：RGB + Normal 视角图；
- `VLM 多维评分`：文本、外观、表面、几何、材质、多视角、综合；
- `几何分布`：当前 manifest 的面数区间分布；
- `渲染验证`：当前 manifest 的 RGB/Normal 渲染完成情况；
- `可计算几何指标`：面数、顶点数、watertight、winding、aspect、degenerate、area。

评测门禁顺序是：资产存在 -> 几何可计算 -> RGB/Normal 渲染完整 -> VLM 评分 -> LLM 汇总。没有渲染图时不要让 VLM 凭空打分。

## 常用 Manifest

- `data/processed/manifest_120.jsonl`：120 个真实资产，正式主数据集。
- `data/processed/manifest_render10.jsonl`：10 个真实资产，已经有 RGB/Normal 渲染，最适合直接跑前端 VLM。
- `data/processed/manifest_render1.jsonl`：单资产调试。
- `data/processed/manifest_smoke3.jsonl`：渲染冒烟测试。
- `data/processed/pairs_smoke3.jsonl`：pairwise/ELO 测试，不适合单资产 VLM。
- `data/processed/sample_manifest.jsonl`：旧 demo，不作为正式评测入口。

## 数据准备

准备 120 个公开 Objaverse-LVIS 资产：

```bash
uv run python scripts/prepare_objaverse_sample.py --num-assets 120
uv run python scripts/download_objaverse_assets.py --manifest data/processed/manifest_120.jsonl
```

## 几何指标

几何指标不依赖 VLM，适合 scale：

```bash
uv run python scripts/compute_geometry_metrics.py \
  --manifest data/processed/manifest_120.jsonl
```

输出：

- `data/results/geometry_metrics.jsonl`
- `data/results/geometry_metrics.csv`
- `data/results/geometry_summary.csv`
- `data/results/geometry_report.md`

## Blender 渲染

VLM 评分依赖真实 RGB/Normal 图，因此需要 Blender。

macOS 安装：

```bash
brew install --cask blender
```

渲染 10 个已选资产：

```bash
blender -b --python scripts/render_blender.py -- \
  --manifest data/processed/manifest_render10.jsonl \
  --output-dir data/renders \
  --views 4
```

分析渲染成功率：

```bash
uv run python scripts/analyze_render_success.py \
  --manifest data/processed/manifest_render10.jsonl \
  --render-dir data/renders
```

分析渲染图质量：

```bash
uv run python scripts/analyze_render_quality.py \
  --manifest data/processed/manifest_render10.jsonl
```

也可以在前端选择一个资产后点击 `Render Selected`，后端会调用同一份 Blender 渲染脚本，只渲染当前资产。

## VLM 单资产评分

前端点击 `Run Selected VLM` 会调用同一条后端链路。命令行也可以直接跑：

```bash
uv run python scripts/score_assets.py \
  --manifest data/processed/manifest_render10.jsonl \
  --model qwen3-vl-235b-a22b-thinking \
  --limit 1
```

结果追加到：

```text
data/results/asset_scores.jsonl
```

评分维度：

- `text_fidelity`
- `appearance`
- `surface_quality`
- `geometry_coherence`
- `texture_material`
- `multi_view_consistency`
- `overall`

## 验证接口

```bash
curl -s http://127.0.0.1:7860/api/models
curl -s 'http://127.0.0.1:7860/api/assets?manifest=data/processed/manifest_render10.jsonl'
curl -s 'http://127.0.0.1:7860/api/evaluation?manifest=data/processed/manifest_render10.jsonl&model=qwen3-vl-235b-a22b-thinking'
curl -s 'http://127.0.0.1:7860/api/views/fac949a2ce8f4a58aa5b61aa5ec8ed11'
```

检查 GLB MIME：

```bash
curl -D - -o /tmp/model.glb \
  http://127.0.0.1:7860/api/model/fac949a2ce8f4a58aa5b61aa5ec8ed11
```

应看到：

```text
content-type: model/gltf-binary
```

## 指标 trade-off

- 几何客观指标：用函数直接算，便宜、可复现、适合 scale。
- 语义、视觉、还原度：用 VLM，看多视角 RGB/Normal。
- 报告、解释、错误归因：用 LLM 汇总已有指标和 VLM reason，不让纯 LLM 直接凭空打 3D 分。

## 更多文档

- `docs/README.md`：当前文档入口和阅读顺序。
- `skills/gen3deval-replication/SKILL.md`：给 Codex/Agent 复用的项目操作 Skill。
- `docs/07_指标方法论.md`
- `docs/08_文献综述与指标决策.md`
- `docs/09_Tripo3D评测指标蓝图.md`
- `docs/10_arxiv论文清单.md`
- `docs/11_manifest说明.md`
- `docs/12_前端评测上下文与可视化说明.md`
- `docs/13_self_evolving_render_gate.md`
- `docs/14_self_evolving_render_quality.md`
- `docs/15_codebase_audit.md`
