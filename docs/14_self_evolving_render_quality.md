# Self Evolving: 渲染质量自检

## 为什么继续优化

上一轮已经加入了“没有 RGB/Normal 不允许 VLM 评分”的硬门禁。但只检查文件数量还不够：真实系统中可能出现“文件存在但图像几乎空白、主体过小、Normal 图异常单色”的情况。

因此本轮增加第二层渲染门禁：渲染图质量自检。

## 参考论文与方法论

本轮没有把新论文指标完整搬进代码，而是吸收了它们的方法论：

- Gen3DEval / GPT-4V Eval3D：VLM 评测必须基于可审计的多视角视觉证据。
- Eval3D (`arXiv:2504.18509`)：评测应细粒度、可解释，并避免只依赖黑盒多模态模型给粗粒度分数。
- Textured Mesh Quality Assessment (`arXiv:2202.02397`)：纹理 mesh 质量要把几何、颜色、语义复杂度和失真分开看。
- FMQM (`arXiv:2505.10824`)：mesh 质量可以从几何场和颜色场抽取低成本特征，启发我们先做 RGB/Normal 的低成本质量自检。
- Hi3DEval (`arXiv:2508.05609`)：3D 评测需要层级化，不只看 object-level image metric，还要关注材质、局部细节和空间一致性。

对应到当前系统：VLM 之前应检查渲染图是否“存在且可用”。

## 新增算法

新增脚本：

```bash
uv run python scripts/analyze_render_quality.py \
  --manifest data/processed/manifest_render10.jsonl
```

输出：

```text
data/results/render_quality.jsonl
```

每个资产计算：

- `brightness`：灰度平均亮度；
- `contrast`：灰度标准差；
- `nonwhite_ratio`：非白像素比例，发现纯白/主体过小；
- `nonblack_ratio`：非黑像素比例，发现纯黑/曝光失败；
- `channel_std_mean`：RGB 通道变化，Normal 图过低时可能表示法线图无效；
- `blank_views`：低信息视图数量；
- `quality_pass`：是否通过质量自检；
- `issues`：失败原因。

## 后端变化

- `/api/assets` 返回 `render_quality`。
- `/api/views/{uid}` 返回 `quality`。
- `/api/evaluation` 的渲染验证表返回：
  - `quality_pass`
  - `quality_issues`

这使前端不只知道“有没有图”，还知道“图是否值得给 VLM 看”。

如果 `quality_pass=false`，后端会拒绝正式 VLM 评分。这样做是为了避免把渲染失败误判为 3D 模型失败。

## 前端变化

`多视角渲染` 区域新增质量条：

- 通过：显示 RGB 对比度、Normal 色彩变化；
- 需复查：显示具体 issues；
- 未渲染：仍然提示先 `Render Selected`。

`渲染验证` 表新增 `Quality` 列。

## 后续优化

1. 增加主体占比估计：用背景白色阈值或 alpha mask 估计 mesh 占画面比例。
2. 增加多视角差异度：四个 RGB 视角如果几乎相同，可能说明相机或资产异常。
3. 增加 Normal 边缘复杂度：用 Sobel/Laplacian 判断 normal 是否有几何细节。
4. VLM prompt 中附带质量自检结果，让 VLM 区分“模型差”和“渲染证据差”。
5. 对 quality fail 的资产不直接进正式 VLM 榜单，只进入错误归因报告。
