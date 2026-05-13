let scoreChart;
let geometryChart;
let manifestItems = [];
let assetRows = [];
let evaluation = null;

const metricHelp = {
  text_fidelity: "文本还原度。VLM 查看多视角 RGB/Normal，并比较 prompt 与 3D 资产是否一致。",
  image_fidelity: "图片还原度。用于 image-to-3D，比较输入图与生成资产的形状、颜色、部件一致性。",
  appearance: "外观质量。VLM 判断整体完整度、可读性、美观度和明显视觉缺陷。",
  surface_quality: "表面质量。VLM 查看 normal 图和 RGB 图，判断噪声、破面、过度平滑、浮片等问题。",
  geometry_coherence: "几何一致性。VLM 判断结构比例、部件连接、是否有穿模或漂浮组件。",
  texture_material: "贴图材质质量。VLM 判断纹理清晰度、材质可信度、颜色和表面观感。",
  multi_view_consistency: "多视角一致性。VLM 比较不同视角是否为同一对象，检测正背面不一致、重复脸、背面崩坏。",
  overall: "综合质量。VLM 基于各维度给出的总体可用性评分。",
  uid: "资产 ID。Objaverse 中每个 3D 资产的唯一标识，用来关联 mesh、渲染图和评分结果。",
  category: "类别。来自 Objaverse-LVIS，用来生成 prompt 和做分组分析。",
  face_count: "面数。trimesh 读取 mesh 后统计三角面数量；越高通常渲染、传输和编辑成本越高。",
  vertex_count: "顶点数。trimesh 统计 mesh vertices；衡量模型复杂度和下游加载压力。",
  aspect_ratio: "长宽比。包围盒最长边 / 最短边；用于发现极端扁平、拉伸或尺度异常资产。",
  surface_area: "表面积。trimesh.area 计算 mesh 表面总面积；可辅助发现尺度异常或展开风险。",
  is_watertight: "封闭。trimesh.is_watertight；表示 mesh 是否没有洞。打印、仿真、CAD 更看重。",
  is_winding_consistent: "朝向一致。trimesh.is_winding_consistent；表示面朝向是否一致，影响法线、阴影和导出质量。",
  degenerate_face_count: "退化面。面积接近 0 的面数量；用于发现坏 mesh、导出隐患和渲染异常。",
  render_success_rate: "渲染成功率。Blender 是否能为当前 manifest 的资产生成完整 4-view RGB 和 normal 图。",
};

const scoreOrder = [
  "text_fidelity",
  "appearance",
  "surface_quality",
  "geometry_coherence",
  "texture_material",
  "multi_view_consistency",
  "overall",
];

const metricLabels = {
  text_fidelity: "文本",
  appearance: "外观",
  surface_quality: "表面",
  geometry_coherence: "几何",
  texture_material: "材质",
  multi_view_consistency: "多视角",
  overall: "综合",
};

function help(label, key) {
  return `<span class="metric-help" title="${metricHelp[key] || ""}">${label}<i>?</i></span>`;
}

async function getJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function fillSelect(id, values) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    el.appendChild(option);
  });
}

function fillManifestSelect(items) {
  manifestItems = items;
  const el = document.getElementById("manifest");
  el.innerHTML = "";
  const sorted = [...items].sort((a, b) => Number(b.recommended) - Number(a.recommended));
  sorted.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.path;
    option.textContent = `${item.recommended ? "* " : ""}${item.name} · ${item.rows} rows · ${item.role}`;
    option.title = item.use;
    el.appendChild(option);
  });
  const render10 = sorted.find((item) => item.name === "manifest_render10.jsonl");
  if (render10) el.value = render10.path;
  updateManifestHelp();
}

function selectedManifestItem() {
  const selected = document.getElementById("manifest").value;
  return manifestItems.find((m) => m.path === selected);
}

function updateManifestHelp() {
  const item = selectedManifestItem();
  const box = document.getElementById("manifestHelp");
  if (!item) {
    box.textContent = "";
    return;
  }
  box.innerHTML = `<b>${item.name}</b><span>${item.role}</span><p>${item.use}</p>`;
}

