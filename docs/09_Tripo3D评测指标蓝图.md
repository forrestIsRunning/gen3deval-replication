# Tripo3D 评测指标蓝图

## 背景

Tripo3D 的核心产品语境是从文本或图片生成可用的 3D 资产。评测不能只回答“像不像”，还要回答：

- 是否符合 prompt 或输入图；
- 是否视觉上可用；
- mesh 是否干净，能否被下游工具打开、编辑、渲染；
- 多视角是否一致，有没有 Janus、漂浮碎片、穿模；
- 模型复杂度是否适合线上交付和用户编辑；
- 不同模型版本之间是否真的变好。

因此评测体系应分成四层：可计算几何门禁、渲染代理指标、VLM 语义/视觉判断、LLM 报告。

## 指标与 Tripo3D 意义

| 指标 | 含义 | 对 Tripo3D 的意义 | 推荐实现 |
| --- | --- | --- | --- |
| vertex_count | 顶点数量 | 控制模型复杂度、加载速度、编辑体验 | 直接计算 |
| face_count | 面数量 | 控制渲染成本、移动端/网页端可用性 | 直接计算 |
| bbox / aspect_ratio | 包围盒尺寸和长宽高比例 | 发现极端扁平、尺度异常、导入失败资产 | 直接计算 |
| surface_area | 表面积 | 检测尺度异常、材质展开风险 | 直接计算 |
| volume | 封闭模型体积 | CAD/打印/仿真场景有意义 | watertight 时计算 |
| is_watertight | mesh 是否封闭 | 对打印、物理仿真、部分编辑工具重要 | 直接计算 |
| is_winding_consistent | 面朝向是否一致 | 影响法线、阴影、渲染和导出质量 | 直接计算 |
| euler_number | 拓扑结构摘要 | 发现破洞、异常拓扑的辅助信号 | 直接计算 |
| degenerate_face_count | 退化面数量 | 发现坏 mesh，作为质量门禁 | 直接计算 |
| render_success_rate | Blender 是否能稳定渲染 RGB/Normal | 衡量资产能否进入后续 VLM 评测和真实生产链路 | 渲染实验 |
| multi_view_consistency | 多视角是否同一对象 | 检测 Janus、多头、背面崩坏 | VLM |
| appearance | 视觉质量、完整度、美观度 | 用户第一感知质量 | VLM 成对/打分 |
| surface_quality | 法线/表面是否平滑、破损、噪声 | 影响游戏、AR、渲染展示 | VLM + normal 图 |
| texture_material | 贴图和材质可信度 | 商品化资产和用户满意度关键 | VLM + 纹理指标 |
| text_fidelity | 是否符合文本 prompt | text-to-3D 主指标 | VLM，最好 pairwise |
| image_fidelity | 是否还原输入图片 | image-to-3D 主指标 | VLM + 视角/轮廓匹配 |
| CLIP/OpenShape score | 文本/图像/3D embedding 对齐 | 低成本语义筛查，补充 VLM | 模型计算 |
| CD/EMD/F-score | 与参考 3D 的距离 | reconstruction benchmark、有 GT 时使用 | 点采样计算 |
| MMD/Coverage/1-NNA/JSD | 生成分布质量、多样性 | 评估模型整体分布而非单个资产 | 数据集级计算 |
| LLM report | 汇总指标、失败模式、版本变化 | 给研发和产品看，不能替代原始指标 | LLM 汇总 |

## 推荐评测分层

### Level 0: 资产可用性门禁

每个生成结果都跑：

- 文件能否加载；
- vertex_count / face_count；
- bbox / aspect_ratio；
- degenerate_face_count；
- winding consistency；
- render_success。

输出：通过/失败、失败原因。

### Level 1: 快速质量评分

对抽样或全量跑：

- 4-view RGB；
- 4-view normal；
- VLM scalar score；
- geometry + render metrics 聚合。

输出：多维评分表和 dashboard。

### Level 2: 版本对比

对同一 prompt/image 的多个模型版本跑：

- pairwise VLM preference；
- appearance / surface / text_fidelity / image_fidelity；
- ELO 聚合；
- 胜负样例可视化。

输出：模型版本 leaderboard。

### Level 3: 学术 benchmark

如果有参考数据或 benchmark：

- CD / EMD / F-score / Normal Consistency；
- MMD / Coverage / 1-NNA / JSD；
- CLIP/OpenShape/ULIP retrieval；
- 人类小样本校准 VLM。

输出：论文式评测表。

## 本次 hands-on 实验

### 实验 1：120 个 Objaverse-LVIS 资产几何指标

产物：

- `data/results/geometry_metrics.jsonl`
- `data/results/geometry_metrics.csv`
- `data/results/geometry_summary.csv`
- `data/results/geometry_report.md`
- `data/results/geometry_*.png`

结论：

- 120/120 资产成功计算基础几何指标；
- 可计算指标非常适合作为 Tripo3D 的第一道自动门禁；
- `component_count` 这类深度拓扑指标可能很慢，应作为可选 deep mode，而不是默认全量指标。

### 实验 2：10 个资产 Blender 多视角渲染

产物：

- `data/processed/manifest_render10.jsonl`
- `data/renders/<uid>/rgb/view_*.png`
- `data/renders/<uid>/normal/view_*.png`
- `data/results/render_success_10.csv`
- `data/results/render_success_10.json`

结果：

- 10/10 资产完成 4-view RGB 和 4-view normal 渲染；
- 当前 Blender 5.1.1 兼容路径可用；
- normal 渲染采用临时材质输出法线颜色，避免 Blender 5.1 compositor API 变化。

## 对现有评测方式的优化

1. **先算再问 VLM**：几何失败或渲染失败的资产不应直接进入 VLM 主评测，否则浪费成本。
2. **scalar + pairwise 并存**：前端展示用 scalar score，模型排名用 pairwise + ELO。
3. **VLM 输入固定化**：所有模型都用相同相机、光照、分辨率、RGB/Normal 视图。
4. **保留证据链**：保存 mesh path、render path、VLM raw JSON、reason、指标 CSV。
5. **针对 Tripo3D 增加 image_fidelity**：Tripo3D 有 image-to-3D 场景，必须单独评估输入图还原度。
6. **建立红线指标**：无法加载、无法渲染、退化面过多、极端 aspect ratio 应作为失败而不是低分。
7. **引入人类校准集**：用少量人工偏好校准 VLM judge，避免模型偏好漂移。
