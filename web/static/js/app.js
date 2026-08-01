const palette = ["#fb7185", "#38bdf8", "#a78bfa", "#fbbf24", "#34d399", "#94a3b8"];

function setupCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio;
  canvas.height = rect.height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  return { context, width: rect.width, height: rect.height };
}

function emptyChart(context, width, height) {
  context.fillStyle = "#94a3b8";
  context.font = "14px system-ui";
  context.textAlign = "center";
  context.fillText("表示するデータがありません", width / 2, height / 2);
}

function drawPie() {
  const canvas = document.querySelector("#pie-chart");
  if (!canvas) return;
  const { context, width, height } = setupCanvas(canvas);
  const { labels, values } = window.KAKEIBO_CHARTS.category;
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!total) return emptyChart(context, width, height);
  const radius = Math.min(82, height * .38, width * .2);
  const centerX = Math.min(width * .28, 120);
  const centerY = height / 2;
  let angle = -Math.PI / 2;
  values.forEach((value, index) => {
    const next = angle + (value / total) * Math.PI * 2;
    context.beginPath(); context.moveTo(centerX, centerY);
    context.arc(centerX, centerY, radius, angle, next);
    context.closePath(); context.fillStyle = palette[index % palette.length]; context.fill();
    angle = next;
  });
  context.beginPath(); context.arc(centerX, centerY, radius * .57, 0, Math.PI * 2);
  context.fillStyle = "#111827"; context.fill();
  context.fillStyle = "#f8fafc"; context.textAlign = "center"; context.font = "700 14px system-ui";
  context.fillText(`${total.toLocaleString()}円`, centerX, centerY + 5);
  const legendX = Math.max(centerX + radius + 30, width * .48);
  labels.forEach((label, index) => {
    const y = 30 + index * 31;
    context.fillStyle = palette[index % palette.length]; context.fillRect(legendX, y, 9, 9);
    context.fillStyle = "#f8fafc"; context.textAlign = "left"; context.font = "600 12px system-ui";
    context.fillText(label, legendX + 17, y + 9);
    context.fillStyle = "#94a3b8"; context.font = "11px system-ui";
    context.fillText(`${values[index].toLocaleString()}円`, legendX + 17, y + 24);
  });
}

function drawBars() {
  const canvas = document.querySelector("#bar-chart");
  if (!canvas) return;
  const { context, width, height } = setupCanvas(canvas);
  const { labels, values } = window.KAKEIBO_CHARTS.monthly;
  if (!values.length) return emptyChart(context, width, height);
  const left = 10, right = 10, top = 25, bottom = 30;
  const chartHeight = height - top - bottom;
  const maximum = Math.max(...values);
  const slot = (width - left - right) / values.length;
  context.strokeStyle = "#293548"; context.lineWidth = 1;
  [0, .5, 1].forEach(ratio => {
    const y = top + chartHeight * ratio;
    context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y); context.stroke();
  });
  values.forEach((value, index) => {
    const barHeight = (value / maximum) * chartHeight;
    const barWidth = Math.min(35, slot * .58);
    const x = left + slot * index + (slot - barWidth) / 2;
    const y = top + chartHeight - barHeight;
    context.fillStyle = "#3b82f6"; context.fillRect(x, y, barWidth, barHeight);
    context.fillStyle = "#94a3b8"; context.textAlign = "center"; context.font = "10px system-ui";
    context.fillText(labels[index].slice(2).replace("-", "/"), x + barWidth / 2, height - 9);
  });
}

function drawAssetLine() {
  const canvas = document.querySelector("#asset-line-chart");
  if (!canvas) return;
  const data = window.KAKEIBO_CHARTS.assets;
  if (window.Chart) {
    const existing = Chart.getChart(canvas);
    if (existing) { existing.resize(); return; }
    new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          { label: "前月残高", data: data.previous, borderColor: "#94a3b8", backgroundColor: "#94a3b8", borderDash: [5, 4], tension: .25 },
          { label: "今月残高", data: data.values, borderColor: "#38bdf8", backgroundColor: "rgba(56,189,248,.16)", fill: true, tension: .25 },
          { label: "翌月繰越", data: data.carryover, borderColor: "#a78bfa", backgroundColor: "#a78bfa", tension: .25 }
        ]
      },
      options: chartOptions("資産残高")
    });
    return;
  }
  const { context, width, height } = setupCanvas(canvas);
  const { labels, values } = data;
  if (!values.length || !values.some(value => value !== 0)) return emptyChart(context, width, height);
  const left = 18, right = 18, top = 28, bottom = 34;
  const chartWidth = width - left - right, chartHeight = height - top - bottom;
  const maximum = Math.max(...values), minimum = Math.min(0, ...values);
  const range = maximum - minimum || 1;
  const point = (value, index) => ({
    x: left + (labels.length === 1 ? chartWidth / 2 : index * chartWidth / (labels.length - 1)),
    y: top + (maximum - value) / range * chartHeight
  });
  context.strokeStyle = "#293548"; context.lineWidth = 1;
  [0, .5, 1].forEach(ratio => {
    const y = top + ratio * chartHeight;
    context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y); context.stroke();
  });
  const gradient = context.createLinearGradient(0, top, 0, height - bottom);
  gradient.addColorStop(0, "rgba(56, 189, 248, .30)"); gradient.addColorStop(1, "rgba(56, 189, 248, 0)");
  context.beginPath();
  values.forEach((value, index) => { const p = point(value, index); index ? context.lineTo(p.x, p.y) : context.moveTo(p.x, p.y); });
  context.lineTo(width - right, height - bottom); context.lineTo(left, height - bottom); context.closePath(); context.fillStyle = gradient; context.fill();
  context.beginPath();
  values.forEach((value, index) => { const p = point(value, index); index ? context.lineTo(p.x, p.y) : context.moveTo(p.x, p.y); });
  context.strokeStyle = "#38bdf8"; context.lineWidth = 3; context.lineJoin = "round"; context.stroke();
  values.forEach((value, index) => {
    const p = point(value, index); context.beginPath(); context.arc(p.x, p.y, 3.5, 0, Math.PI * 2); context.fillStyle = "#e0f2fe"; context.fill();
    if (index % Math.max(1, Math.ceil(labels.length / 6)) === 0 || index === labels.length - 1) {
      context.fillStyle = "#94a3b8"; context.textAlign = "center"; context.font = "10px system-ui";
      context.fillText(labels[index].slice(2).replace("-", "/"), p.x, height - 10);
    }
  });
}

