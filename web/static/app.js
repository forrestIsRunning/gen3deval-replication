let scoreChart;
let geometryChart;
let geometryRows = [];
let scoreRows = [];

const metricHelp = {
  text_fidelity: "文本还原度。VLM 查看多视角 RGB，并比较目标 prompt 与 3D 资产是否一致。",
  image_fidelity: "图片还原度。用于 image-to-3D，比较输入图与生成资产的形状、颜色、部件一致性。",
  appearance: "外观质量。VLM 判断整体完整度、可读性、美观度和明显视觉缺陷。",
  surface_quality: "表面质量。VLM 查看 normal 图和 RGB 图，判断噪声、破面、过度平滑、浮片等问题。",
  geometry_coherence: "几何一致性。VLM 判断结构比例、部件连接、是否有穿模或漂浮组件。",
  texture_material: "贴图材质质量。VLM 判断纹理清晰度、材质可信度、颜色和表面观感。",
  multi_view_consistency: "多视角一致性。VLM 比较不同视角是否为同一对象，检测 Janus/背面崩坏。",
  overall: "综合质量。VLM 基于各维度给出的总体可用性评分。",
  face_count: "三角面数量。trimesh 读取 mesh 后统计 faces，越高通常渲染和编辑成本越高。",
  vertex_count: "顶点数量。trimesh 读取 mesh 后统计 vertices，衡量模型复杂度。",
  aspect_ratio: "包围盒最长边 / 最短边。用于发现极端扁平、拉伸或尺度异常资产。",
  surface_area: "mesh 表面积。trimesh.area 计算，可辅助发现尺度异常。",
  is_watertight: "mesh 是否封闭。trimesh.is_watertight，打印、仿真、CAD 场景更关键。",
  is_winding_consistent: "面朝向是否一致。影响法线、阴影、渲染和导出质量。",
  degenerate_face_count: "面积接近 0 的退化面数量。用于发现坏 mesh 和导出/渲染隐患。",
  render_success_rate: "渲染成功率。Blender 是否能为资产生成完整 4-view RGB 和 normal 图。",
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

function renderKpis(dashboard) {
  const kpis = document.getElementById("kpis");
  const cards = [
    ["几何资产", `${dashboard.geometry.ok}/${dashboard.geometry.assets}`, "120 个真实 Objaverse-LVIS 资产的可计算几何指标。"],
    ["渲染成功", `${dashboard.render.complete}/${dashboard.render.assets}`, metricHelp.render_success_rate],
    ["VLM 样本", `${dashboard.scores.assets}`, "已有真实渲染图上的真实 VLM 评分样本数。"],
    ["论文覆盖", `${dashboard.literature.download_ok}/${dashboard.literature.papers}`, "4 个方向各 10 篇 arXiv/相关论文 PDF 下载覆盖。"],
  ];
  kpis.innerHTML = cards
    .map(([label, value, tip]) => `<div class="kpi" title="${tip}"><span>${label}</span><b>${value}</b></div>`)
    .join("");
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
  return Object.keys(sums).map((key) => ({
    dimension: key,
    score: Math.round((sums[key] / counts[key]) * 100) / 100,
  }));
}

function renderScoreChart(scores) {
  const data = scoreAverages(scores);
  const ctx = document.getElementById("chart");
  if (scoreChart) scoreChart.destroy();
  scoreChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.dimension),
      datasets: [{ data: data.map((d) => d.score), backgroundColor: "#2563eb" }],
    },
    options: {
      responsive: true,
      scales: { y: { min: 0, max: 10 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => metricHelp[data[ctx.dataIndex].dimension] || "",
          },
        },
      },
    },
  });
}

function renderGeometryChart(rows) {
  const top = rows
    .filter((row) => row.ok && row.geometry)
    .slice(0, 40)
    .map((row) => ({ uid: row.uid.slice(0, 6), faces: row.geometry.face_count || 0 }));
  const ctx = document.getElementById("geometryChart");
  if (geometryChart) geometryChart.destroy();
  geometryChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((d) => d.uid),
      datasets: [{ data: top.map((d) => d.faces), backgroundColor: "#0f766e" }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { afterLabel: () => metricHelp.face_count } },
      },
    },
  });
}

function renderCards(scores) {
  const cards = document.getElementById("cards");
  cards.innerHTML = "";
  scores.forEach((row) => {
    const card = document.createElement("div");
    card.className = "card";
    const scoreHtml = Object.entries(row.scores || {})
      .map(([key, value]) => `<span title="${metricHelp[key] || ""}">${key}</span><b>${value}</b>`)
      .join("");
    card.innerHTML = `
      <strong>${row.uid}</strong>
      <div>${row.category || ""}</div>
      <div class="scores">${scoreHtml}</div>
      <p>${row.reason || ""}</p>
    `;
    cards.appendChild(card);
  });
}

