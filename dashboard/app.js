/**
 * ETF Backtesting Dashboard - Application Logic
 * Loads results.json and renders interactive charts and tables.
 */

// ================================================================
// Color palette
// ================================================================
const COLORS = {
    etfs: [
        { main: '#6366f1', bg: 'rgba(99, 102, 241, 0.12)', border: 'rgba(99, 102, 241, 0.8)' },
        { main: '#06b6d4', bg: 'rgba(6, 182, 212, 0.12)', border: 'rgba(6, 182, 212, 0.8)' },
        { main: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.8)' },
    ],
    benchmarks: [
        { main: '#64748b', bg: 'rgba(100, 116, 139, 0.08)', border: 'rgba(100, 116, 139, 0.5)' },
        { main: '#94a3b8', bg: 'rgba(148, 163, 184, 0.08)', border: 'rgba(148, 163, 184, 0.5)' },
        { main: '#78716c', bg: 'rgba(120, 113, 108, 0.08)', border: 'rgba(120, 113, 108, 0.5)' },
        { main: '#a1a1aa', bg: 'rgba(161, 161, 170, 0.08)', border: 'rgba(161, 161, 170, 0.5)' },
    ],
    green: '#10b981',
    red: '#ef4444',
    gridColor: 'rgba(255, 255, 255, 0.04)',
    tickColor: '#555570',
};

// ================================================================
// Global state
// ================================================================
let DATA = null;
let performanceChart = null;
let drawdownChart = null;
let sortState = { column: null, direction: 'desc' };
let currentMinTime = null;
let currentMaxTime = null;

// ================================================================
// Initialization
// ================================================================
document.addEventListener('DOMContentLoaded', async () => {
    try {
        showLoading();
        const response = await fetch('results.json');
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        DATA = await response.json();
        
        // Initialize currentMetrics using the JS pipeline to populate peak/trough dates
        [...DATA.etfs, ...DATA.benchmarks].forEach(item => item.currentMetrics = recalculateMetricsJS(item, null, null));
        
        hideLoading();
        renderDashboard();
    } catch (err) {
        showError(err.message);
    }
});

function showLoading() {
    document.getElementById('dashboard-content').innerHTML = `
        <div class="loading">
            <div class="loading__spinner"></div>
            <div class="loading__text">Loading backtest results...</div>
        </div>`;
}

function hideLoading() {
    document.getElementById('dashboard-content').innerHTML = '';
}

function showError(message) {
    document.getElementById('dashboard-content').innerHTML = `
        <div class="error">
            <div class="error__title">Failed to load results</div>
            <div class="error__message">${message}</div>
            <div style="margin-top:16px;color:var(--text-muted);font-size:0.85rem;">
                Make sure to run <code style="color:var(--etf-1)">python run_backtest.py</code> first to generate results.json
            </div>
        </div>`;
}

// ================================================================
// Main render
// ================================================================
function renderDashboard() {
    const container = document.getElementById('dashboard-content');

    // Update header meta
    document.getElementById('meta-period').textContent =
        `${formatDate(DATA.meta.start_date)} — ${formatDate(DATA.meta.end_date)}`;
    document.getElementById('meta-generated').textContent =
        new Date(DATA.meta.generated_at).toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });

    // Build the best-performing ETF summary
    const bestETF = DATA.etfs.reduce((best, etf) =>
        etf.metrics.total_return_pct > best.metrics.total_return_pct ? etf : best);

    container.innerHTML = `
        <!-- Quick Metrics -->
        <div class="metrics-header" style="display:flex; justify-content: space-between; align-items: center; margin-bottom: 12px; margin-top: 4px;">
            <h2 style="font-size: 1.1rem; color: var(--text-primary); margin: 0; display:flex; align-items:center; gap: 8px;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                Performance Summary
            </h2>
            <select id="metrics-filter-select" style="background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 6px 12px; font-family: 'Inter', sans-serif; font-size: 0.9rem; cursor:pointer; outline:none;">
                <option value="all">Compare All Portfolios</option>
                <optgroup label="ETFs">
                    \${DATA.etfs.map((e, i) => \`<option value="etf_\${i}">\${e.name}</option>\`).join('')}
                </optgroup>
                <optgroup label="Benchmarks">
                    \${DATA.benchmarks.map((b, i) => \`<option value="bench_\${i}">\${b.name}</option>\`).join('')}
                </optgroup>
            </select>
        </div>
        <div class="metrics-grid" id="metrics-grid"></div>

        <!-- Time Controls -->
        <div class="time-controls-card">
            <div class="time-controls__label">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                Time Period
            </div>
            <div class="time-controls__presets">
                <button class="preset-btn active" data-start="min" data-end="max">Max</button>
                <button class="preset-btn" data-start="2007-07-01" data-end="2009-12-31">2008 Crisis</button>
                <button class="preset-btn" data-start="2010-01-01" data-end="2012-12-31">Euro Debt</button>
                <button class="preset-btn" data-start="2013-01-01" data-end="2018-12-31">FAANG Rise</button>
                <button class="preset-btn" data-start="2016-01-01" data-end="2019-12-31">Brexit</button>
                <button class="preset-btn" data-start="2020-01-01" data-end="2021-12-31">COVID-19</button>
                <button class="preset-btn" data-start="2022-11-01" data-end="max">AI Bubble</button>
            </div>
            <div class="time-controls__custom">
                <input type="date" id="custom-start-date" class="date-input">
                <span class="date-separator">to</span>
                <input type="date" id="custom-end-date" class="date-input">
                <button id="apply-custom-btn" class="preset-btn" style="margin-left:8px; padding: 6px 12px; background:var(--etf-2); color:#fff; border:none; box-shadow: 0 0 8px rgba(6, 182, 212, 0.4);">Apply</button>
                <label class="normalize-label" style="display:flex; align-items:center; gap:6px; margin-left:12px; font-size:0.8rem; color:var(--text-secondary); cursor:pointer;">
                    <input type="checkbox" id="normalize-toggle" checked> Normalize to start date
                </label>
            </div>
        </div>

        <!-- Performance Chart -->
        <div class="card" id="perf-chart-card">
            <div class="card__header">
                <div class="card__title">
                    <svg class="card__title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg>
                    Growth of $10,000
                </div>
            </div>
            <div class="chart-container">
                <canvas id="performance-chart"></canvas>
            </div>
            <div class="legend-container" id="perf-legend"></div>
        </div>

        <!-- Holdings Inspector -->
        <div class="card" id="holdings-card">
            <div class="card__header">
                <div class="card__title">
                    <svg class="card__title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"></circle>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    </svg>
                    Holdings Inspector
                </div>
            </div>
            <div class="holdings-controls" id="holdings-controls"></div>
            <div class="holdings-grid" id="holdings-grid"></div>
        </div>

        <!-- Performance Table -->
        <div class="card" id="perf-table-card">
            <div class="card__header">
                <div class="card__title">
                    <svg class="card__title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="3" y1="9" x2="21" y2="9"></line>
                        <line x1="9" y1="21" x2="9" y2="9"></line>
                    </svg>
                    Performance Summary
                </div>
            </div>
            <div class="perf-table-wrapper">
                <table class="perf-table" id="perf-table"></table>
            </div>
        </div>

        <!-- Drawdown Chart -->
        <div class="card" id="drawdown-card">
            <div class="card__header">
                <div class="card__title">
                    <svg class="card__title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline>
                        <polyline points="17 6 23 6 23 12"></polyline>
                    </svg>
                    Drawdown
                </div>
            </div>
            <div class="chart-container chart-container--small">
                <canvas id="drawdown-chart"></canvas>
            </div>
        </div>

        <!-- Monthly Returns Heatmap -->
        <div class="card" id="heatmap-card">
            <div class="card__header">
                <div class="card__title">
                    <svg class="card__title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                    </svg>
                    Monthly Returns Heatmap
                </div>
            </div>
            <div class="heatmap-controls" id="heatmap-controls"></div>
            <div class="heatmap-container" id="heatmap-container"></div>
        </div>
    `;

    document.getElementById('metrics-filter-select').addEventListener('change', renderMetrics);
    renderMetrics();
    renderPerformanceChart();
    renderPerformanceTable();
    renderDrawdownChart();
    renderHoldingsInspector();
    renderHeatmap();
    setupTimeControls();
}

