# 文档入口

这份目录做过减法：当前有效文档只保留评测方法、数据说明、前端上下文和 self-evolving 记录。早期草稿、旧命令和过时计划已移到 `docs/archive/`。

## 推荐阅读顺序

1. `../README.md`：如何启动后端/前端，如何跑数据、渲染、VLM。
2. `11_manifest说明.md`：每个 manifest 的用途。
3. `12_前端评测上下文与可视化说明.md`：前端如何按 `manifest + uid + model` 过滤。
4. `13_self_evolving_render_gate.md`：为什么未渲染不能 VLM，如何先渲染再评分。
5. `14_self_evolving_render_quality.md`：为什么文件齐全还要做渲染质量自检。
6. `09_Tripo3D评测指标蓝图.md`：完整指标分层。
7. `08_文献综述与指标决策.md`：论文方法论和指标选择。

## 当前有效原则

- 几何客观指标用函数直接算，适合 scale。
- RGB/Normal 渲染是 VLM 评分的证据，不存在证据就不评分。
- 渲染文件存在不等于证据可用，需要做质量自检。
- VLM 负责语义、视觉、还原度；LLM 只汇总已有指标和 VLM reason。
- 前端所有图表都必须绑定当前 `manifest + uid + model` 上下文。

## 已归档文档

`docs/archive/` 中保留早期探索记录，包括旧计划、旧命令、旧前端说明和初版论文笔记。它们不再作为当前操作入口。