function renderAssets() {
  const asset = document.getElementById("asset");
  const seen = new Set();
  const rows = [...scoreRows, ...geometryRows];
  asset.innerHTML = "";
  rows.forEach((row) => {
    if (!row.uid || seen.has(row.uid)) return;
    seen.add(row.uid);
    const option = document.createElement("option");
    option.value = row.uid;
    option.textContent = `${row.uid} ${row.category ? `(${row.category})` : ""}`;
    asset.appendChild(option);
  });
  updateViewer();
}

function updateViewer() {
  const asset = document.getElementById("asset");
  const viewer = document.getElementById("viewer");
  const selected = asset.value;
  if (!selected) {
    viewer.removeAttribute("src");
    return;
  }
  viewer.src = `/api/model/${encodeURIComponent(selected)}`;
}

function renderGeometry(rows) {
  const tbody = document.getElementById("geometryRows");
  tbody.innerHTML = "";
  rows.slice(0, 120).forEach((row) => {
    const g = row.geometry || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.uid}</td>
      <td>${row.category || ""}</td>
      <td>${g.face_count ?? ""}</td>
      <td>${g.vertex_count ?? ""}</td>
      <td>${g.is_watertight ?? ""}</td>
      <td>${g.is_winding_consistent ?? ""}</td>
      <td>${g.aspect_ratio ?? ""}</td>
      <td>${g.degenerate_face_count ?? ""}</td>
      <td>${g.surface_area ?? ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderRenderSuccess(data) {
  const summary = document.getElementById("renderSummary");
  const s = data.summary || {};
  summary.innerHTML = `
    <div class="summary-item" title="${metricHelp.render_success_rate}">
      <span>${help("render_success_rate", "render_success_rate")}</span>
      <b>${Math.round((s.success_rate || 0) * 100)}%</b>
    </div>
    <div class="summary-item"><span>complete</span><b>${s.complete || 0}/${s.assets || 0}</b></div>
  `;
  const tbody = document.getElementById("renderRows");
  tbody.innerHTML = "";
  (data.rows || []).forEach((row) => {
    const tr = document.createElement("tr");
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
  const bars = document.getElementById("literatureBars");
  const entries = Object.entries(data.by_direction || {});
  bars.innerHTML = entries
    .map(([key, value]) => `<div class="bar-row"><span>${key}</span><b>${value}</b><em style="width:${Math.min(100, value * 10)}%"></em></div>`)
    .join("");
}

async function loadScores() {
  const data = await getJson("/api/scores");
  scoreRows = data.scores;
  renderScoreChart(scoreRows);
  renderCards(scoreRows);
  renderAssets();
}

async function loadGeometry() {
  const data = await getJson("/api/geometry");
  geometryRows = data.geometry;
  renderGeometry(geometryRows);
  renderGeometryChart(geometryRows);
  renderAssets();
}

async function loadDashboard() {
  const [dashboard, render, literature] = await Promise.all([
    getJson("/api/dashboard"),
    getJson("/api/render-success"),
    getJson("/api/literature"),
  ]);
  renderKpis(dashboard);
  renderRenderSuccess(render);
  renderLiterature(literature);
}

async function init() {
  const [models, manifests] = await Promise.all([getJson("/api/models"), getJson("/api/manifests")]);
  fillSelect("model", models.models);
  fillSelect("manifest", manifests.manifests);
  document.getElementById("asset").addEventListener("change", updateViewer);
  document.getElementById("run").addEventListener("click", async () => {
    const req = {
      model: document.getElementById("model").value,
      manifest: document.getElementById("manifest").value,
      limit: Number(document.getElementById("limit").value),
    };
    document.getElementById("log").textContent = "running real VLM evaluation...";
    const result = await getJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    document.getElementById("log").textContent = `${result.stdout}\n${result.stderr || ""}`;
    await loadScores();
    await loadDashboard();
  });
  document.getElementById("geometryRun").addEventListener("click", async () => {
    const req = {
      manifest: document.getElementById("manifest").value,
      limit: Number(document.getElementById("limit").value),
    };
    document.getElementById("log").textContent = "computing real geometry metrics...";
    const result = await getJson("/api/geometry/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    document.getElementById("log").textContent = `${result.stdout}\n${result.stderr || ""}`;
    await loadGeometry();
    await loadDashboard();
  });
  await loadDashboard();
  await loadScores();
  await loadGeometry();
}

init().catch((err) => {
  document.getElementById("log").textContent = err.stack || String(err);
});