// ================================================================
// Focus Timeline Controls
// ================================================================
const focusLinePlugin = {
    id: 'focusLine',
    afterDraw: (chart) => {
        const focusDate = chart.options.focusDate;
        if (!focusDate) return;
        const { ctx, chartArea: { top, bottom, left, right }, scales: { x } } = chart;
        const px = x.getPixelForValue(focusDate);
        if (px >= left && px <= right) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(px, top);
            ctx.lineTo(px, bottom);
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#06b6d4'; // Cyan line matching dashboard themes
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

window.setFocusDate = (timeMs, etfName) => {
    if (performanceChart) {
        performanceChart.options.focusDate = timeMs;
        performanceChart.update();
    }
    if (drawdownChart) {
        drawdownChart.options.focusDate = timeMs;
        drawdownChart.update();
    }
    
    // Update Holdings Inspector
    if (etfName) {
        const select = document.getElementById('holdings-etf-select');
        const slider = document.getElementById('holdings-date-slider');
        if (select && slider) {
            const etfIdx = DATA.etfs.findIndex(e => e.name === etfName);
            if (etfIdx !== -1) {
                select.value = etfIdx;
                let minDiff = Infinity;
                let closestIdx = 0;
                DATA.etfs[etfIdx].holdings_log.forEach((h, idx) => {
                    const diff = Math.abs(new Date(h.date).getTime() - timeMs);
                    if (diff < minDiff) {
                        minDiff = diff;
                        closestIdx = idx;
                    }
                });
                slider.value = closestIdx;
                slider.dispatchEvent(new Event('input'));
            }
        }
    }
};

// ================================================================
// Time Controls & Metric Recalculation
// ================================================================

function recalculateMetricsJS(item, minTime, maxTime) {
    const dates = item.timeseries.dates;
    const values = item.timeseries.values;
    
    let startIndex = 0;
    let endIndex = dates.length - 1;
    
    if (minTime) {
        while(startIndex < dates.length && new Date(dates[startIndex]).getTime() < minTime) startIndex++;
    }
    if (maxTime) {
        while(endIndex >= 0 && new Date(dates[endIndex]).getTime() > maxTime) endIndex--;
    }
    
    if (startIndex >= endIndex || startIndex >= dates.length || endIndex < 0) {
        return {
            total_return_pct: 0,
            annualized_return_pct: 0,
            max_drawdown_pct: 0,
            volatility_pct: 0,
            sharpe_ratio: 0,
            _actualStartDate: dates[0],
            _actualEndDate: dates[0]
        };
    }
    
    const subValues = values.slice(startIndex, endIndex + 1);
    const subDates = dates.slice(startIndex, endIndex + 1);
    
    const startVal = subValues[0];
    const endVal = subValues[subValues.length - 1];
    
    const totalReturn = (endVal / startVal) - 1;
    
    const sDate = new Date(subDates[0]);
    const eDate = new Date(subDates[subDates.length - 1]);
    const nDays = (eDate - sDate) / (1000 * 60 * 60 * 24);
    const nYears = Math.max(nDays / 365.25, 0.01);
    
    const annualizedReturn = Math.pow(1 + totalReturn, 1 / nYears) - 1;
    
    let maxDrawdown = 0;
    let cumMax = subValues[0];
    let peakDate = subDates[0];
    let troughDate = subDates[0];
    const dailyReturns = [];
    
    for (let i = 1; i < subValues.length; i++) {
        const v = subValues[i];
        const vPrev = subValues[i-1];
        if (v > cumMax) {
            cumMax = v;
            peakDate = subDates[i];
        }
        const dd = (v - cumMax) / cumMax;
        if (dd < maxDrawdown) {
            maxDrawdown = dd;
            troughDate = subDates[i];
        }
        dailyReturns.push((v / vPrev) - 1);
    }
    
    let volatility = 0;
    if (dailyReturns.length > 1) {
        const mean = dailyReturns.reduce((a, b) => a + b) / dailyReturns.length;
        const variance = dailyReturns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (dailyReturns.length - 1);
        volatility = Math.sqrt(variance) * Math.sqrt(252);
    }
    
    const sharpe = volatility > 0 ? (annualizedReturn - 0.04) / volatility : 0;
    
    return {
        total_return_pct: parseFloat((totalReturn * 100).toFixed(2)),
        annualized_return_pct: parseFloat((annualizedReturn * 100).toFixed(2)),
        max_drawdown_pct: parseFloat((maxDrawdown * 100).toFixed(2)),
        volatility_pct: parseFloat((volatility * 100).toFixed(2)),
        sharpe_ratio: parseFloat(sharpe.toFixed(2)),
        _actualStartDate: subDates[0],
        _actualEndDate: subDates[subDates.length - 1],
        _troughDate: troughDate,
        _peakDate: peakDate
    };
}

function setupTimeControls() {
    const presetBtns = document.querySelectorAll('.preset-btn[data-start]');
    const startInput = document.getElementById('custom-start-date');
    const endInput = document.getElementById('custom-end-date');
    const normalizeToggle = document.getElementById('normalize-toggle');

    const getNormalizedData = (rawData, minTime, normalize) => {
        let startFactor = 1;
        if (normalize && minTime) {
            // Find the closest point we have on or after minTime
            const basePoint = rawData.find(p => new Date(p.x).getTime() >= minTime);
            if (basePoint) {
                startFactor = 10000 / basePoint.y;
            }
        }
        return rawData.map(p => ({ x: p.x, y: p.y * startFactor }));
    };

    const updateCharts = (startVal, endVal) => {
        const minTime = startVal === 'min' || !startVal ? null : new Date(startVal).getTime();
        const maxTime = endVal === 'max' || !endVal ? null : new Date(endVal).getTime();
        const normalize = normalizeToggle.checked;
        
        currentMinTime = minTime;
        currentMaxTime = maxTime;

        // Recalculate component metrics based on new bounds
        const allItems = [...DATA.etfs, ...DATA.benchmarks];
        allItems.forEach(item => {
            if (minTime || maxTime) {
                item.currentMetrics = recalculateMetricsJS(item, minTime, maxTime);
            } else {
                item.currentMetrics = Object.assign({}, item.metrics);
                item.currentMetrics._actualStartDate = DATA.meta.start_date;
                item.currentMetrics._actualEndDate = DATA.meta.end_date;
            }
        });

        if (performanceChart) {
            performanceChart.options.scales.x.min = minTime;
            performanceChart.options.scales.x.max = maxTime;

            // Update underlying data for normalization
            let datasetIndex = 0;
            DATA.etfs.forEach(item => {
                const rawData = downsampleTimeseries(item.timeseries.dates, item.timeseries.values);
                performanceChart.data.datasets[datasetIndex].data = getNormalizedData(rawData, minTime, normalize);
                datasetIndex++;
            });
            DATA.benchmarks.forEach(item => {
                const rawData = downsampleTimeseries(item.timeseries.dates, item.timeseries.values);
                performanceChart.data.datasets[datasetIndex].data = getNormalizedData(rawData, minTime, normalize);
                datasetIndex++;
            });

            performanceChart.update();
        }
        if (drawdownChart) {
            drawdownChart.options.scales.x.min = minTime;
            drawdownChart.options.scales.x.max = maxTime;
            drawdownChart.update();
        }
        
        // Re-render other dashboard components with subset data
        renderMetrics();
        renderPerformanceTable();
        if (window.renderHeatmapTable) window.renderHeatmapTable();
    };

    presetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const startVal = btn.dataset.start;
            const endVal = btn.dataset.end;

            startInput.value = startVal !== 'min' ? startVal : '';
            endInput.value = endVal !== 'max' ? endVal : '';

            updateCharts(startVal, endVal);
        });
    });

    const handleCustomDateChange = () => {
        document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
        updateCharts(startInput.value, endInput.value);
    };

    startInput.addEventListener('change', handleCustomDateChange);
    endInput.addEventListener('change', handleCustomDateChange);
    document.getElementById('apply-custom-btn').addEventListener('click', handleCustomDateChange);

    normalizeToggle.addEventListener('change', () => {
        let startVal = 'min';
        let endVal = 'max';
        const activeBtn = Array.from(document.querySelectorAll('.preset-btn')).find(b => b.classList.contains('active'));
        if (activeBtn) {
            startVal = activeBtn.dataset.start;
            endVal = activeBtn.dataset.end;
        } else {
            startVal = startInput.value;
            endVal = endInput.value;
        }
        updateCharts(startVal, endVal);
    });
}

