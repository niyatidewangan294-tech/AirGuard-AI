/**
 * dashboard.js
 * ────────────
 * AirGuard AI – Dashboard Frontend Logic (Phase 1 + Phase 2)
 *
 * Phase 2 additions:
 *  - Confidence-band shading on the forecast chart
 *  - PM2.5 overlay line on the history bar chart
 *  - Best outdoor window badge
 *  - Hourly forecast table (next 12 hours)
 *  - Early warning banner (auto-shows at top of dashboard on page load)
 *  - RAG health advisory panel (/api/rag)
 *  - Community "mark done" interaction + progress bar
 */

// ── State ──────────────────────────────────────────────────────────────────────
let currentCity   = "Delhi";
let currentReport = null;
let forecastChart = null;
let historyChart  = null;
let communityDone = 0;      // count of community actions marked done
let communityTotal = 0;

// ── AQI colour helper ─────────────────────────────────────────────────────────
function aqiColor(aqi) {
  if (aqi <= 50)  return "#00e400";
  if (aqi <= 100) return "#ffff00";
  if (aqi <= 150) return "#ff7e00";
  if (aqi <= 200) return "#ff0000";
  if (aqi <= 300) return "#8f3f97";
  return "#7e0023";
}

// Hex → rgba helper for chart fills
function hexRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── Gauge ring ─────────────────────────────────────────────────────────────────
function updateGauge(aqi) {
  const circle = document.getElementById("gauge-fill");
  if (!circle) return;
  const circumference = 2 * Math.PI * 56;
  const fraction  = Math.min(aqi / 500, 1);
  circle.style.strokeDasharray  = `${circumference}`;
  circle.style.strokeDashoffset = circumference * (1 - fraction);
  circle.style.stroke = aqiColor(aqi);
  document.getElementById("aqi-value").textContent  = aqi;
  document.getElementById("aqi-value").style.color  = aqiColor(aqi);
}

// ── Status dot ────────────────────────────────────────────────────────────────
function setStatus(state) {
  const dot = document.getElementById("status-dot");
  const txt = document.getElementById("status-text");
  if (!dot || !txt) return;
  dot.className = "status-dot";
  dot.style.background = "";
  if (state === "loading") { dot.classList.add("loading"); txt.textContent = "Fetching…"; }
  else if (state === "live")   { txt.textContent = "Live data"; }
  else if (state === "sample") { dot.style.background = "var(--warning)"; txt.textContent = "Sample data"; }
  else if (state === "error")  { dot.classList.add("error"); txt.textContent = "Error"; }
}

// ── Skeletons ─────────────────────────────────────────────────────────────────
function showSkeleton() {
  document.querySelectorAll(".skeleton-area").forEach(el => {
    el.innerHTML = '<div class="skeleton" style="height:1.1rem;margin-bottom:0.5rem;"></div>'.repeat(4);
  });
}

// ── Format helpers ────────────────────────────────────────────────────────────
function fmt(val, decimals = 1) {
  const n = parseFloat(val);
  return isNaN(n) ? "—" : n.toFixed(decimals);
}

