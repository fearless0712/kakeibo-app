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
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { drawPie(); drawBars(); }, 120); });
drawPie(); drawBars();