// ================================================================
// Quick Metrics
// ================================================================
function renderMetrics() {
    const grid = document.getElementById('metrics-grid');
    const filterSelect = document.getElementById('metrics-filter-select');
    const filterVal = filterSelect ? filterSelect.value : 'all';
    const allItems = [...DATA.etfs, ...DATA.benchmarks];

    if (filterVal === 'all') {
        const bestOverall = allItems.reduce((b, x) =>
            x.currentMetrics.total_return_pct > b.currentMetrics.total_return_pct ? x : b);
        const worstDD = allItems.reduce((b, x) =>
            x.currentMetrics.max_drawdown_pct < b.currentMetrics.max_drawdown_pct ? x : b);
        const bestSharpe = allItems.reduce((b, x) =>
            x.currentMetrics.sharpe_ratio > b.currentMetrics.sharpe_ratio ? x : b);

        const spy = DATA.benchmarks.find(b => b.ticker === 'SPY');
        const mag10 = DATA.etfs.find(e => e.name === 'MAG 10');
        const alpha = mag10 && spy
            ? (mag10.currentMetrics.annualized_return_pct - spy.currentMetrics.annualized_return_pct).toFixed(1)
            : null;

        const actStart = bestOverall.currentMetrics._actualStartDate || DATA.meta.start_date;
        const actEnd = bestOverall.currentMetrics._actualEndDate || DATA.meta.end_date;

        grid.innerHTML = `
            ${metricCard('Best Performer', `${bestOverall.currentMetrics.total_return_pct}%`, bestOverall.name, bestOverall.currentMetrics.total_return_pct >= 0, new Date(bestOverall.currentMetrics._peakDate).getTime(), bestOverall.name)}
            ${metricCard('Best Sharpe', bestSharpe.currentMetrics.sharpe_ratio.toFixed(2), bestSharpe.name, bestSharpe.currentMetrics.sharpe_ratio >= 0, new Date(bestSharpe.currentMetrics._peakDate).getTime(), bestSharpe.name)}
            ${metricCard('Worst Drawdown', `${worstDD.currentMetrics.max_drawdown_pct}%`, worstDD.name, false, new Date(worstDD.currentMetrics._troughDate).getTime(), worstDD.name)}
            ${alpha !== null ? metricCard('MAG 10 vs SPY α', `${alpha}%`, 'Annualized excess return', parseFloat(alpha) >= 0) : metricCard('ETFs Tracked', DATA.etfs.length + DATA.benchmarks.length, 'Hypothetical + Benchmarks', true)}
            ${metricCard('Selected Period', `${yearsBetween(actStart, actEnd).toFixed(1)} yrs`, `${formatDate(actStart)} to ${formatDate(actEnd)}`, null)}
            ${metricCard('Rebalance Freq', 'Monthly', 'Equal-weight reconstitution', null)}
        `;
    } else {
        const [type, idx] = filterVal.split('_');
        const focusItem = type === 'etf' ? DATA.etfs[parseInt(idx)] : DATA.benchmarks[parseInt(idx)];

        const actStart = focusItem.currentMetrics._actualStartDate || DATA.meta.start_date;
        const actEnd = focusItem.currentMetrics._actualEndDate || DATA.meta.end_date;

        grid.innerHTML = `
            ${metricCard('Total Return', `${focusItem.currentMetrics.total_return_pct}%`, focusItem.name, focusItem.currentMetrics.total_return_pct >= 0, new Date(focusItem.currentMetrics._peakDate).getTime(), focusItem.name)}
            ${metricCard('Sharpe Ratio', focusItem.currentMetrics.sharpe_ratio.toFixed(2), 'Risk-adjusted return', focusItem.currentMetrics.sharpe_ratio >= 0, new Date(focusItem.currentMetrics._peakDate).getTime(), focusItem.name)}
            ${metricCard('Max Drawdown', `${focusItem.currentMetrics.max_drawdown_pct}%`, 'Worst trough securely captured', false, new Date(focusItem.currentMetrics._troughDate).getTime(), focusItem.name)}
            ${metricCard('Volatility', `${focusItem.currentMetrics.volatility_pct}%`, 'Annualized variance', null)}
            ${metricCard('Selected Period', `${yearsBetween(actStart, actEnd).toFixed(1)} yrs`, `${formatDate(actStart)} to ${formatDate(actEnd)}`, null)}
            ${metricCard('Rebalance Freq', 'Monthly', 'Equal-weight reconstitution', null)}
        `;
    }

    // Attach click listeners to interactive cards
    grid.querySelectorAll('.metric-card[data-focus-date]').forEach(card => {
        card.addEventListener('click', () => {
            const timeMs = parseInt(card.dataset.focusDate);
            const etfName = card.dataset.focusEtf;
            window.setFocusDate(timeMs, etfName);
        });
    });
}

