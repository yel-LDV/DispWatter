/* History view — telemetry chart and table */

import { state, selectedDevice } from './state.js';
import { socket, on } from './ws.js';
import { el, toast } from './ui.js';

export function initHistory() {
    const view = document.getElementById('view-history');
    if (!view) return;

    el('btnRefreshHistory')?.addEventListener('click', loadHistory);
    el('historyPeriod')?.addEventListener('change', loadHistory);
}

function getPeriodRange(period) {
    const end = new Date();
    const start = new Date();
    switch (period) {
        case '24h': start.setHours(start.getHours() - 24); break;
        case '7d': start.setDate(start.getDate() - 7); break;
        case '30d': start.setDate(start.getDate() - 30); break;
    }
    return { start: start.toISOString(), end: end.toISOString() };
}

async function loadHistory() {
    const dev = selectedDevice();
    if (!dev) {
        toast('Selecciona un dispositivo primero', 'warning');
        return;
    }

    const period = el('historyPeriod')?.value || '7d';
    const { start, end } = getPeriodRange(period);

    await socket.connect();

    const result = await new Promise((resolve) => {
        const off = on('history_result', (data) => {
            off();
            resolve(data);
        });
        socket.send({
            event: 'get_history',
            device_id: dev.id,
            start,
            end,
            limit: 500,
        });
        setTimeout(() => { off(); resolve({ entries: [], stats: {} }); }, 10000);
    });

    const entries = result.entries || [];
    const stats = result.stats || {};

    renderHistoryStats(stats);
    renderHistoryChart(entries);
    renderHistoryTable(entries);
}

function renderHistoryStats(stats) {
    const container = el('historyStats');
    if (!container) return;

    const avgLevel = stats.avg_level != null ? stats.avg_level.toFixed(1) + '%' : '—';
    const minLevel = stats.min_level != null ? stats.min_level.toFixed(1) + '%' : '—';
    const maxLevel = stats.max_level != null ? stats.max_level.toFixed(1) + '%' : '—';
    const totalLiters = stats.total_liters != null ? stats.total_liters.toFixed(1) + ' L' : '—';

    container.innerHTML = `
        <div class="field"><label>Promedio</label><div class="stat-value">${avgLevel}</div></div>
        <div class="field"><label>Mínimo</label><div class="stat-value">${minLevel}</div></div>
        <div class="field"><label>Máximo</label><div class="stat-value">${maxLevel}</div></div>
        <div class="field"><label>Total litros</label><div class="stat-value">${totalLiters}</div></div>
    `;
}

function renderHistoryChart(entries) {
    const canvas = el('historyChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.parentElement.clientWidth - 32;
    const height = 200;
    canvas.width = width;
    canvas.height = height;

    ctx.clearRect(0, 0, width, height);

    if (!entries.length) {
        ctx.fillStyle = '#888';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Sin datos', width / 2, height / 2);
        return;
    }

    const padding = { top: 20, right: 20, bottom: 30, left: 40 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const levels = entries.map(e => e.percent || 0);
    const minL = Math.min(...levels, 0);
    const maxL = Math.max(...levels, 100);
    const range = maxL - minL || 1;

    // Grid
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        const val = Math.round(maxL - (range / 4) * i);
        ctx.fillStyle = '#888';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(val + '%', padding.left - 5, y + 4);
    }

    // Line
    const step = chartW / Math.max(entries.length - 1, 1);
    ctx.strokeStyle = '#4fc3f7';
    ctx.lineWidth = 2;
    ctx.beginPath();
    entries.forEach((entry, i) => {
        const x = padding.left + i * step;
        const y = padding.top + chartH - ((entry.percent || 0 - minL) / range) * chartH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // X-axis labels
    ctx.fillStyle = '#888';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    const labelCount = Math.min(5, entries.length);
    for (let i = 0; i < labelCount; i++) {
        const idx = Math.floor((i / (labelCount - 1)) * (entries.length - 1));
        const entry = entries[idx];
        if (entry && entry.timestamp) {
            const x = padding.left + idx * step;
            const d = new Date(entry.timestamp);
            const label = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            ctx.save();
            ctx.translate(x, height - 5);
            ctx.rotate(-Math.PI / 4);
            ctx.textAlign = 'right';
            ctx.fillText(label, 0, 0);
            ctx.restore();
        }
    }
}

function renderHistoryTable(entries) {
    const tableWrap = document.querySelector('#view-history .table-wrap table');
    if (!tableWrap) return;

    if (!entries.length) {
        tableWrap.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--muted);">Sin datos</td></tr>';
        return;
    }

    let html = '<thead><tr><th>Fecha</th><th>Nivel</th><th>Litros</th><th>Distancia</th><th>Bomba</th></tr></thead><tbody>';
    const reversed = [...entries].reverse().slice(0, 50);
    reversed.forEach(entry => {
        const d = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '—';
        const pct = entry.percent != null ? entry.percent.toFixed(1) + '%' : '—';
        const liters = entry.liters != null ? entry.liters.toFixed(1) : '—';
        const dist = entry.distance_mm != null ? (entry.distance_mm / 10).toFixed(0) + ' cm' : '—';
        const pump = entry.pump_on ? 'ON' : 'OFF';
        html += `<tr><td>${d}</td><td>${pct}</td><td>${liters}</td><td>${dist}</td><td>${pump}</td></tr>`;
    });
    html += '</tbody>';
    tableWrap.innerHTML = html;
}
