# Self Evolving: 渲染门禁与评测闭环

## 触发问题

前端在 `多视角渲染` 中显示：

- `RGB 尚未渲染`
- `Normal 尚未渲染`

此时用户自然会问：是否还能直接做 VLM 评测？

结论：不能直接做 VLM 语义/视觉评测。

原因是当前 VLM rubric 的证据来源就是 RGB/Normal 多视角图。没有这些图时，VLM 没有真实视觉证据；继续评分只会导致空跑、跳过或不可信的模型判断。

## 本轮代码演进

### 后端

新增真实渲染状态检查：

- `/api/assets` 返回每个资产的 `render` 状态：
  - `rgb_views`
  - `normal_views`
  - `render_complete`
- `/api/views/{uid}` 同样返回渲染视图数量。
- `/api/run` 在单资产 VLM 评分前检查 RGB/Normal 是否各至少 4 张；不满足时返回错误，不创建 VLM job。
- `/api/render/run` 新增后台渲染任务，调用 `scripts/render_blender.py` 为当前资产生成真实 RGB/Normal。
- `/api/evaluation` 的渲染验证改为按当前 manifest 实时扫描 `data/renders/<uid>/rgb|normal`，不再依赖固定的 `render_success_10.csv`。

### 前端

新增交互闭环：

1. 用户选择 `Manifest + 资产 + VLM`。
2. 前端检查当前资产是否有完整 RGB/Normal。
3. 未渲染时禁用 `Run Selected VLM`。
4. 用户点击 `Render Selected`。
5. Blender 后台渲染完成后刷新视图。
6. 渲染完整后允许 `Run Selected VLM`。

这样可以避免无证据评分，也让用户知道下一步该做什么。

## 评测方法论更新

当前 pipeline 的 gate 顺序应固定为：

1. **资产存在**：manifest 有 `local_path` 且文件存在。
2. **几何可计算**：mesh 能被 `trimesh` 加载并计算基础指标。
3. **渲染完整**：至少 4-view RGB + 4-view Normal。
4. **VLM 评分**：只在真实渲染证据存在时运行。
5. **LLM 报告**：只汇总几何、渲染、VLM reason，不凭空打分。

## 下一步算法优化候选

1. **渲染质量自检**：对 RGB 图做非空图检测、亮度/对比度检测、主体占比检测，避免“渲染成功但图片不可用”。
2. **Normal 图有效性检测**：检查 normal 图颜色分布是否过于单一，用于发现法线输出异常。
3. **几何红线门禁**：对极端 `aspect_ratio`、过高 `degenerate_face_count`、无法加载资产直接标记为 fail，不进入 VLM。
4. **VLM 校准集**：固定 20-50 个资产作为人工审查集，比较不同 VLM 模型和 prompt rubric 的稳定性。
5. **模型级分布指标**：在有生成结果集合时加入 MMD/Coverage/1-NNA/JSD，而不是只看单资产评分。

## 实操回答

如果前端显示 `RGB 尚未渲染` 或 `Normal 尚未渲染`：

- 可以查看 3D 预览；
- 可以查看几何指标；
- 不应该运行 VLM 评分；
- 应先点击 `Render Selected`；
- 渲染完成后再点击 `Run Selected VLM`。