function metricCard(label, value, subtitle, positive, focusDateMs = null, etfName = null) {
    const cls = positive === null ? 'neutral' : (positive ? 'positive' : 'negative');
    const dataAttr = focusDateMs ? `data-focus-date="${focusDateMs}" data-focus-etf="${etfName}"` : '';
    const clickHint = focusDateMs ? `<div style="font-size: 0.65rem; padding-top: 4px; opacity: 0.7;">⇲ Click to inspect date</div>` : '';
    const pointerCls = focusDateMs ? 'style="cursor: pointer;"' : '';
    
    return `
        <div class="metric-card metric-card--${cls}" ${dataAttr} ${pointerCls}>
            <div class="metric-card__label">${label}</div>
            <div class="metric-card__value">${value}</div>
            <div class="metric-card__subtitle">${subtitle}</div>
            ${clickHint}
        </div>`;
}

function getETFColor(etf, i) {
    if (etf.name === 'Ult-Yield') {
        // Vibrant Amber/Orange
        return { main: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.8)' };
    }
    if (etf.name === 'Ult-VIX') {
        // Unique vibrant rose/magenta
        return { main: '#ec4899', bg: 'rgba(236, 72, 153, 0.12)', border: 'rgba(236, 72, 153, 0.8)' };
    }
    if (etf.name === 'Ult-200SMA') {
        // Emerald Green
        return { main: '#10b981', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.8)' };
    }
    if (etf.name === 'Ult-RiskKPI') {
        // Vibrant Violet/Purple
        return { main: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)', border: 'rgba(139, 92, 246, 0.8)' };
    }
    if (etf.name === 'Ult-Hybrid') {
        // Vibrant Sky Blue
        return { main: '#0ea5e9', bg: 'rgba(14, 165, 233, 0.12)', border: 'rgba(14, 165, 233, 0.8)' };
    }
    const isAnnual = etf.name.toLowerCase().includes('annual');
    if (isAnnual) {
        const siblingName = etf.name.replace(/\s+Annual$/i, '');
        const siblingIdx = DATA.etfs.findIndex(e => e.name === siblingName);
        if (siblingIdx !== -1) {
            return COLORS.etfs[siblingIdx % COLORS.etfs.length];
        }
    }
    return COLORS.etfs[i % COLORS.etfs.length];
}

