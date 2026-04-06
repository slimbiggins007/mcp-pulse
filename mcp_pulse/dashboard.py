"""FastAPI dashboard for mcp-pulse."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from mcp_pulse.storage import Storage

_storage: Storage | None = None


def create_app(db_path: str | None = None) -> FastAPI:
    global _storage
    _storage = Storage(db_path)

    app = FastAPI(title="mcp-pulse")

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/servers")
    async def servers() -> list[str]:
        return _storage.get_servers()

    @app.get("/api/summary/{server_name}")
    async def summary(server_name: str) -> dict:
        s = _storage.get_server_summary(server_name)
        return asdict(s)

    @app.get("/api/stats")
    async def stats(server: str | None = None) -> list[dict]:
        return [asdict(s) for s in _storage.get_tool_stats(server)]

    @app.get("/api/calls")
    async def calls(server: str | None = None, limit: int = 50) -> list[dict]:
        return [asdict(e) for e in _storage.get_recent_calls(limit, server)]

    @app.get("/api/hourly")
    async def hourly(server: str | None = None, hours: int = 24) -> list[dict]:
        return _storage.get_calls_per_hour(server, hours)

    return app


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mcp-pulse</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e1e4ed; --muted: #8b8fa3; --accent: #6c5ce7;
    --green: #00b894; --red: #e17055; --blue: #74b9ff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
  .subtitle { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
  .card-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .card-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .card-value.green { color: var(--green); }
  .card-value.red { color: var(--red); }
  .section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  .section-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--muted); font-weight: 500; padding: 8px 12px;
       border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .badge-ok { background: rgba(0,184,148,0.15); color: var(--green); }
  .badge-err { background: rgba(225,112,85,0.15); color: var(--red); }
  .server-tabs { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
  .server-tab { padding: 6px 16px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border);
                color: var(--muted); cursor: pointer; font-size: 13px; transition: all 0.15s; }
  .server-tab:hover { border-color: var(--accent); color: var(--text); }
  .server-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .chart-container { height: 200px; }
  .empty { text-align: center; color: var(--muted); padding: 48px; font-size: 14px; }
  .mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
  .refresh-btn { float: right; background: var(--surface); border: 1px solid var(--border); color: var(--muted);
                 padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
  .refresh-btn:hover { border-color: var(--accent); color: var(--text); }
</style>
</head>
<body>

<div style="display:flex;justify-content:space-between;align-items:start;">
  <div>
    <h1>mcp-pulse</h1>
    <div class="subtitle">MCP Server Analytics</div>
  </div>
  <button class="refresh-btn" onclick="loadAll()">Refresh</button>
</div>

<div class="server-tabs" id="serverTabs"></div>

<div class="grid" id="summaryCards">
  <div class="empty">Loading...</div>
</div>

<div class="section">
  <div class="section-title">Calls per Hour</div>
  <div class="chart-container"><canvas id="hourlyChart"></canvas></div>
</div>

<div class="section">
  <div class="section-title">Tool Breakdown</div>
  <table id="toolTable">
    <thead>
      <tr><th>Tool</th><th>Calls</th><th>Avg (ms)</th><th>p50 (ms)</th><th>p95 (ms)</th><th>Errors</th><th>Error Rate</th></tr>
    </thead>
    <tbody id="toolBody"></tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">Recent Calls</div>
  <table id="callTable">
    <thead>
      <tr><th>Time</th><th>Tool</th><th>Duration (ms)</th><th>Status</th><th>Size</th></tr>
    </thead>
    <tbody id="callBody"></tbody>
  </table>
</div>

<script>
let currentServer = null;
let hourlyChart = null;

async function api(path) {
  const res = await fetch(path);
  return res.json();
}

function qs(s) { return currentServer ? `${s}${s.includes('?')?'&':'?'}server=${encodeURIComponent(currentServer)}` : s; }

async function loadServers() {
  const servers = await api('/api/servers');
  const tabs = document.getElementById('serverTabs');
  if (!servers.length) {
    tabs.innerHTML = '';
    document.getElementById('summaryCards').innerHTML = '<div class="empty">No data yet. Instrument an MCP server and make some tool calls.</div>';
    return;
  }
  tabs.innerHTML = '<div class="server-tab ' + (!currentServer ? 'active' : '') + '" onclick="selectServer(null)">All</div>'
    + servers.map(s => '<div class="server-tab ' + (currentServer===s?'active':'') + '" onclick="selectServer(\\''+s+'\\')">'+s+'</div>').join('');
  if (!currentServer && servers.length === 1) { currentServer = servers[0]; loadServers(); }
}

function selectServer(s) { currentServer = s; loadAll(); }

async function loadSummary() {
  if (!currentServer) {
    const stats = await api('/api/stats');
    const total = stats.reduce((a,s) => a+s.total_calls, 0);
    const errors = stats.reduce((a,s) => a+s.error_count, 0);
    const avgMs = stats.length ? stats.reduce((a,s) => a+s.avg_duration_ms, 0) / stats.length : 0;
    renderSummary(total, errors, avgMs, stats.length);
  } else {
    const s = await api('/api/summary/' + encodeURIComponent(currentServer));
    renderSummary(s.total_calls, s.total_errors, s.avg_duration_ms, s.tools.length);
  }
}

function renderSummary(total, errors, avgMs, toolCount) {
  const errRate = total ? ((errors/total)*100).toFixed(1) : '0.0';
  document.getElementById('summaryCards').innerHTML = `
    <div class="card"><div class="card-label">Total Calls</div><div class="card-value">${total.toLocaleString()}</div></div>
    <div class="card"><div class="card-label">Error Rate</div><div class="card-value ${parseFloat(errRate)>5?'red':'green'}">${errRate}%</div></div>
    <div class="card"><div class="card-label">Avg Latency</div><div class="card-value">${avgMs.toFixed(0)}<span style="font-size:14px;color:var(--muted)">ms</span></div></div>
    <div class="card"><div class="card-label">Tools</div><div class="card-value">${toolCount}</div></div>`;
}

async function loadHourly() {
  const data = await api(qs('/api/hourly'));
  const ctx = document.getElementById('hourlyChart').getContext('2d');
  if (hourlyChart) hourlyChart.destroy();
  hourlyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.hour.split('T')[1] || d.hour),
      datasets: [
        { label: 'Calls', data: data.map(d => d.calls), backgroundColor: 'rgba(108,92,231,0.6)', borderRadius: 4 },
        { label: 'Errors', data: data.map(d => d.errors), backgroundColor: 'rgba(225,112,85,0.6)', borderRadius: 4 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8b8fa3', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#8b8fa3', font: { size: 10 } }, grid: { color: '#2a2d3a' } },
        y: { ticks: { color: '#8b8fa3' }, grid: { color: '#2a2d3a' } },
      }
    }
  });
}

async function loadTools() {
  const stats = await api(qs('/api/stats'));
  const body = document.getElementById('toolBody');
  if (!stats.length) { body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted)">No data</td></tr>'; return; }
  body.innerHTML = stats.map(s => `<tr>
    <td class="mono">${s.tool_name}</td>
    <td>${s.total_calls}</td>
    <td>${s.avg_duration_ms.toFixed(1)}</td>
    <td>${s.p50_duration_ms.toFixed(1)}</td>
    <td>${s.p95_duration_ms.toFixed(1)}</td>
    <td>${s.error_count}</td>
    <td><span class="badge ${s.error_rate>0.05?'badge-err':'badge-ok'}">${(s.error_rate*100).toFixed(1)}%</span></td>
  </tr>`).join('');
}

async function loadCalls() {
  const calls = await api(qs('/api/calls?limit=30'));
  const body = document.getElementById('callBody');
  if (!calls.length) { body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--muted)">No calls yet</td></tr>'; return; }
  body.innerHTML = calls.map(c => {
    const t = new Date(c.timestamp);
    const time = t.toLocaleDateString(undefined,{month:'short',day:'numeric'}) + ' ' + t.toLocaleTimeString();
    return `<tr>
      <td class="mono">${time}</td>
      <td class="mono">${c.tool_name}</td>
      <td>${c.duration_ms.toFixed(1)}</td>
      <td><span class="badge ${c.success?'badge-ok':'badge-err'}">${c.success?'OK':'ERR'}</span></td>
      <td class="mono">${c.response_size > 1024 ? (c.response_size/1024).toFixed(1)+'K' : c.response_size+'B'}</td>
    </tr>`;
  }).join('');
}

async function loadAll() {
  await loadServers();
  await Promise.all([loadSummary(), loadHourly(), loadTools(), loadCalls()]);
}

loadAll();
setInterval(loadAll, 30000);
</script>
</body>
</html>
"""