function renderKpis(dashboard) {
  const kpis = document.getElementById("kpis");
  const cards = [
    ["几何资产", `${dashboard.geometry.ok}/${dashboard.geometry.assets}`, "真实 Objaverse-LVIS 资产的可计算几何指标。"],
    ["渲染成功", `${dashboard.render.complete}/${dashboard.render.assets}`, metricHelp.render_success_rate],
    ["VLM 样本", `${dashboard.scores.assets}`, "已有真实渲染图上的真实 VLM 评分样本数，按 uid + model 保存。"],
    ["论文覆盖", `${dashboard.literature.download_ok}/${dashboard.literature.papers}`, "4 个方向各 10 篇 arXiv/相关论文 PDF 下载覆盖。"],
  ];
  kpis.innerHTML = cards
    .map(([label, value, tip]) => `<div class="kpi" title="${tip}"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function renderAssetSelect() {
  const el = document.getElementById("asset");
  el.innerHTML = "";
  assetRows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.uid;
    const badges = [
      row.has_render ? "已渲染" : "未渲染",
      row.scored_models?.length ? `已评分 ${row.scored_models.length}` : "未评分",
    ].join(" · ");
    option.textContent = `${row.uid.slice(0, 8)} · ${row.category || "unknown"} · ${badges}`;
    option.title = row.prompt || row.uid;
    el.appendChild(option);
  });
}

function selectedAsset() {
  const uid = document.getElementById("asset").value;
  return assetRows.find((row) => row.uid === uid);
}

function contextText() {
  const model = document.getElementById("model").value;
  const manifest = selectedManifestItem();
  const asset = selectedAsset();
  return {
    manifest: manifest?.name || "",
    model,
    uid: asset?.uid || "",
    category: asset?.category || "",
    prompt: asset?.prompt || "",
  };
}

function renderContext() {
  const ctx = contextText();
  document.getElementById("contextBox").innerHTML = `
    <div><span>Manifest</span><b>${ctx.manifest}</b></div>
    <div><span>Asset</span><b>${ctx.uid ? `${ctx.uid.slice(0, 12)} · ${ctx.category}` : "未选择"}</b></div>
    <div><span>VLM</span><b>${ctx.model}</b></div>
    <p>${ctx.prompt || "选择 manifest 和资产后，VLM 将只对当前资产的真实多视角渲染打分。"}</p>
  `;
}

function scoreAverages(scores) {
  const sums = {};
  const counts = {};
  scores.forEach((row) => {
    Object.entries(row.scores || {}).forEach(([key, value]) => {
      sums[key] = (sums[key] || 0) + Number(value);
      counts[key] = (counts[key] || 0) + 1;
    });
  });
  return scoreOrder
    .filter((key) => counts[key])
    .map((key) => ({ dimension: key, score: Math.round((sums[key] / counts[key]) * 100) / 100 }));
}

function renderScoreChart(scores) {
  const data = scoreAverages(scores);
  const ctxText = contextText();
  document.getElementById("scoreTitle").textContent = "VLM 多维评分";
  document.getElementById("scoreSubtitle").textContent = `${ctxText.model} · ${data.length ? `${scores.length} 个已评分资产` : "当前选择暂无评分"}`;
  const ctx = document.getElementById("chart");
  if (scoreChart) scoreChart.destroy();
  scoreChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => metricLabels[d.dimension] || d.dimension),
      datasets: [
        {
          data: data.map((d) => d.score),
          backgroundColor: data.map((d) => (d.dimension === "overall" ? "#b45309" : "#2563eb")),
          borderRadius: 5,
          barThickness: 18,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 4, right: 18, bottom: 4, left: 4 } },
      scales: {
        x: {
          min: 0,
          max: 10,
          grid: { color: "#edf0f5" },
          ticks: { stepSize: 2 },
        },
        y: {
          grid: { display: false },
          ticks: { autoSkip: false, padding: 8 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => data[items[0].dataIndex].dimension,
            label: (ctx) => `平均分: ${ctx.parsed.x}`,
            afterLabel: (ctx) => metricHelp[data[ctx.dataIndex].dimension] || "",
          },
        },
      },
    },
  });
}

function renderGeometryChart(rows) {
  const selectedUid = document.getElementById("asset").value;
  const values = rows
    .filter((row) => row.ok && row.geometry)
    .map((row) => ({ uid: row.uid, faces: Number(row.geometry.face_count || 0) }))
    .filter((row) => row.faces > 0);
  const bins = [
    { label: "<5k", min: 0, max: 5000 },
    { label: "5k-20k", min: 5000, max: 20000 },
    { label: "20k-50k", min: 20000, max: 50000 },
    { label: "50k-100k", min: 50000, max: 100000 },
    { label: ">100k", min: 100000, max: Infinity },
  ].map((bin) => ({
    ...bin,
    count: values.filter((row) => row.faces >= bin.min && row.faces < bin.max).length,
    selected: values.some((row) => row.uid === selectedUid && row.faces >= bin.min && row.faces < bin.max),
  }));
  const selected = values.find((row) => row.uid === selectedUid);
  document.getElementById("geometrySubtitle").textContent = selected
    ? `当前资产 ${formatNumber(selected.faces)} faces；图中按面数区间聚合 ${values.length} 个资产。`
    : `按面数区间聚合 ${values.length} 个资产。`;
  const ctx = document.getElementById("geometryChart");
  if (geometryChart) geometryChart.destroy();
  geometryChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: bins.map((d) => d.label),
      datasets: [
        {
          data: bins.map((d) => d.count),
          backgroundColor: bins.map((d) => (d.selected ? "#b45309" : "#0f766e")),
          borderRadius: 5,
          barThickness: 28,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 8, right: 12, bottom: 0, left: 4 } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { padding: 8 },
        },
        y: {
          beginAtZero: true,
          grid: { color: "#edf0f5" },
          ticks: { precision: 0 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `资产数: ${ctx.parsed.y}`,
            afterLabel: (ctx) => {
              const bin = bins[ctx.dataIndex];
              return bin.selected ? `当前资产在该区间。${metricHelp.face_count}` : metricHelp.face_count;
            },
          },
        },
      },
    },
  });
}

function renderCards(scores) {
  const cards = document.getElementById("cards");
  cards.innerHTML = "";
  if (!scores.length) {
    cards.innerHTML = `<p>当前 manifest + VLM 还没有评分。选择资产后点击 Run Selected VLM。</p>`;
    return;
  }
  scores.forEach((row) => {
    const card = document.createElement("div");
    card.className = "card";
    const scoreHtml = scoreOrder
      .filter((key) => row.scores && key in row.scores)
      .map((key) => `<span title="${metricHelp[key] || ""}">${key}</span><b>${row.scores[key]}</b>`)
      .join("");
    card.innerHTML = `
      <strong>${row.uid}</strong>
      <div>${row.category || ""} · ${row.model || ""}</div>
      <div class="scores">${scoreHtml}</div>
      <p>${row.reason || ""}</p>
    `;
    cards.appendChild(card);
  });
}

function updateViewer() {
  const selected = document.getElementById("asset").value;
  const viewer = document.getElementById("viewer");
  if (!selected) {
    viewer.removeAttribute("src");
    return;
  }
  viewer.src = `/api/model/${encodeURIComponent(selected)}`;
}

async function renderViews(uid) {
  const box = document.getElementById("viewGrid");
  if (!uid) {
    box.innerHTML = `<p>请选择资产。</p>`;
    return;
  }
  const data = await getJson(`/api/views/${encodeURIComponent(uid)}`);
  const blocks = [
    ["RGB", data.rgb || []],
    ["Normal", data.normal || []],
  ];
  box.innerHTML = blocks
    .map(([label, images]) => {
      if (!images.length) return `<div class="view-group"><h3>${label}</h3><p>尚未渲染。</p></div>`;
      return `
        <div class="view-group">
          <h3>${label}</h3>
          <div class="thumbs">
            ${images.map((src, index) => `<figure><img src="${src}" alt="${label} view ${index}" /><figcaption>view ${index}</figcaption></figure>`).join("")}
          </div>
        </div>
      `;
    })
    .join("");
}

function renderGeometry(rows) {
  const tbody = document.getElementById("geometryRows");
  const selectedUid = document.getElementById("asset").value;
  tbody.innerHTML = "";
  rows.slice(0, 160).forEach((row) => {
    const g = row.geometry || {};
    const tr = document.createElement("tr");
    if (row.uid === selectedUid) tr.className = "selected-row";
    tr.innerHTML = `
      <td title="${metricHelp.uid}">${row.uid}</td>
      <td title="${metricHelp.category}">${row.category || ""}</td>
      <td title="${metricHelp.face_count}">${formatNumber(g.face_count)}</td>
      <td title="${metricHelp.vertex_count}">${formatNumber(g.vertex_count)}</td>
      <td title="${metricHelp.is_watertight}">${formatBool(g.is_watertight)}</td>
      <td title="${metricHelp.is_winding_consistent}">${formatBool(g.is_winding_consistent)}</td>
      <td title="${metricHelp.aspect_ratio}">${formatNumber(g.aspect_ratio)}</td>
      <td title="${metricHelp.degenerate_face_count}">${formatNumber(g.degenerate_face_count)}</td>
      <td title="${metricHelp.surface_area}">${formatNumber(g.surface_area)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function formatBool(value) {
  if (value === true) return "是";
  if (value === false) return "否";
  return "";
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString();
  return Math.round(n * 1000) / 1000;
}

function renderRenderSuccess(render) {
  const summary = document.getElementById("renderSummary");
  const rows = render.rows || [];
  summary.innerHTML = `
    <div class="summary-item" title="${metricHelp.render_success_rate}">
      <span>${help("渲染成功率", "render_success_rate")}</span>
      <b>${Math.round((render.success_rate || 0) * 100)}%</b>
    </div>
    <div class="summary-item"><span>当前 manifest</span><b>${render.complete || 0}/${render.assets || 0}</b></div>
  `;
  const tbody = document.getElementById("renderRows");
  const selectedUid = document.getElementById("asset").value;
  tbody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (row.uid === selectedUid) tr.className = "selected-row";
    tr.innerHTML = `
      <td>${row.uid}</td>
      <td>${row.rgb_views}</td>
      <td>${row.normal_views}</td>
      <td>${row.render_complete}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLiterature(data) {
  const box = document.getElementById("literatureIdeas");
  box.innerHTML = (data.ideas || [])
    .map(
      (row) => `
        <article class="idea">
          <div><b>${row.paper}</b><span>${row.direction}</span></div>
          <p><strong>借鉴：</strong>${row.idea}</p>
          <p><strong>当前实现：</strong>${row.implemented}</p>
        </article>
      `,
    )
    .join("");
}

async function loadAssets() {
  const manifest = document.getElementById("manifest").value;
  const data = await getJson(`/api/assets?manifest=${encodeURIComponent(manifest)}`);
  assetRows = data.assets || [];
  renderAssetSelect();
}

async function loadEvaluation() {
  const manifest = document.getElementById("manifest").value;
  const model = document.getElementById("model").value;
  evaluation = await getJson(`/api/evaluation?manifest=${encodeURIComponent(manifest)}&model=${encodeURIComponent(model)}`);
  renderScoreChart(evaluation.scores || []);
  renderCards(evaluation.scores || []);
  renderGeometry(evaluation.geometry || []);
  renderGeometryChart(evaluation.geometry || []);
  renderRenderSuccess(evaluation.render || {});
}

async function refreshContext() {
  renderContext();
  updateViewer();
  await renderViews(document.getElementById("asset").value);
  if (evaluation) {
    renderGeometry(evaluation.geometry || []);
    renderGeometryChart(evaluation.geometry || []);
    renderRenderSuccess(evaluation.render || {});
  }
}

async function init() {
  const [models, manifests, dashboard, literature] = await Promise.all([
    getJson("/api/models"),
    getJson("/api/manifests"),
    getJson("/api/dashboard"),
    getJson("/api/literature-ideas"),
  ]);
  fillSelect("model", models.models);
  fillManifestSelect(manifests.manifests);
  renderKpis(dashboard);
  renderLiterature(literature);

  document.getElementById("manifest").addEventListener("change", async () => {
    updateManifestHelp();
    await loadAssets();
    await loadEvaluation();
    await refreshContext();
  });
  document.getElementById("model").addEventListener("change", async () => {
    await loadEvaluation();
    await refreshContext();
  });
  document.getElementById("asset").addEventListener("change", refreshContext);

  document.getElementById("run").addEventListener("click", async () => {
    const req = {
      model: document.getElementById("model").value,
      manifest: document.getElementById("manifest").value,
      uid: document.getElementById("asset").value,
    };
    if (!req.uid) return;
    document.getElementById("log").textContent = "running real VLM evaluation for selected asset...";
    const result = await getJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (result.job_id) await pollJob(result.job_id);
    await loadAssets();
    await loadEvaluation();
    await refreshContext();
  });

  document.getElementById("geometryRun").addEventListener("click", async () => {
    const req = { manifest: document.getElementById("manifest").value };
    document.getElementById("log").textContent = "computing real geometry metrics for current manifest...";
    const result = await getJson("/api/geometry/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    document.getElementById("log").textContent = `${result.stdout || ""}\n${result.stderr || ""}`;
    await loadEvaluation();
    await refreshContext();
  });

  await loadAssets();
  await loadEvaluation();
  await refreshContext();
}

async function pollJob(jobId) {
  const log = document.getElementById("log");
  for (;;) {
    const job = await getJson(`/api/jobs/${jobId}`);
    log.textContent = `job ${jobId}\nstatus: ${job.status}\n\n${job.stdout || ""}\n${job.stderr || ""}`;
    if (job.status === "complete" || job.status === "failed" || job.status === "missing") return job;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

init().catch((err) => {
  document.getElementById("log").textContent = err.stack || String(err);
});