// ================================================================
// Performance Chart
// ================================================================
function renderPerformanceChart() {
    const ctx = document.getElementById('performance-chart').getContext('2d');

    const datasets = [];

    // ETFs
    DATA.etfs.forEach((etf, i) => {
        let color = getETFColor(etf, i);
        const isAnnual = etf.name.toLowerCase().includes('annual');

        datasets.push({
            label: etf.name,
            data: downsampleTimeseries(etf.timeseries.dates, etf.timeseries.values),
            borderColor: color.main,
            backgroundColor: color.bg,
            borderWidth: 2.5,
            borderDash: isAnnual ? [2, 4] : [], // Dotted style for Annual ETFs
            pointRadius: 0,
            pointHitRadius: 8,
            fill: false,
            tension: 0.1,
            order: 1,
        });
    });

    // Benchmarks
    DATA.benchmarks.forEach((bench, i) => {
        // Map benchmark ticker to corresponding ETF universe
        const benchToUniverse = {
            "SPY": "sp500",
            "EFA": "efa",
            "EEM": "eem"
        };
        
        const uni = benchToUniverse[bench.ticker];
        let color = COLORS.benchmarks[i % COLORS.benchmarks.length];
        
        if (uni) {
            const etfIdx = DATA.etfs.findIndex(e => e.universe === uni);
            if (etfIdx !== -1) {
                color = COLORS.etfs[etfIdx % COLORS.etfs.length];
            }
        }

        datasets.push({
            label: bench.name,
            data: downsampleTimeseries(bench.timeseries.dates, bench.timeseries.values),
            borderColor: color.main,
            backgroundColor: color.bg,
            borderWidth: 1.5,
            borderDash: [6, 3],
            pointRadius: 0,
            pointHitRadius: 8,
            fill: false,
            tension: 0.1,
            order: 2,
        });
    });

    const recessionBandsPlugin = {
        id: 'recessionBands',
        beforeDraw: (chart) => {
            const { ctx, chartArea: { top, bottom, left, right }, scales: { x } } = chart;
            ctx.save();
            ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'; // Subtle highlight band

            const recessions = [
                { start: '2007-12-01', end: '2009-06-30' }, // Great Recession
                { start: '2020-02-01', end: '2020-04-30' }  // COVID-19
            ];

            recessions.forEach(r => {
                const rStart = new Date(r.start).getTime();
                const rEnd = new Date(r.end).getTime();

                if (rEnd >= x.min && rStart <= x.max) {
                    const drawStartVal = Math.max(rStart, x.min);
                    const drawEndVal = Math.min(rEnd, x.max);

                    const startPx = x.getPixelForValue(drawStartVal);
                    const endPx = x.getPixelForValue(drawEndVal);

                    const drawLeft = Math.max(startPx, left);
                    const drawRight = Math.min(endPx, right);

                    if (drawRight > drawLeft) {
                        ctx.fillRect(drawLeft, top, drawRight - drawLeft, bottom - top);
                    }
                }
            });
            ctx.restore();
        }
    };

    performanceChart = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            onClick: (e, elements, chart) => {
                if (!elements || elements.length === 0) return;
                
                const element = elements[0];
                const dataPoint = chart.data.datasets[element.datasetIndex].data[element.index];
                if (!dataPoint) return;
                
                const targetTime = new Date(dataPoint.x).getTime();
                const slider = document.getElementById('holdings-date-slider');
                const select = document.getElementById('holdings-etf-select');
                
                if (slider && select) {
                    const etfIdx = parseInt(select.value);
                    const etf = DATA.etfs[etfIdx];
                    if (etf) {
                        let closestIdx = 0;
                        let minDiff = Infinity;
                        
                        etf.holdings_log.forEach((h, idx) => {
                            const diff = Math.abs(new Date(h.date).getTime() - targetTime);
                            if (diff < minDiff) {
                                minDiff = diff;
                                closestIdx = idx;
                            }
                        });
                        slider.value = closestIdx;
                        slider.dispatchEvent(new Event('input'));
                    }
                }
            },
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(13, 13, 26, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Inter', size: 12, weight: '600' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: $${numberWithCommas(ctx.parsed.y.toFixed(0))}`,
                    },
                },
            },
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'month', displayFormats: { month: 'MMM yyyy' } },
                    grid: { color: COLORS.gridColor, drawBorder: false },
                    ticks: { color: COLORS.tickColor, font: { size: 10 }, maxTicksLimit: 12 },
                },
                y: {
                    grid: { color: COLORS.gridColor, drawBorder: false },
                    ticks: {
                        color: COLORS.tickColor,
                        font: { family: 'JetBrains Mono', size: 10 },
                        callback: v => '$' + numberWithCommas(v),
                    },
                },
            },
        },
        plugins: [recessionBandsPlugin, focusLinePlugin]
    });

    // Custom legend
    renderCustomLegend('perf-legend', performanceChart);
}

