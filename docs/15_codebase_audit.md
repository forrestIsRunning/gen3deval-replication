# Codebase Audit: 下一轮优化清单

本轮阅读了 `scripts/`、`web/`、`docs/` 和 Skill。目标是继续做减法，把判断逻辑集中，避免前端、后端、脚本各自维护一套规则。

## 已落地

### 1. Readiness Gate 统一

之前的问题：

- 前端用 `has_render + render_quality` 自己判断能否 VLM；
- 后端 `/api/run` 又独立判断；
- 未来加入几何红线、质量红线时容易不一致。

现在后端统一返回 `readiness`：

- `ready_for_vlm`
- `status`
- `blockers`
- `actions`
- `has_model`
- `geometry`
- `render`
- `render_quality`

前端只消费 `readiness.ready_for_vlm` 和 `readiness.blockers`。

### 2. 渲染质量缓存

`/api/assets` 和 `/api/evaluation` 会频繁读取 RGB/Normal 并计算质量指标。现在增加了进程内 `QUALITY_CACHE`，按图片路径、mtime、size 生成指纹；渲染文件变化时自动失效。

### 3. 文档继续做减法

当前文档入口是 `docs/README.md`。旧草稿留在 `docs/archive/`，不作为当前操作依据。

## 仍需优化

1. **共享质量算法**：`web/app.py` 和 `scripts/analyze_render_quality.py` 仍有重复实现，下一步应抽到 `scripts/render_quality_lib.py` 或项目内公共模块。
2. **几何红线未参数化**：当前 readiness 只检查 geometry 是否存在，还没有按 `aspect_ratio`、`degenerate_face_count`、`face_count` 设置红线。
3. **文档与运行面已分离**：当前主运行面已收缩为 geometry / render / score / minimal web UI；文档和论文材料保留，但不应再被视为默认执行入口。
4. **pairwise 路径较旧**：`evaluate_pairwise.py` 仍使用旧维度 `surface`，还没有纳入 texture/material、多视角一致性和 readiness gate。
5. **论文材料偏研究档案**：`paper/` 与 `docs/archive/` 适合作为知识背景，不应继续驱动前端或主流程 API 设计。

## 新论文启发

- `Hi3DEval`：评测需要层级化，覆盖对象、部件、材质、空间关系。
- `MVGBench`：多视角评测要关注几何一致性、纹理一致性、图像质量和语义一致性。
- `FMQM`：mesh 质量可从几何场和颜色场提取低成本特征，适合在 VLM 前做快速筛查。

## 下一步建议

优先做两件事：

1. 抽公共 readiness/quality 模块，减少 `web/app.py` 体积；
2. 给 readiness 加几何红线配置，例如：
   - `face_count` 过高；
   - `aspect_ratio` 极端；
   - `degenerate_face_count` 过高；
   - `is_winding_consistent=false`。
