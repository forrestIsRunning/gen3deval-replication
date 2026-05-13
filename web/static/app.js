let chart;

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

function averages(scores) {
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

function renderChart(scores) {
  const data = averages(scores);
  const ctx = document.getElementById("chart");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.dimension),
      datasets: [{ label: "平均分", data: data.map((d) => d.score), backgroundColor: "#2563eb" }],
    },
    options: {
      responsive: true,
      scales: { y: { min: 0, max: 10 } },
      plugins: { legend: { display: false } },
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
      .map(([key, value]) => `<span>${key}</span><b>${value}</b>`)
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

function renderAssets(scores) {
  const asset = document.getElementById("asset");
  asset.innerHTML = "";
  scores.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.uid;
    option.textContent = row.uid;
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

async function loadScores() {
  const data = await getJson("/api/scores");
  renderChart(data.scores);
  renderCards(data.scores);
  renderAssets(data.scores);
}

async function loadGeometry() {
  const data = await getJson("/api/geometry");
  const tbody = document.getElementById("geometryRows");
  tbody.innerHTML = "";
  data.geometry.forEach((row) => {
    const g = row.geometry || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.uid}</td>
      <td>${g.face_count ?? ""}</td>
      <td>${g.vertex_count ?? ""}</td>
      <td>${g.component_count ?? ""}</td>
      <td>${g.is_watertight ?? ""}</td>
      <td>${g.aspect_ratio ?? ""}</td>
      <td>${g.surface_area ?? ""}</td>
    `;
    tbody.appendChild(tr);
  });
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
      mock: document.getElementById("mock").checked,
    };
    document.getElementById("log").textContent = "running...";
    const result = await getJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    document.getElementById("log").textContent = `${result.stdout}\n${result.stderr || ""}`;
    await loadScores();
  });
  document.getElementById("geometryRun").addEventListener("click", async () => {
    const req = {
      manifest: document.getElementById("manifest").value,
      limit: Number(document.getElementById("limit").value),
    };
    document.getElementById("log").textContent = "computing geometry metrics...";
    const result = await getJson("/api/geometry/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    document.getElementById("log").textContent = `${result.stdout}\n${result.stderr || ""}`;
    await loadGeometry();
  });
  await loadScores();
  await loadGeometry();
}

init().catch((err) => {
  document.getElementById("log").textContent = err.stack || String(err);
});