function aqiBg(aqi) {
  return hexRgba(aqiColor(aqi), 0.18);
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — Early Warning Banner
// Injected directly below the navbar when the report has active warnings
// ─────────────────────────────────────────────────────────────────────────────
function renderEarlyWarningBanner(report) {
  // Remove any existing banner first
  const existing = document.getElementById("early-warning-bar");
  if (existing) existing.remove();

  if (!report.warnings || report.warnings.length === 0) return;

  const banner = document.createElement("div");
  banner.id = "early-warning-bar";
  banner.className = "early-warning-bar";

  const itemsHtml = report.warnings.map(w => `
    <div class="warn-item">
      ${w.message}
      <span class="warn-advice"> — ${w.advice}</span>
    </div>`).join("");

  banner.innerHTML = `
    <span class="warn-icon">🚨</span>
    <div class="warn-body">
      <div class="warn-title">Early Warning: Air Quality Forecast Alert for ${report.city}</div>
      <div class="warn-items">${itemsHtml}</div>
    </div>`;

  // Insert right after the navbar
  const navbar = document.querySelector(".navbar");
  if (navbar && navbar.nextSibling) {
    navbar.parentNode.insertBefore(banner, navbar.nextSibling);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// AQI Hero Card
// ─────────────────────────────────────────────────────────────────────────────
function renderAqiHero(report) {
  updateGauge(report.aqi);
  document.getElementById("aqi-city").textContent        = report.city;
  document.getElementById("aqi-description").textContent = report.category.description;

  const badge = document.getElementById("aqi-badge");
  badge.textContent        = `${report.category.emoji}  ${report.category.level}`;
  badge.style.background   = report.category.color + "22";
  badge.style.color        = report.category.color;
  badge.style.borderColor  = report.category.color + "55";
  badge.style.border       = `1px solid ${report.category.color}55`;

  const src = document.getElementById("data-source");
  if (src) {
    src.textContent = report.data_source === "live"
      ? "🟢 Live AQI data"
      : "🟡 Sample data (set AQICN_API_KEY in .env for live data)";
    src.className = `source-badge ${report.data_source}`;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pollutant grid
// ─────────────────────────────────────────────────────────────────────────────
function renderPollutants(report) {
  const grid = document.getElementById("pollutant-grid");
  if (!grid) return;

  const pollutants = [
    { key: "pm25", label: "PM2.5", unit: "µg/m³" },
    { key: "pm10", label: "PM10",  unit: "µg/m³" },
    { key: "no2",  label: "NO₂",   unit: "µg/m³" },
    { key: "o3",   label: "O₃",    unit: "µg/m³" },
    { key: "so2",  label: "SO₂",   unit: "µg/m³" },
    { key: "co",   label: "CO",    unit: "mg/m³"  },
  ];

  grid.innerHTML = pollutants.map(p => `
    <div class="pollutant-item">
      <div class="pollutant-name">${p.label}</div>
      <div class="pollutant-value">${fmt(report[p.key])}</div>
      <div class="pollutant-unit">${p.unit}</div>
    </div>`).join("");

  const domEl = document.getElementById("dominant-pollutant");
  if (domEl) {
    const d = report.dominant_pollutant;
    if (d) {
      domEl.innerHTML = `<strong>⚠️ Dominant:</strong> ${d.name} (${fmt(d.value)} — ${d.ratio}× threshold) — ${d.health_note}`;
      domEl.className = "warning-banner mt-sm";
    } else {
      domEl.innerHTML = "✅ All pollutants within safe thresholds.";
      domEl.className = "source-badge live mt-sm";
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Health Recommendations
// ─────────────────────────────────────────────────────────────────────────────
function renderRecommendations(report) {
  const list = document.getElementById("rec-list");
  if (!list) return;

  list.innerHTML = report.recommendations.map(r => `<li class="rec-item">${r}</li>`).join("");

  const modelEl = document.getElementById("model-badge");
  if (modelEl) {
    if (report.ai_generated) {
      modelEl.innerHTML = `<span class="ai-badge">✨ ${report.model_used}</span>`;
    } else {
      modelEl.innerHTML = `<span class="ai-badge" style="color:var(--warning);border-color:rgba(210,153,34,0.3)">📋 ${report.model_used}</span>`;
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Daily Plan + Outdoor Advice
// ─────────────────────────────────────────────────────────────────────────────
function renderDailyPlan(report) {
  const el = document.getElementById("daily-plan-text");
  if (el) el.textContent = report.daily_plan;
  const outdoorEl = document.getElementById("outdoor-advice");
  if (outdoorEl) outdoorEl.textContent = report.outdoor_advice;
}

// ─────────────────────────────────────────────────────────────────────────────
// Warnings card (inside the health risk card)
// ─────────────────────────────────────────────────────────────────────────────
function renderWarnings(report) {
  const container = document.getElementById("warnings-container");
  if (!container) return;

  if (!report.warnings || report.warnings.length === 0) {
    container.innerHTML = '<div class="source-badge live">✅ No air quality warnings for the next 24 hours.</div>';
    return;
  }

  container.innerHTML = `<div class="warning-list">
    ${report.warnings.map(w => `
      <div class="warning-banner">
        <span class="icon">⚠️</span>
        <div>
          <div>${w.message}</div>
          <div style="font-size:0.78rem;color:var(--text-muted);margin-top:0.2rem">${w.advice}</div>
        </div>
      </div>`).join("")}
  </div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Vulnerable groups
// ─────────────────────────────────────────────────────────────────────────────
function renderVulnerableGroups(report) {
  const el = document.getElementById("vulnerable-groups");
  if (!el) return;

  if (!report.vulnerable_groups || report.vulnerable_groups.length === 0) {
    el.innerHTML = '<p class="source-badge live">No specific groups at elevated risk today.</p>';
    return;
  }
  el.innerHTML = `<div class="tag-list">${report.vulnerable_groups.map(g => `<span class="tag">${g}</span>`).join("")}</div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — Forecast chart with confidence band + best window badge
// ─────────────────────────────────────────────────────────────────────────────
function renderForecastChart(report) {
  const canvas = document.getElementById("forecast-chart");
  if (!canvas) return;

  if (forecastChart) { forecastChart.destroy(); }
  const ctx = canvas.getContext("2d");

  forecastChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: report.chart_labels,
      datasets: [
        // ── Upper confidence band (filled to lower) ──
        {
          label: "Upper band",
          data:  report.chart_high,
          borderColor:     "transparent",
          backgroundColor: "rgba(88,166,255,0.1)",
          fill: "+1",          // fill down to dataset index+1 (the lower band)
          tension: 0.4,
          pointRadius: 0,
        },
        // ── AQI line ──
        {
          label: "AQI",
          data:  report.chart_data,
          borderColor: "#58a6ff",
          backgroundColor: "transparent",
          fill: false,
          tension: 0.4,
          pointBackgroundColor: report.chart_data.map(v => aqiColor(v)),
          pointRadius: 5,
          pointHoverRadius: 7,
          borderWidth: 2,
        },
        // ── Lower confidence band ──
        {
          label: "Lower band",
          data:  report.chart_low,
          borderColor:     "transparent",
          backgroundColor: "rgba(88,166,255,0.1)",
          fill: false,
          tension: 0.4,
          pointRadius: 0,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.dataset.label === "AQI") return `AQI: ${ctx.parsed.y}`;
              if (ctx.dataset.label === "Upper band") return `High: ${ctx.parsed.y}`;
              if (ctx.dataset.label === "Lower band") return `Low: ${ctx.parsed.y}`;
              return "";
            }
          }
        }
      },
      scales: {
        x: { ticks: { color: "#8b949e", font: { size: 11 } }, grid: { color: "#21262d" } },
        y: { ticks: { color: "#8b949e", font: { size: 11 } }, grid: { color: "#21262d" }, beginAtZero: true }
      }
    }
  });

  // ── Forecast summary text ──
  const summaryEl = document.getElementById("forecast-summary");
  if (summaryEl) summaryEl.textContent = report.forecast_summary;

  // ── Best outdoor window badge ──
  const bwEl = document.getElementById("best-window-badge");
  if (bwEl && report.best_window) {
    const bw = report.best_window;
    bwEl.innerHTML = `🌿 Best outdoor time today: <span class="bw-time">${bw.start} – ${bw.end}</span> (forecast AQI <span class="bw-time">${bw.aqi}</span>)`;
    bwEl.classList.remove("hidden");
  }

  // ── Confidence note ──
  const sigmaEl = document.getElementById("sigma-note");
  if (sigmaEl) {
    sigmaEl.textContent = `Shaded area = ±1 standard deviation based on 7-day history (σ = ${report.sigma} AQI units)`;
  }

  // ── Hourly table ──
  renderHourlyTable(report);
}

// ── Hourly forecast table ──────────────────────────────────────────────────
function renderHourlyTable(report) {
  const tableEl = document.getElementById("hourly-table-body");
  if (!tableEl || !report.hourly_table) return;

  tableEl.innerHTML = report.hourly_table.map(row => {
    const color = aqiColor(row.aqi);
    return `<tr>
      <td>${row.time}</td>
      <td><span class="hourly-aqi" style="background:${hexRgba(color, 0.2)};color:${color}">${row.aqi}</span></td>
      <td style="color:var(--text-muted)">${row.band}</td>
      <td style="color:${color}">${row.category}</td>
    </tr>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — History chart with PM2.5 overlay line
// ─────────────────────────────────────────────────────────────────────────────
function renderHistoryChart(report) {
  const canvas = document.getElementById("history-chart");
  if (!canvas) return;

  if (historyChart) { historyChart.destroy(); }
  const ctx = canvas.getContext("2d");

  historyChart = new Chart(ctx, {
    data: {
      labels: report.history_labels,
      datasets: [
        // ── AQI bars ──
        {
          type: "bar",
          label: "Daily AQI",
          data: report.history_data,
          backgroundColor: report.history_data.map(v => hexRgba(aqiColor(v), 0.7)),
          borderColor:     report.history_data.map(v => aqiColor(v)),
          borderWidth: 1,
          borderRadius: 4,
          yAxisID: "yAQI",
        },
        // ── PM2.5 line overlay ──
        {
          type: "line",
          label: "PM2.5 (µg/m³)",
          data: report.history_pm25,
          borderColor: "#bc8cff",
          backgroundColor: "transparent",
          borderWidth: 2,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: "#bc8cff",
          yAxisID: "yPM25",
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.dataset.label === "Daily AQI")    return `AQI: ${ctx.parsed.y}`;
              if (ctx.dataset.label === "PM2.5 (µg/m³)") return `PM2.5: ${ctx.parsed.y} µg/m³`;
              return ctx.dataset.label + ": " + ctx.parsed.y;
            }
          }
        }
      },
      scales: {
        x:     { ticks: { color: "#8b949e", font: { size: 11 } }, grid: { color: "#21262d" } },
        yAQI:  {
          position: "left",
          ticks: { color: "#8b949e", font: { size: 11 } },
          grid:  { color: "#21262d" },
          beginAtZero: true,
          title: { display: true, text: "AQI", color: "#8b949e", font: { size: 11 } },
        },
        yPM25: {
          position: "right",
          ticks: { color: "#bc8cff", font: { size: 11 } },
          grid:  { drawOnChartArea: false },
          beginAtZero: true,
          title: { display: true, text: "PM2.5 µg/m³", color: "#bc8cff", font: { size: 11 } },
        },
      }
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — Community actions with mark-done + progress bar
// ─────────────────────────────────────────────────────────────────────────────
function renderCommunity(report) {
  const container = document.getElementById("community-container");
  if (!container) return;

  communityDone  = 0;
  communityTotal = 0;

  let html = "";

  if (report.community_message) {
    html += `<div class="daily-plan-text" style="margin-bottom:1rem;">${report.community_message}</div>`;
  }

  // Progress bar placeholder
  html += `
    <div id="community-progress-wrap" style="margin-bottom:1rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem;">
        <span class="card-title" style="margin:0">Your Progress Today</span>
        <span id="community-progress-label" class="progress-label">0 / 0 done</span>
      </div>
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="community-progress-bar" style="width:0%"></div></div>
    </div>`;

  report.community_actions.forEach((group, gi) => {
    html += `<div class="community-category">
      <div class="community-category-title">${group.category}</div>`;

    group.actions.forEach((a, ai) => {
      const id = `ca-${gi}-${ai}`;
      communityTotal++;
      html += `
        <div class="community-action-item" id="${id}">
          <div class="community-action-left">
            <span>${a.action}</span>
            <span class="community-action-impact">💡 ${a.impact}</span>
          </div>
          <button class="mark-done-btn" data-id="${id}" onclick="markDone(this, '${id}')">✓ Done</button>
        </div>`;
    });

    html += `</div>`;
  });

  container.innerHTML = html;
  updateCommunityProgress();
}

function markDone(btn, id) {
  const item = document.getElementById(id);
  if (!item) return;

  if (item.classList.contains("done")) {
    // Un-mark
    item.classList.remove("done");
    btn.classList.remove("done");
    btn.textContent = "✓ Done";
    communityDone = Math.max(0, communityDone - 1);
  } else {
    // Mark done
    item.classList.add("done");
    btn.classList.add("done");
    btn.textContent = "✓ Done!";
    communityDone++;
  }
  updateCommunityProgress();
}

function updateCommunityProgress() {
  const bar   = document.getElementById("community-progress-bar");
  const label = document.getElementById("community-progress-label");
  if (!bar || !label) return;
  const pct = communityTotal > 0 ? Math.round((communityDone / communityTotal) * 100) : 0;
  bar.style.width   = `${pct}%`;
  label.textContent = `${communityDone} / ${communityTotal} done`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline meta
// ─────────────────────────────────────────────────────────────────────────────
function renderMeta(report) {
  const el = document.getElementById("pipeline-meta");
  if (el) {
    const lf = report.langflow_active ? "🟢 Langflow active" : "⚪ Langflow not configured";
    el.textContent = `Pipeline ran in ${report.pipeline_time_s}s · ${lf}`;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Master render
// ─────────────────────────────────────────────────────────────────────────────
function renderReport(report) {
  currentReport = report;

  renderEarlyWarningBanner(report);   // Phase 2: top of page
  renderAqiHero(report);
  renderPollutants(report);
  renderRecommendations(report);
  renderDailyPlan(report);
  renderWarnings(report);
  renderVulnerableGroups(report);
  renderForecastChart(report);        // Phase 2: confidence band + best window
  renderHistoryChart(report);         // Phase 2: PM2.5 overlay
  renderCommunity(report);            // Phase 2: mark done
  renderMeta(report);

  document.getElementById("dashboard-content").classList.remove("hidden");
  document.getElementById("empty-state").classList.add("hidden");
  setStatus(report.data_source);
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — RAG Health Advisory Panel
// ─────────────────────────────────────────────────────────────────────────────
async function askRag() {
  const input  = document.getElementById("rag-input");
  const ansEl  = document.getElementById("rag-answer");
  const srcEl  = document.getElementById("rag-sources-list");
  const srcBox = document.getElementById("rag-sources-wrap");
  const btn    = document.getElementById("rag-ask-btn");

  const question = input.value.trim();
  if (!question) return;

  btn.disabled = true;
  btn.textContent = "Thinking…";
  ansEl.textContent = "Retrieving health guidelines…";
  ansEl.classList.add("visible");
  if (srcBox) srcBox.style.display = "none";

  try {
    const body = { question };
    if (currentReport) {
      body.city = currentReport.city;
      body.aqi  = currentReport.aqi;
    }

    const resp = await fetch("/api/rag", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await resp.json();

    ansEl.textContent = data.answer || "No answer returned.";

    // Show retrieved guideline sources
    if (data.sources && data.sources.length > 0 && srcEl && srcBox) {
      srcEl.textContent = data.sources.join("\n\n──\n\n");
      srcBox.style.display = "block";
    }
  } catch (err) {
    ansEl.textContent = "Network error. Please try again.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Ask";
  }
}

// Populate the RAG input from a suggestion chip
function ragChip(question) {
  const input = document.getElementById("rag-input");
  if (input) { input.value = question; input.focus(); }
}

// ─────────────────────────────────────────────────────────────────────────────
// Fetch full report
// ─────────────────────────────────────────────────────────────────────────────
async function fetchReport(city) {
  currentCity = city.trim();
  if (!currentCity) return;

  setStatus("loading");
  document.getElementById("search-btn").disabled = true;
  document.getElementById("error-banner").classList.add("hidden");
  showSkeleton();

  try {
    const resp = await fetch(`/api/full-report?city=${encodeURIComponent(currentCity)}`);
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.error || "API error");
    }
    const report = await resp.json();
    renderReport(report);
  } catch (err) {
    setStatus("error");
    document.getElementById("error-message").textContent = `Error: ${err.message}`;
    document.getElementById("error-banner").classList.remove("hidden");
  } finally {
    document.getElementById("search-btn").disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// AI Chat Assistant
// ─────────────────────────────────────────────────────────────────────────────
const chatPanel    = document.getElementById("chat-panel");
const chatToggle   = document.getElementById("chat-toggle");
const chatClose    = document.getElementById("chat-close");
const chatMessages = document.getElementById("chat-messages");
const chatInput    = document.getElementById("chat-input");
const chatSend     = document.getElementById("chat-send");

function toggleChat() {
  chatPanel.classList.toggle("open");
  if (chatPanel.classList.contains("open")) chatInput.focus();
}

if (chatToggle) chatToggle.addEventListener("click", toggleChat);
if (chatClose)  chatClose.addEventListener("click",  toggleChat);

function appendMessage(text, role) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

async function sendChat() {
  const msg = chatInput.value.trim();
  if (!msg) return;
  chatInput.value = "";
  appendMessage(msg, "user");

  const typing = appendMessage("Thinking…", "bot typing");

  try {
    const body = { message: msg };
    if (currentReport) { body.city = currentReport.city; body.aqi = currentReport.aqi; }

    const resp = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await resp.json();
    typing.remove();
    appendMessage(data.reply || "Sorry, I couldn't process that.", "bot");
  } catch {
    typing.remove();
    appendMessage("Network error. Please try again.", "bot");
  }
}

if (chatSend)  chatSend.addEventListener("click", sendChat);
if (chatInput) chatInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// ─────────────────────────────────────────────────────────────────────────────
// Search form + city chips
// ─────────────────────────────────────────────────────────────────────────────
const searchForm  = document.getElementById("search-form");
const searchInput = document.getElementById("city-input");

if (searchForm) {
  searchForm.addEventListener("submit", e => {
    e.preventDefault();
    fetchReport(searchInput.value);
  });
}

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    searchInput.value = chip.dataset.city;
    fetchReport(chip.dataset.city);
  });
});

// Wire up the RAG ask button
const ragBtn = document.getElementById("rag-ask-btn");
if (ragBtn) ragBtn.addEventListener("click", askRag);
const ragInputEl = document.getElementById("rag-input");
if (ragInputEl) ragInputEl.addEventListener("keydown", e => {
  if (e.key === "Enter") askRag();
});

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  fetchReport(currentCity);
});


// ═════════════════════════════════════════════════════════════════════════════
// PHASE 3 — Multi-Agent System, Final Plan, User Profile, Enhanced Chat
// ═════════════════════════════════════════════════════════════════════════════

// ── Chat conversation history (Phase 3) ──────────────────────────────────────
// Keeps the last 6 message turns so the AI has context for follow-up questions.
const chatHistory = [];   // [{role:"user"|"assistant", content:"..."}]

// ── Phase 3 state ─────────────────────────────────────────────────────────────
let userProfile = {};           // {age_group, conditions:[]}
let agentStatusData = null;     // cached /api/agent-status response

// ─────────────────────────────────────────────────────────────────────────────
// Services status bar (/api/agent-status)
// ─────────────────────────────────────────────────────────────────────────────
async function loadAgentStatus() {
  try {
    const resp = await fetch("/api/agent-status");
    const data = await resp.json();
    agentStatusData = data;

    const svcMap = {
      aqicn:    { dot: "svc-aqicn-dot",    label: "svc-aqicn-label" },
      watsonx:  { dot: "svc-watsonx-dot",  label: "svc-watsonx-label" },
      langflow: { dot: "svc-langflow-dot", label: "svc-langflow-label" },
      rag:      { dot: "svc-rag-dot",      label: "svc-rag-label" },
    };

    for (const [key, ids] of Object.entries(svcMap)) {
      const svc = data.services[key];
      if (!svc) continue;
      const dot   = document.getElementById(ids.dot);
      const label = document.getElementById(ids.label);
      if (dot) {
        dot.className = "dot " + (svc.configured ? "on" : "off");
      }
      if (label) label.textContent = svc.label;
    }
  } catch {
    // Silently ignore — status bar is non-critical
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline diagram — animate each step based on the agent_trace
// ─────────────────────────────────────────────────────────────────────────────
function renderPipelineDiagram(trace) {
  if (!trace || trace.length === 0) return;

  trace.forEach((step, i) => {
    const psEl  = document.getElementById(`ps-${i}`);
    const pbEl  = document.getElementById(`pb-${i}`);
    const pdEl  = document.getElementById(`pd-${i}`);
    if (!psEl) return;

    // Set the step class (used by CSS for colour/animation)
    psEl.className = `pipeline-step ${step.status === "ok" ? "done" : step.status}`;

    // Badge inside the node circle
    if (pbEl) {
      if (step.status === "ok") {
        pbEl.className = "pipeline-node-badge ok";
        pbEl.textContent = "✓";
      } else if (step.status === "error") {
        pbEl.className = "pipeline-node-badge error";
        pbEl.textContent = "✕";
      } else {
        pbEl.className = "pipeline-node-badge run";
        pbEl.textContent = "…";
      }
    }

    // Duration below the label
    if (pdEl && step.duration_ms > 0) {
      pdEl.textContent = `${step.duration_ms}ms`;
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent trace cards — detailed step-by-step log
// ─────────────────────────────────────────────────────────────────────────────
function renderAgentTrace(trace) {
  const container = document.getElementById("trace-list");
  if (!container || !trace) return;

  container.innerHTML = trace.map(step => {
    const statusLabel = step.status === "ok" ? "✓ Done" : step.status === "error" ? "✕ Error" : "⏳ Running";
    const durationStr = step.duration_ms > 0 ? `${step.duration_ms}ms` : "";

    return `
      <div class="trace-card ${step.status}">
        <span class="trace-emoji">${step.emoji}</span>
        <div class="trace-body">
          <div class="trace-header">
            <span class="trace-name">${step.agent}</span>
            <span class="trace-meta">
              <span class="trace-status-dot ${step.status}"></span>
              ${statusLabel}
              ${durationStr ? `<span>·</span><span>${durationStr}</span>` : ""}
            </span>
          </div>
          <div class="trace-description">${step.description}</div>
          ${step.output_snippet ? `<div class="trace-snippet">${escHtml(step.output_snippet)}</div>` : ""}
        </div>
      </div>`;
  }).join("");
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─────────────────────────────────────────────────────────────────────────────
// Final Daily Action Plan card
// ─────────────────────────────────────────────────────────────────────────────
function renderFinalPlan(report) {
  const fp = report.final_plan;
  if (!fp) return;

  // Headline
  const hlEl = document.getElementById("final-plan-headline");
  if (hlEl) {
    hlEl.textContent = fp.headline || report.daily_plan;
    hlEl.classList.remove("skeleton-area");
  }

  // 4-section grid
  const gridEl = document.getElementById("final-plan-grid");
  if (gridEl) {
    const sections = [
      { icon: "🌅", label: "Morning",  text: fp.morning_action },
      { icon: "🌿", label: "Best Outdoor Time", text: fp.best_outdoor },
      { icon: "🏥", label: "Health Tip", text: fp.ai_tip },
      { icon: "🌙", label: "Evening", text: fp.evening_action },
    ];

    gridEl.innerHTML = sections.map(s => `
      <div class="plan-section">
        <span class="plan-section-icon">${s.icon}</span>
        <div class="plan-section-body">
          <div class="plan-section-label">${s.label}</div>
          <div class="plan-section-text">${s.text || "—"}</div>
        </div>
      </div>`).join("");
  }

  // Source badge
  const srcEl = document.getElementById("final-plan-source");
  if (srcEl && fp.source) {
    const srcLabels = {
      watsonx:  "✨ Generated by IBM watsonx.ai",
      langflow: "🔗 Generated by IBM Langflow",
      template: "📋 Generated by rule-based engine",
      error:    "⚠️ Fallback template used",
    };
    srcEl.textContent = srcLabels[fp.source] || fp.source;
    srcEl.classList.remove("hidden");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// User profile form
// ─────────────────────────────────────────────────────────────────────────────
function readProfile() {
  const age = document.getElementById("profile-age")?.value || "";
  const conditions = (document.getElementById("profile-conditions")?.value || "")
    .split(",")
    .map(s => s.trim())
    .filter(Boolean);

  return { age_group: age, conditions };
}

async function applyProfile() {
  const profile = readProfile();
  userProfile   = profile;

  const statusEl = document.getElementById("profile-status");
  const btn      = document.getElementById("profile-apply-btn");

  const parts = [];
  if (profile.age_group) parts.push(profile.age_group);
  if (profile.conditions.length) parts.push(profile.conditions.join(", "));

  if (statusEl) {
    statusEl.textContent = parts.length
      ? `Profile saved: ${parts.join(" · ")}. Re-fetching personalised report…`
      : "No profile set — using generic recommendations.";
  }

  if (btn) btn.disabled = true;

  // Re-fetch the full report with this profile using POST
  setStatus("loading");
  document.getElementById("error-banner").classList.add("hidden");
  showSkeleton();

  try {
    const resp = await fetch("/api/full-report", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ city: currentCity, user_profile: profile }),
    });
    if (!resp.ok) throw new Error((await resp.json()).error || "API error");
    const report = await resp.json();
    renderReport(report);

    if (statusEl) {
      statusEl.textContent = parts.length
        ? `Personalised for: ${parts.join(" · ")}`
        : "Using generic recommendations.";
    }
  } catch (err) {
    setStatus("error");
    document.getElementById("error-message").textContent = `Profile fetch error: ${err.message}`;
    document.getElementById("error-banner").classList.remove("hidden");
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 3 additions to renderReport() — injected into the master render
// ─────────────────────────────────────────────────────────────────────────────

// Override renderReport to also call Phase 3 renderers
const _renderReportPhase2 = renderReport;

function renderReport(report) {
  currentReport = report;

  // Phase 1 + 2 renderers
  renderEarlyWarningBanner(report);
  renderAqiHero(report);
  renderPollutants(report);
  renderRecommendations(report);
  renderDailyPlan(report);
  renderWarnings(report);
  renderVulnerableGroups(report);
  renderForecastChart(report);
  renderHistoryChart(report);
  renderCommunity(report);
  renderMeta(report);

  // Phase 3 renderers
  renderPipelineDiagram(report.agent_trace);
  renderAgentTrace(report.agent_trace);
  renderFinalPlan(report);

  document.getElementById("dashboard-content").classList.remove("hidden");
  document.getElementById("empty-state").classList.add("hidden");
  setStatus(report.data_source);
}

// ─────────────────────────────────────────────────────────────────────────────
// Enhanced chat — with conversation history and full-report context
// ─────────────────────────────────────────────────────────────────────────────

// Override sendChat to include conversation history
async function sendChat() {
  const msg = chatInput.value.trim();
  if (!msg) return;

  chatInput.value = "";
  appendMessage(msg, "user");
  chatHistory.push({ role: "user", content: msg });

  const typing = appendMessage("Thinking…", "bot typing");

  try {
    // Build context from current report
    const body = {
      message: msg,
      history: chatHistory.slice(-6),    // last 6 turns for context
    };
    if (currentReport) {
      body.city    = currentReport.city;
      body.aqi     = currentReport.aqi;
      body.context = {
        category:        currentReport.category_level,
        daily_plan:      currentReport.daily_plan,
        recommendations: (currentReport.recommendations || []).slice(0, 3),
        forecast_summary: currentReport.forecast_summary,
        warnings_count:  (currentReport.warnings || []).length,
      };
    }
    if (userProfile && (userProfile.age_group || (userProfile.conditions || []).length)) {
      body.user_profile = userProfile;
    }

    const resp = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await resp.json();
    const reply = data.reply || "Sorry, I couldn't process that.";

    typing.remove();
    appendMessage(reply, "bot");
    chatHistory.push({ role: "assistant", content: reply });

    // Keep history to last 12 entries (6 turns)
    if (chatHistory.length > 12) chatHistory.splice(0, chatHistory.length - 12);

  } catch {
    typing.remove();
    appendMessage("Network error. Please try again.", "bot");
  }
}

// ── Phase 3 init ───────────────────────────────────────────────────────────────
// Load agent status on startup (services pills in the pipeline card)
document.addEventListener("DOMContentLoaded", () => {
  loadAgentStatus();
});