function drawCashflow() {
  const canvas = document.querySelector("#cashflow-chart");
  if (!canvas) return;
  const data = window.KAKEIBO_CHARTS.cashflow;
  if (window.Chart) {
    const existing = Chart.getChart(canvas);
    if (existing) { existing.resize(); return; }
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { label: "収入", data: data.income, backgroundColor: "rgba(34,197,94,.78)", borderColor: "#22c55e", borderWidth: 1 },
          { label: "支出", data: data.expense, backgroundColor: "rgba(239,68,68,.78)", borderColor: "#ef4444", borderWidth: 1 },
          { label: "収支", data: data.net, backgroundColor: "rgba(59,130,246,.78)", borderColor: "#3b82f6", borderWidth: 1 }
        ]
      },
      options: chartOptions("収支")
    });
    return;
  }
  const { context, width, height } = setupCanvas(canvas);
  const { labels, net } = data;
  if (!net.length) return emptyChart(context, width, height);
  const left = 12, right = 12, top = 24, bottom = 34;
  const chartHeight = height - top - bottom;
  const limit = Math.max(...net.map(value => Math.abs(value)), 1);
  const zeroY = top + chartHeight / 2;
  const slot = (width - left - right) / net.length;
  context.strokeStyle = "#475569"; context.lineWidth = 1;
  context.beginPath(); context.moveTo(left, zeroY); context.lineTo(width - right, zeroY); context.stroke();
  net.forEach((value, index) => {
    const barWidth = Math.min(34, slot * .58);
    const barHeight = Math.abs(value) / limit * chartHeight * .45;
    const x = left + slot * index + (slot - barWidth) / 2;
    const y = value >= 0 ? zeroY - barHeight : zeroY;
    context.fillStyle = value >= 0 ? "#22c55e" : "#ef4444";
    context.fillRect(x, y, barWidth, Math.max(barHeight, value === 0 ? 2 : 1));
    if (index % Math.max(1, Math.ceil(labels.length / 6)) === 0 || index === labels.length - 1) {
      context.fillStyle = "#94a3b8"; context.textAlign = "center"; context.font = "10px system-ui";
      context.fillText(labels[index].slice(2).replace("-", "/"), x + barWidth / 2, height - 10);
    }
  });
  context.fillStyle = "#22c55e"; context.fillRect(left, 4, 10, 10);
  context.fillStyle = "#cbd5e1"; context.textAlign = "left"; context.font = "11px system-ui";
  context.fillText("黒字", left + 15, 13);
  context.fillStyle = "#ef4444"; context.fillRect(left + 55, 4, 10, 10);
  context.fillStyle = "#cbd5e1"; context.fillText("赤字", left + 70, 13);
}

function chartOptions(label) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: "#cbd5e1", usePointStyle: true } },
      tooltip: { callbacks: { label: context => `${context.dataset.label}: ${Number(context.raw).toLocaleString()}円` } }
    },
    scales: {
      x: { ticks: { color: "#94a3b8", maxRotation: 0, autoSkip: true }, grid: { color: "rgba(41,53,72,.45)" } },
      y: { ticks: { color: "#94a3b8", callback: value => `${Number(value).toLocaleString()}円` }, grid: { color: "rgba(41,53,72,.65)" }, title: { display: false, text: label } }
    }
  };
}

let installPrompt;
const installButton = document.querySelector("#install-button");
window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault(); installPrompt = event; installButton.hidden = false;
});
installButton?.addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt(); await installPrompt.userChoice; installPrompt = null; installButton.hidden = true;
});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js");
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { drawPie(); drawBars(); drawAssetLine(); drawCashflow(); }, 120); });
drawPie(); drawBars(); drawAssetLine(); drawCashflow();
