# arXiv 论文清单

本清单由 `scripts/collect_arxiv_literature.py` 生成，目标是每个方向至少 10 篇。由于 arXiv API 触发限流，本次使用脚本内置 fallback seed list，并下载 PDF 到 `paper/arxiv_survey/`。

## 方向

1. `text_to_3d_eval`：Text/Image-to-3D 端到端评测、prompt benchmark、VLM judge。
2. `point_cloud_generation_metrics`：CD/EMD/MMD/Coverage/1-NNA/JSD 等生成分布指标。
3. `mesh_texture_quality`：mesh 清洁度、拓扑、法线、纹理质量。
4. `multimodal_3d_alignment`：3D-text/image embedding、retrieval、zero-shot 对齐。

## 本地文件

- 总清单 JSON：`paper/arxiv_survey/papers.json`
- 总清单 CSV：`paper/arxiv_survey/papers.csv`
- PDF：`paper/arxiv_survey/<direction>/*.pdf`

## 统计

- text_to_3d_eval: 10 篇
- point_cloud_generation_metrics: 10 篇
- mesh_texture_quality: 10 篇
- multimodal_3d_alignment: 10 篇
- 下载成功：40/40

## 使用方式

```bash
uv run python scripts/collect_arxiv_literature.py --per-direction 10 --download
```

如遇 arXiv API 429，脚本会使用 fallback 种子清单继续执行。
