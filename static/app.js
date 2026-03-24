const $ = (id) => document.getElementById(id);

const cpuCtx = $("cpuChart").getContext("2d");
const memCtx = $("memChart").getContext("2d");

const cpuChart = new Chart(cpuCtx, {
  type: "line",
  data: { labels: [], datasets: [{ label: "CPU %", data: [], borderColor: "#34d399", tension: 0.2 }] },
  options: { animation: false, plugins: { legend: { labels: { color: "#e5e7eb" } } }, scales: { x: { ticks: { color: "#9ca3af" } }, y: { ticks: { color: "#9ca3af" } } } }
});

const memChart = new Chart(memCtx, {
  type: "line",
  data: { labels: [], datasets: [{ label: "Memory MB", data: [], borderColor: "#60a5fa", tension: 0.2 }] },
  options: { animation: false, plugins: { legend: { labels: { color: "#e5e7eb" } } }, scales: { x: { ticks: { color: "#9ca3af" } }, y: { ticks: { color: "#9ca3af" } } } }
});

function readConfig() {
  return {
    interval: Number($("interval").value),
    top_n: Number($("top_n").value),
    baseline_window: Number($("baseline_window").value),
    cpu_z_threshold: Number($("cpu_z_threshold").value),
    memory_window: Number($("memory_window").value),
    memory_leak_threshold_mb: Number($("memory_leak_threshold_mb").value),
    output: $("output").value,
    dry_run: $("dry_run").checked,
  };
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const txt = await response.text();
    throw new Error(txt || `Request failed: ${response.status}`);
  }
  return response.json();
}

function renderSummary(status) {
  const s = status.summary || {};
  const entries = [
    ["Running", status.running ? "Yes" : "No"],
    ["Total Samples", s.total_samples || 0],
    ["Unique Processes", s.unique_processes || 0],
    ["CPU Anomalies", s.cpu_anomalies || 0],
    ["Mem Leak Suspicions", s.memory_leak_suspicions || 0],
  ];

  $("summaryCards").innerHTML = entries
    .map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`)
    .join("");
  $("runState").textContent = status.running ? "Running" : "Stopped";
  $("runState").style.color = status.running ? "#34d399" : "#f59e0b";
}

function renderSamples(samples) {
  const tbody = $("samplesTable").querySelector("tbody");
  tbody.innerHTML = samples
    .slice(-100)
    .reverse()
    .map((r) => {
      const cls = r.cpu_anomaly ? "anomaly" : r.memory_leak_suspected ? "memleak" : "";
      return `<tr class="${cls}">
        <td>${new Date(r.timestamp).toLocaleTimeString()}</td>
        <td>${r.pid}</td>
        <td>${r.name}</td>
        <td>${r.cpu_percent.toFixed(2)}</td>
        <td>${r.memory_mb.toFixed(2)}</td>
        <td>${r.cpu_anomaly}</td>
        <td>${r.memory_leak_suspected}</td>
        <td>${r.notes || ""}</td>
      </tr>`;
    })
    .join("");

  const chartRows = samples.slice(-50);
  cpuChart.data.labels = chartRows.map((r) => new Date(r.timestamp).toLocaleTimeString());
  cpuChart.data.datasets[0].data = chartRows.map((r) => r.cpu_percent);
  cpuChart.update();

  memChart.data.labels = chartRows.map((r) => new Date(r.timestamp).toLocaleTimeString());
  memChart.data.datasets[0].data = chartRows.map((r) => r.memory_mb);
  memChart.update();
}

function renderAlerts(alerts) {
  const tbody = $("alertsTable").querySelector("tbody");
  tbody.innerHTML = alerts
    .slice(-100)
    .reverse()
    .map(
      (a) => `<tr>
      <td>${new Date(a.timestamp).toLocaleTimeString()}</td>
      <td>${a.type}</td>
      <td>${a.pid}</td>
      <td>${a.name}</td>
      <td>${a.cpu_percent.toFixed(2)}</td>
      <td>${a.memory_mb.toFixed(2)}</td>
      <td>${a.message}</td>
    </tr>`
    )
    .join("");
}

async function refresh() {
  try {
    const [status, samples, alerts] = await Promise.all([
      api("/api/status"),
      api("/api/samples?limit=300"),
      api("/api/alerts?limit=300"),
    ]);
    renderSummary(status);
    renderSamples(samples);
    renderAlerts(alerts);
  } catch (err) {
    console.error(err);
  }
}

$("startBtn").addEventListener("click", async () => {
  try {
    await api("/api/start", { method: "POST", body: JSON.stringify(readConfig()) });
    refresh();
  } catch (err) {
    alert(`Start failed: ${err.message}`);
  }
});

$("stopBtn").addEventListener("click", async () => {
  try {
    await api("/api/stop", { method: "POST" });
    refresh();
  } catch (err) {
    alert(`Stop failed: ${err.message}`);
  }
});

refresh();
setInterval(refresh, 2000);
