# Manifest 说明

## 当前需要的 manifest

| 文件 | 是否需要 | 用途 |
| --- | --- | --- |
| `data/processed/manifest_120.jsonl` | 需要 | 主数据集。120 个真实 Objaverse-LVIS 资产，适合全量几何指标、全量渲染和正式评测。 |
| `data/processed/manifest_render10.jsonl` | 需要 | 已渲染小批量。10 个真实资产，已有 RGB/Normal，最适合直接在前端点 `Run VLM` 做真实 VLM 小批量评测。 |

## 辅助/测试 manifest

| 文件 | 是否正式需要 | 用途 |
| --- | --- | --- |
| `data/processed/manifest_smoke3.jsonl` | 不作为正式数据集 | 3 个真实资产，用来验证 Blender 渲染脚本是否正常。 |
| `data/processed/pairs_smoke3.jsonl` | 不作为单资产 VLM 输入 | pairwise/ELO 冒烟测试输入，用于 `evaluate_pairwise.py`，不适合 `score_assets.py`。 |
| `data/processed/sample_manifest.jsonl` | 不需要 | 旧 demo，没有真实 `local_path`，不用于正式评测。 |

## 前端默认建议

- 跑几何指标：选 `manifest_120.jsonl`。
- 跑 VLM：先选 `manifest_render10.jsonl`，因为它已有真实渲染图。
- 做渲染脚本调试：选 `manifest_smoke3.jsonl`。