// ================================================================
// Custom Legend
// ================================================================
function renderCustomLegend(containerId, chart) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';

    chart.data.datasets.forEach((ds, i) => {
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<span class="legend-dot" style="background:${ds.borderColor}"></span>${ds.label}`;
        item.addEventListener('click', () => {
            const meta = chart.getDatasetMeta(i);
            meta.hidden = !meta.hidden;
            item.classList.toggle('inactive', meta.hidden);
            chart.update();
        });
        container.appendChild(item);
    });
}

// ================================================================
// Performance Table
// ================================================================
function renderPerformanceTable() {
    const table = document.getElementById('perf-table');
    const columns = [
        { key: 'name', label: 'Name', format: v => v },
        { key: 'total_return_pct', label: 'Total Return', format: v => colorVal(v, '%') },
        { key: 'annualized_return_pct', label: 'Ann. Return', format: v => colorVal(v, '%') },
        { key: 'max_drawdown_pct', label: 'Max Drawdown', format: v => colorVal(v, '%') },
        { key: 'sharpe_ratio', label: 'Sharpe Ratio', format: v => colorVal(v, '') },
        { key: 'volatility_pct', label: 'Volatility', format: v => `${v}%` },
    ];

    // Build rows data
    const rows = [];
    DATA.etfs.forEach((etf, i) => {
        const color = COLORS.etfs[i % COLORS.etfs.length];
        rows.push({
            name: `<span class="etf-badge" style="background:${color.main}"></span>${etf.name}`,
            rawName: etf.name,
            isETF: true,
            ...etf.currentMetrics,
        });
    });
    DATA.benchmarks.forEach((bench, i) => {
        rows.push({
            name: bench.name,
            rawName: bench.name,
            isETF: false,
            ...bench.currentMetrics,
        });
    });

    // Sort
    if (sortState.column) {
        rows.sort((a, b) => {
            let av = a[sortState.column], bv = b[sortState.column];
            if (typeof av === 'string') av = av.toLowerCase();
            if (typeof bv === 'string') bv = bv.toLowerCase();
            return sortState.direction === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
        });
    }

    table.innerHTML = `
        <thead><tr>
            ${columns.map(c => {
                let cls = '';
                if (sortState.column === c.key) cls = sortState.direction === 'asc' ? 'sorted-asc' : 'sorted-desc';
                return `<th class="${cls}" data-col="${c.key}">${c.label}</th>`;
            }).join('')}
        </tr></thead>
        <tbody>
            ${rows.map(r => `
                <tr class="${r.isETF ? '' : 'bench-row'}">
                    ${columns.map(c => {
                        const val = c.key === 'name' ? r.name : r[c.key];
                        return `<td>${c.key === 'name' ? val : c.format(val)}</td>`;
                    }).join('')}
                </tr>
            `).join('')}
        </tbody>`;

    // Sort handlers
    table.querySelectorAll('th').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.dataset.col;
            if (col === 'name') {
                sortState.column = 'rawName';
            } else {
                sortState.column = col;
            }
            sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
            renderPerformanceTable();
        });
    });
}

// ================================================================
// Drawdown Chart
// ================================================================
function renderDrawdownChart() {
    const ctx = document.getElementById('drawdown-chart').getContext('2d');

    const datasets = [];

    DATA.etfs.forEach((etf, i) => {
        let color = getETFColor(etf, i);
        const isAnnual = etf.name.toLowerCase().includes('annual');

        datasets.push({
            label: etf.name,
            data: downsampleTimeseries(etf.drawdown.dates, etf.drawdown.values),
            borderColor: color.main,
            backgroundColor: isAnnual ? 'transparent' : color.bg,
            borderWidth: 1.5,
            borderDash: isAnnual ? [2, 4] : [], // Dotted style for Annual ETFs
            pointRadius: 0,
            fill: !isAnnual,
            tension: 0.1,
        });
    });

    DATA.benchmarks.forEach((bench, i) => {
        const benchToUniverse = {
            "SPY": "sp500",
            "EFA": "efa",
            "EEM": "eem"
        };
        const uni = benchToUniverse[bench.ticker];
        let color = COLORS.benchmarks[i % COLORS.benchmarks.length];
        if (uni) {
            const etfIdx = DATA.etfs.findIndex(e => e.universe === uni);
            if (etfIdx !== -1) {
                color = COLORS.etfs[etfIdx % COLORS.etfs.length];
            }
        }

        datasets.push({
            label: bench.name,
            data: downsampleTimeseries(bench.drawdown.dates, bench.drawdown.values),
            borderColor: color.main,
            backgroundColor: 'transparent',
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            fill: false,
            tension: 0.1,
        });
    });

    drawdownChart = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(13, 13, 26, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleFont: { family: 'Inter', size: 12, weight: '600' },
                    bodyFont: { family: 'JetBrains Mono', size: 11 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`,
                    },
                },
            },
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'month', displayFormats: { month: 'MMM yyyy' } },
                    grid: { color: COLORS.gridColor, drawBorder: false },
                    ticks: { color: COLORS.tickColor, font: { size: 10 }, maxTicksLimit: 10 },
                },
                y: {
                    grid: { color: COLORS.gridColor, drawBorder: false },
                    ticks: {
                        color: COLORS.tickColor,
                        font: { family: 'JetBrains Mono', size: 10 },
                        callback: v => v.toFixed(0) + '%',
                    },
                },
            },
        },
        plugins: [focusLinePlugin]
    });
}

// ================================================================
// Holdings Inspector
// ================================================================
function renderHoldingsInspector() {
    const controlsEl = document.getElementById('holdings-controls');
    const gridEl = document.getElementById('holdings-grid');

    if (!DATA.etfs.length || !DATA.etfs[0].holdings_log.length) {
        gridEl.innerHTML = '<p style="color:var(--text-muted)">No holdings data available</p>';
        return;
    }

    // Build controls
    const etfOptions = DATA.etfs.map((e, i) => `<option value="${i}">${e.name}</option>`).join('');

    controlsEl.innerHTML = `
        <div class="control-group">
            <label>Select ETF</label>
            <select id="holdings-etf-select">${etfOptions}</select>
        </div>
        <div class="control-group slider-container">
            <label>Rebalance Date</label>
            <input type="range" id="holdings-date-slider" min="0" max="${DATA.etfs[0].holdings_log.length - 1}" value="0">
        </div>
        <div class="control-group">
            <label>Date</label>
            <div class="date-display" id="holdings-date-display">${DATA.etfs[0].holdings_log[0].date}</div>
        </div>
    `;

    const select = document.getElementById('holdings-etf-select');
    const slider = document.getElementById('holdings-date-slider');

    const updateHoldings = () => {
        const etfIdx = parseInt(select.value);
        const etf = DATA.etfs[etfIdx];
        const dateIdx = parseInt(slider.value);
        const holding = etf.holdings_log[dateIdx];
        const colorSet = getETFColor(etf, etfIdx);

        document.getElementById('holdings-date-display').textContent = holding.date;

        gridEl.innerHTML = holding.holdings.map(h => {
            const name = DATA.ticker_names ? (DATA.ticker_names[h.ticker] || '') : '';
            return `
            <div class="holding-card" title="${name}">
                <div class="holding-card__header">
                    <a href="https://finance.yahoo.com/quote/${h.ticker}" target="_blank" rel="noopener noreferrer" class="holding-card__ticker" style="color: inherit; text-decoration: none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${h.ticker}</a>
                    <div class="holding-card__weight">${(h.weight * 100).toFixed(1)}%</div>
                </div>
                <!-- If no name exists, fall back to "—" so lines remain uniform -->
                <div class="holding-card__name">${name || '—'}</div>
                <div class="holding-card__bar" style="background:${colorSet.main}"></div>
            </div>
            `;
        }).join('');
    };

    select.addEventListener('change', () => {
        const etfIdx = parseInt(select.value);
        const etf = DATA.etfs[etfIdx];
        slider.max = etf.holdings_log.length - 1;
        slider.value = 0;
        updateHoldings();
    });

    slider.addEventListener('input', updateHoldings);
    updateHoldings();
}

