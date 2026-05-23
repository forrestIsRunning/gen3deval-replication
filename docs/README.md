# 文档入口

## 当前有效

先读这 6 个：

1. `../README.md`：启动、数据流、主入口。
2. `11_manifest说明.md`：manifest 的用途和分层。
3. `13_self_evolving_render_gate.md`：未渲染不能跑 VLM。
4. `14_self_evolving_render_quality.md`：渲染文件存在不等于可用。
5. `15_codebase_audit.md`：当前优化清单。
6. `16_LLM观测与调试.md`：Opik 观测和低分复核。

补充阅读：

- `07_指标方法论.md`
- `08_文献综述与指标决策.md`
- `09_Tripo3D评测指标蓝图.md`
- `12_前端评测上下文与可视化说明.md`

## 归档

`docs/archive/` 只放历史材料：

- 旧计划
- 旧命令
- 旧前端说明
- 早期论文笔记

这里的内容只作为背景，不作为当前操作入口。

## 验证命令

```bash
uv run python -m py_compile web/app.py scripts/*.py
node --check web/static/app.js
uv run python scripts/score_assets.py --help
uv run python scripts/compute_geometry_metrics.py --help
uv run python scripts/download_objaverse_assets.py --help
```