// ================================================================
// Monthly Returns Heatmap
// ================================================================
function renderHeatmap() {
    const controlsEl = document.getElementById('heatmap-controls');
    const containerEl = document.getElementById('heatmap-container');

    const allItems = [...DATA.etfs, ...DATA.benchmarks];
    const options = allItems.map((item, i) =>
        `<option value="${i}">${item.name}</option>`
    ).join('');
    
    const compareOptions = `<option value="-1">None (Absolute Returns)</option>` + options;

    controlsEl.innerHTML = `
        <div class="control-group">
            <label>Select Fund</label>
            <select id="heatmap-select">${options}</select>
        </div>
        <div class="control-group">
            <label>Compare To</label>
            <select id="heatmap-compare-select">${compareOptions}</select>
        </div>
    `;

    const select = document.getElementById('heatmap-select');
    const compareSelect = document.getElementById('heatmap-compare-select');

    window.renderHeatmapTable = () => {
        const idx = parseInt(select.value);
        const compareIdx = parseInt(compareSelect.value);
        
        const item = allItems[idx];
        let returns = item.monthly_returns;
        
        let compareReturns = null;
        let compareName = '';
        if (compareIdx >= 0) {
            compareReturns = allItems[compareIdx].monthly_returns;
            compareName = allItems[compareIdx].name;
        }

        // Filter based on current timeframe selection
        if (currentMinTime || currentMaxTime) {
            const minTimeStr = currentMinTime ? new Date(currentMinTime) : new Date('2000-01-01');
            const maxTimeStr = currentMaxTime ? new Date(currentMaxTime) : new Date('2100-01-01');
            
            const minYear = minTimeStr.getUTCFullYear();
            const minMonth = minTimeStr.getUTCMonth() + 1;
            const maxYear = maxTimeStr.getUTCFullYear();
            const maxMonth = maxTimeStr.getUTCMonth() + 1;
            
            const inRange = (r) => {
                if (r.year < minYear || r.year > maxYear) return false;
                if (r.year === minYear && r.month < minMonth) return false;
                if (r.year === maxYear && r.month > maxMonth) return false;
                return true;
            };
            
            returns = returns.filter(inRange);
            if (compareReturns) {
                compareReturns = compareReturns.filter(inRange);
            }
        }

        if (!returns || !returns.length) {
            containerEl.innerHTML = '<p style="color:var(--text-muted)">No monthly return data</p>';
            return;
        }

        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

        // Group by year and store both fund and benchmark
        const byYear = {};
        returns.forEach(r => {
            if (!byYear[r.year]) byYear[r.year] = {};
            byYear[r.year][r.month] = { fund: r.return, bench: 0 };
        });
        
        if (compareReturns) {
            compareReturns.forEach(r => {
                if (byYear[r.year] && byYear[r.year][r.month]) {
                    byYear[r.year][r.month].bench = r.return;
                }
            });
        }

        const years = Object.keys(byYear).sort();

        // Find max absolute return (or alpha) for color scaling
        let maxAbs = 1;
        const fundReturnsArr = [];
        const benchReturnsArr = [];
        
        years.forEach(year => {
            Object.keys(byYear[year]).forEach(monthNum => {
                const val = byYear[year][monthNum];
                if (compareReturns) {
                    fundReturnsArr.push(val.fund / 100);
                    benchReturnsArr.push(val.bench / 100);
                }
                const diff = compareReturns ? (val.fund - val.bench) : val.fund;
                if (Math.abs(diff) > maxAbs) maxAbs = Math.abs(diff);
            });
        });

        let statsHtml = '';
        if (compareReturns && fundReturnsArr.length > 1) {
            const meanFund = fundReturnsArr.reduce((a, b) => a + b) / fundReturnsArr.length;
            const meanBench = benchReturnsArr.reduce((a, b) => a + b) / benchReturnsArr.length;
            
            let covariance = 0;
            let varianceBench = 0;
            for (let i = 0; i < fundReturnsArr.length; i++) {
                const diffBench = benchReturnsArr[i] - meanBench;
                covariance += (fundReturnsArr[i] - meanFund) * diffBench;
                varianceBench += diffBench * diffBench;
            }
            covariance /= (fundReturnsArr.length - 1);
            varianceBench /= (fundReturnsArr.length - 1);
            
            const beta = varianceBench > 0 ? covariance / varianceBench : 1.0;
            const fundAnn = item.currentMetrics.annualized_return_pct / 100;
            const benchAnn = allItems[compareIdx].currentMetrics.annualized_return_pct / 100;
            const alpha = (fundAnn - 0.04) - beta * (benchAnn - 0.04);
            const alphaPct = alpha * 100;
            
            statsHtml = `<div style="margin-bottom: 16px; padding: 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 6px; display:flex; gap: 24px; font-size: 0.9rem; color: var(--text-secondary);">
                <div><span style="opacity: 0.8;">Beta (vs ${compareName}):</span> <strong style="color:var(--text-primary); margin-left: 4px;">${beta.toFixed(2)}</strong></div>
                <div><span style="opacity: 0.8;">Jensen's Alpha:</span> <strong class="${alphaPct >= 0 ? 'positive' : 'negative'}" style="margin-left: 4px;">${alphaPct > 0 ? '+' : ''}${alphaPct.toFixed(2)}%</strong></div>
                <div style="margin-left: auto; font-size: 0.8rem; opacity: 0.6; align-self: center;">Assumes 4.0% Risk-Free Rate</div>
            </div>`;
        }

        let html = '<table class="heatmap-table"><thead><tr><th>Year</th>';
        months.forEach(m => html += `<th>${m}</th>`);
        html += '<th>Annual</th>';
        if (compareReturns) html += '<th>β (Beta)</th><th>α (Alpha)</th>';
        html += '</tr></thead><tbody>';

        years.forEach(year => {
            html += `<tr><td>${year}</td>`;
            let fundAnnualReturn = 1;
            let benchAnnualReturn = 1;
            let hasData = false;
            
            const yFundArr = [];
            const yBenchArr = [];

            months.forEach((_, mi) => {
                const monthNum = mi + 1;
                const d = byYear[year]?.[monthNum];
                if (d !== undefined) {
                    hasData = true;
                    fundAnnualReturn *= (1 + d.fund / 100);
                    benchAnnualReturn *= (1 + d.bench / 100);
                    
                    if (compareReturns) {
                        yFundArr.push(d.fund / 100);
                        yBenchArr.push(d.bench / 100);
                    }
                    
                    const val = compareReturns ? (d.fund - d.bench) : d.fund;
                    const intensity = Math.min(Math.abs(val) / maxAbs, 1);
                    const bg = val >= 0
                        ? `rgba(16, 185, 129, ${0.1 + intensity * 0.6})`
                        : `rgba(239, 68, 68, ${0.1 + intensity * 0.6})`;
                    const textColor = intensity > 0.5 ? '#fff' : (val >= 0 ? '#10b981' : '#ef4444');
                    
                    const titleText = compareReturns 
                        ? `${months[mi]} ${year}:\n${item.name}: ${d.fund.toFixed(2)}%\n${compareName}: ${d.bench.toFixed(2)}%\nDiff: ${val.toFixed(2)}%`
                        : `${months[mi]} ${year}: ${val.toFixed(2)}%`;
                        
                    html += `<td style="background:${bg};color:${textColor}" title="${titleText}">${val.toFixed(1)}%</td>`;
                } else {
                    html += '<td style="color:var(--text-muted)">—</td>';
                }
            });

            // Annual total
            if (hasData) {
                const fundAnnual = (fundAnnualReturn - 1) * 100;
                const benchAnnual = (benchAnnualReturn - 1) * 100;
                const annual = compareReturns ? (fundAnnual - benchAnnual) : fundAnnual;
                
                const aColor = annual >= 0 ? '#10b981' : '#ef4444';
                
                const titleText = compareReturns 
                    ? `Annual ${year}:\n${item.name}: ${fundAnnual.toFixed(2)}%\n${compareName}: ${benchAnnual.toFixed(2)}%\nDiff: ${annual.toFixed(2)}%`
                    : `Annual ${year}: ${annual.toFixed(2)}%`;
                    
                html += `<td style="color:${aColor};font-weight:600" title="${titleText}">${annual.toFixed(1)}%</td>`;
                
                if (compareReturns) {
                    let yBeta = 1.0;
                    let yAlphaPct = 0;
                    
                    if (yFundArr.length > 1) {
                         const mFund = yFundArr.reduce((a,b)=>a+b)/yFundArr.length;
                         const mBench = yBenchArr.reduce((a,b)=>a+b)/yBenchArr.length;
                         
                         let cov = 0; let varB = 0;
                         for(let i=0; i<yFundArr.length; i++) {
                             const diffB = yBenchArr[i] - mBench;
                             cov += (yFundArr[i] - mFund) * diffB;
                             varB += diffB * diffB;
                         }
                         yBeta = varB > 0 ? cov / varB : 1.0;
                         
                         const alpha = ((fundAnnualReturn - 1) - 0.04) - yBeta * ((benchAnnualReturn - 1) - 0.04);
                         yAlphaPct = alpha * 100;
                    }
                    
                    html += `<td style="color:var(--text-primary); font-size: 0.85rem; font-family: 'JetBrains Mono', monospace;" title="Annual Beta vs ${compareName}">${yBeta.toFixed(2)}</td>`;
                    const alphaColor = yAlphaPct >= 0 ? '#10b981' : '#ef4444';
                    html += `<td style="color:${alphaColor}; font-size: 0.85rem; font-family: 'JetBrains Mono', monospace; font-weight: 500" title="Jensen's Alpha (Assumes 4% RF)">${yAlphaPct > 0 ? '+' : ''}${yAlphaPct.toFixed(2)}%</td>`;
                }
            } else {
                html += '<td>—</td>';
                if (compareReturns) html += '<td>—</td><td>—</td>';
            }

            html += '</tr>';
        });

        html += '</tbody></table>';
        containerEl.innerHTML = statsHtml + html;
    };

    select.addEventListener('change', window.renderHeatmapTable);
    compareSelect.addEventListener('change', window.renderHeatmapTable);
    window.renderHeatmapTable();
}

// ================================================================
// Utility functions
// ================================================================

function downsampleTimeseries(dates, values) {
    // Convert to Chart.js {x, y} format, skip every N points for performance
    const maxPoints = 500;
    const step = Math.max(1, Math.floor(dates.length / maxPoints));
    const result = [];
    for (let i = 0; i < dates.length; i += step) {
        result.push({ x: dates[i], y: values[i] });
    }
    // Always include last point
    if (result.length && result[result.length - 1].x !== dates[dates.length - 1]) {
        result.push({ x: dates[dates.length - 1], y: values[values.length - 1] });
    }
    return result;
}

function colorVal(val, suffix) {
    const cls = val >= 0 ? 'positive' : 'negative';
    return `<span class="${cls}">${val}${suffix}</span>`;
}

function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function yearsBetween(start, end) {
    const s = new Date(start);
    const e = new Date(end);
    return (e - s) / (365.25 * 24 * 60 * 60 * 1000);
}
