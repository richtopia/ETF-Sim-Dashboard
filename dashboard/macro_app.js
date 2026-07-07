/**
     * Historical Macro Backtesting App
     * Loads macro_historical.json and manages charts and metrics.
     */

    let DATA = null;
    let performanceChart = null;
    let scoreChart = null;
    let chartScale = 'logarithmic'; // Default scale

    const COLORS = {
        equity: { main: '#ef4444', bg: 'rgba(239, 68, 68, 0.08)' },
        gold: { main: '#f59e0b', bg: 'rgba(245, 158, 11, 0.08)' },
        treasury: { main: '#10b981', bg: 'rgba(16, 185, 129, 0.08)' },
        sma_gold: { main: '#a855f7', bg: 'rgba(168, 85, 247, 0.08)' },
        sma_treas: { main: '#ec4899', bg: 'rgba(236, 72, 153, 0.08)' },
        macro_gold: { main: '#f43f5e', bg: 'rgba(244, 63, 94, 0.08)' },
        macro_treas: { main: '#0ea5e9', bg: 'rgba(14, 165, 233, 0.08)' }
    };

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            const response = await fetch("macro_historical.json");
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            DATA = await response.json();
            
            // Set initial date inputs
            const dates = DATA.dates;
            const startInput = document.getElementById("custom-start-date");
            const endInput = document.getElementById("custom-end-date");
            
            startInput.value = dates[0];
            startInput.min = dates[0];
            startInput.max = dates[dates.length - 1];
            
            endInput.value = dates[dates.length - 1];
            endInput.min = dates[0];
            endInput.max = dates[dates.length - 1];
            
            // Event listeners
            const presetBtns = document.querySelectorAll(".preset-btn[data-start]");
            
            function clearPresetActiveStates() {
                presetBtns.forEach(b => b.classList.remove("preset-btn--active"));
            }

            startInput.addEventListener("change", () => {
                clearPresetActiveStates();
            });
            endInput.addEventListener("change", () => {
                clearPresetActiveStates();
            });
            
            document.getElementById("apply-custom-btn").addEventListener("click", () => {
                updateDashboard();
            });
            
            document.getElementById("normalize-toggle").addEventListener("change", () => {
                updateDashboard();
            });
            
            document.getElementById("scale-log").addEventListener("click", () => setChartScale('logarithmic'));
            document.getElementById("scale-linear").addEventListener("click", () => setChartScale('linear'));
            
            // Preset Regimes buttons
            presetBtns.forEach(btn => {
                btn.addEventListener("click", () => {
                    clearPresetActiveStates();
                    btn.classList.add("preset-btn--active");
                    
                    const startVal = btn.getAttribute("data-start");
                    let endVal = btn.getAttribute("data-end");
                    if (endVal === "max") {
                        endVal = dates[dates.length - 1];
                    }
                    
                    startInput.value = startVal;
                    endInput.value = endVal;
                    
                    updateDashboard();
                });
            });
            
            // Toggles
            const checkboxIds = [
                "toggle-equity", "toggle-gold", "toggle-treasury",
                "toggle-sma-gold", "toggle-sma-treas", "toggle-macro-gold", "toggle-macro-treas"
            ];
            checkboxIds.forEach(id => {
                document.getElementById(id).addEventListener("change", updateDashboard);
            });

            document.getElementById("metrics-filter-select").addEventListener("change", () => renderMetrics());
            
            // Render first time
            updateDashboard();
            
        } catch (err) {
            console.error("Failed to load historical macro data:", err);
        }
    });

    function setChartScale(scale) {
        chartScale = scale;
        document.getElementById("scale-log").classList.toggle("toggle-btn--active", scale === 'logarithmic');
        document.getElementById("scale-linear").classList.toggle("toggle-btn--active", scale === 'linear');
        
        if (performanceChart) {
            performanceChart.options.scales.y.type = scale;
            performanceChart.update();
        }
    }

    function updateDashboard() {
        if (!DATA) return;
        
        const dates = DATA.dates;
        const startDateStr = document.getElementById("custom-start-date").value;
        const endDateStr = document.getElementById("custom-end-date").value;
        
        // Find indices
        let startIdx = dates.findIndex(d => d >= startDateStr);
        let endIdx = dates.findIndex(d => d >= endDateStr);
        
        if (startIdx === -1) startIdx = 0;
        if (endIdx === -1 || endIdx < startIdx) endIdx = dates.length - 1;
        
        // Clamp indices
        startIdx = Math.max(0, Math.min(startIdx, dates.length - 1));
        endIdx = Math.max(startIdx, Math.min(endIdx, dates.length - 1));
        
        // Slice dates
        const slicedDates = dates.slice(startIdx, endIdx + 1);
        
        // Recalculate metrics for scoreboard
        calculateAndRenderMetrics(startIdx, endIdx);
        
        // Render charts
        renderPerformanceChart(slicedDates, startIdx, endIdx);
        renderScoreChart(slicedDates, startIdx, endIdx);
        
        // Render new sub-panels
        renderMetrics();
        renderHoldingsInspector();
        renderHeatmap();
    }

    function calculateAndRenderMetrics(startIdx, endIdx) {
        const tbody = document.getElementById("metrics-table-body");
        tbody.innerHTML = "";
        
        // Define all strategies to calculate
        const items = [
            { id: "toggle-equity", name: "Equity Composite", key: "equity", isPortfolio: false, data: DATA.assets.equity, color: COLORS.equity.main },
            { id: "toggle-gold", name: "Gold Spot", key: "gold", isPortfolio: false, data: DATA.assets.gold, color: COLORS.gold.main },
            { id: "toggle-treasury", name: "U.S. Treasuries", key: "treasury", isPortfolio: false, data: DATA.assets.treasury, color: COLORS.treasury.main },
            { id: "toggle-sma-gold", name: "200-SMA Switch (Gold)", key: "sma_gold", isPortfolio: true, data: DATA.portfolios.sma_gold, color: COLORS.sma_gold.main },
            { id: "toggle-sma-treas", name: "200-SMA Switch (Treasury)", key: "sma_treas", isPortfolio: true, data: DATA.portfolios.sma_treas, color: COLORS.sma_treas.main },
            { id: "toggle-macro-gold", name: "Macro Score (Gold)", key: "macro_gold", isPortfolio: true, data: DATA.portfolios.macro_gold, color: COLORS.macro_gold.main },
            { id: "toggle-macro-treas", name: "Macro Score (Treasury)", key: "macro_treas", isPortfolio: true, data: DATA.portfolios.macro_treas, color: COLORS.macro_treas.main }
        ];
        
        items.forEach(item => {
            const isChecked = document.getElementById(item.id).checked;
            
            // Calculate metrics
            const values = item.data;
            const startVal = values[startIdx];
            const endVal = values[endIdx];
            
            const totalRet = ((endVal - startVal) / startVal) * 100;
            
            // Ann. Return
            const days = (new Date(DATA.dates[endIdx]) - new Date(DATA.dates[startIdx])) / (1000 * 60 * 60 * 24);
            const annRet = days > 30 ? (Math.pow(endVal / startVal, 365.25 / days) - 1) * 100 : 0;
            
            // Max Drawdown
            let maxDD = 0;
            let peak = -Infinity;
            for (let i = startIdx; i <= endIdx; i++) {
                if (values[i] > peak) peak = values[i];
                const dd = ((values[i] - peak) / peak) * 100;
                if (dd < maxDD) maxDD = dd;
            }
            
            // Sharpe Ratio (assumes 4% RF rate)
            // Calculate daily standard deviation
            const dailyRets = [];
            for (let i = startIdx + 1; i <= endIdx; i++) {
                dailyRets.push((values[i] - values[i - 1]) / values[i - 1]);
            }
            
            let sharpe = 0;
            if (dailyRets.length > 10) {
                const mean = dailyRets.reduce((a, b) => a + b, 0) / dailyRets.length;
                const variance = dailyRets.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (dailyRets.length - 1);
                const dailyStd = Math.sqrt(variance);
                const annStd = dailyStd * Math.sqrt(252);
                
                const excess = annRet - 4.0;
                sharpe = annStd > 0.001 ? excess / (annStd * 100) : 0;
            }
            
            // Add row
            const tr = document.createElement("tr");
            tr.style.opacity = isChecked ? "1" : "0.4";
            tr.innerHTML = `
                <td style="text-align: left; font-weight: 600;">
                    <span style="display:inline-block; width:10px; height:10px; background:${item.color}; border-radius:3px; margin-right:8px;"></span>
                    ${item.name}
                </td>
                <td class="${totalRet >= 0 ? 'text-green' : 'text-red'}">${totalRet.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}%</td>
                <td class="${annRet >= 0 ? 'text-green' : 'text-red'}">${annRet.toFixed(2)}%</td>
                <td class="text-red">${maxDD.toFixed(2)}%</td>
                <td style="font-weight:600; color:var(--text-primary);">${sharpe.toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function downsampleTimeseries(dates, values, limit = 500) {
        if (dates.length <= limit) return dates.map((d, i) => ({ x: new Date(d), y: values[i] }));
        
        const step = Math.ceil(dates.length / limit);
        const result = [];
        
        for (let i = 0; i < dates.length; i += step) {
            result.push({
                x: new Date(dates[i]),
                y: values[i]
            });
        }
        
        // Ensure final point is included
        const lastIdx = dates.length - 1;
        if (result.length > 0 && result[result.length - 1].x.getTime() !== new Date(dates[lastIdx]).getTime()) {
            result.push({
                x: new Date(dates[lastIdx]),
                y: values[lastIdx]
            });
        }
        return result;
    }

    // Custom Chart.js Plugin to draw NBER recessions shading
    const recessionPlugin = {
        id: 'recessions',
        beforeDraw: (chart) => {
            if (!DATA || !DATA.recessions || !chart.chartArea) return;
            
            const ctx = chart.ctx;
            const xAxis = chart.scales.x;
            
            // Find sliced date indexes based on date inputs
            const dates = DATA.dates;
            const startDateStr = document.getElementById("custom-start-date").value;
            const endDateStr = document.getElementById("custom-end-date").value;
            
            let startIdx = dates.findIndex(d => d >= startDateStr);
            let endIdx = dates.findIndex(d => d >= endDateStr);
            if (startIdx === -1) startIdx = 0;
            if (endIdx === -1 || endIdx < startIdx) endIdx = dates.length - 1;
            
            // Compute periods
            const periods = [];
            let inRec = false;
            let startVal = null;
            
            for (let idx = startIdx; idx <= endIdx; idx++) {
                const isRec = DATA.recessions[idx] === 1;
                const dVal = new Date(dates[idx]);
                
                if (isRec && !inRec) {
                    inRec = true;
                    startVal = dVal;
                } else if (!isRec && inRec) {
                    inRec = false;
                    periods.push({ start: startVal, end: dVal });
                }
            }
            if (inRec) {
                periods.push({ start: startVal, end: new Date(dates[endIdx]) });
            }
            
            // Draw bands
            ctx.save();
            ctx.fillStyle = 'rgba(255, 255, 255, 0.045)'; // Subtle NBER shading in dark mode
            
            periods.forEach(p => {
                const xStart = xAxis.getPixelForValue(p.start);
                const xEnd = xAxis.getPixelForValue(p.end);
                
                // Keep inside chart boundaries
                const xLeft = Math.max(chart.chartArea.left, xStart);
                const xRight = Math.min(chart.chartArea.right, xEnd);
                
                if (xRight > xLeft) {
                    ctx.fillRect(
                        xLeft, 
                        chart.chartArea.top, 
                        xRight - xLeft, 
                        chart.chartArea.bottom - chart.chartArea.top
                    );
                }
            });
            ctx.restore();
        }
    };


    function renderPerformanceChart(slicedDates, startIdx, endIdx) {
        const ctx = document.getElementById("performance-chart").getContext("2d");
        
        const datasets = [];
        
        // Map configs
        const configs = [
            { id: "toggle-equity", label: "Equity Composite", data: DATA.assets.equity, color: COLORS.equity },
            { id: "toggle-gold", label: "Gold Spot", data: DATA.assets.gold, color: COLORS.gold },
            { id: "toggle-treasury", label: "U.S. Treasuries", data: DATA.assets.treasury, color: COLORS.treasury },
            { id: "toggle-sma-gold", label: "200-SMA Switch (Gold)", data: DATA.portfolios.sma_gold, color: COLORS.sma_gold },
            { id: "toggle-sma-treas", label: "200-SMA Switch (Treasury)", data: DATA.portfolios.sma_treas, color: COLORS.sma_treas },
            { id: "toggle-macro-gold", label: "Macro Score (Gold)", data: DATA.portfolios.macro_gold, color: COLORS.macro_gold },
            { id: "toggle-macro-treas", label: "Macro Score (Treasury)", data: DATA.portfolios.macro_treas, color: COLORS.macro_treas }
        ];
        
        configs.forEach(cfg => {
            const isChecked = document.getElementById(cfg.id).checked;
            if (isChecked) {
                // Slice values
                const slicedVals = cfg.data.slice(startIdx, endIdx + 1);
                
                // Normalize sliced values if checkbox is checked
                const isNormalize = document.getElementById("normalize-toggle").checked;
                const normalizedVals = isNormalize 
                    ? slicedVals.map(v => (v / slicedVals[0]) * 100)
                    : slicedVals;
                
                datasets.push({
                    label: cfg.label,
                    data: downsampleTimeseries(slicedDates, normalizedVals),
                    borderColor: cfg.color.main,
                    backgroundColor: cfg.color.bg,
                    borderWidth: 1.8,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.05
                });
            }
        });
        
        if (performanceChart) {
            performanceChart.destroy();
        }
        
        performanceChart = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            plugins: [recessionPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'year' },
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: { color: '#555570', font: { size: 10 } }
                    },
                    y: {
                        type: chartScale,
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: {
                            color: '#555570',
                            font: { size: 10 },
                            callback: function(value) {
                                const isNormalize = document.getElementById("normalize-toggle").checked;
                                return isNormalize 
                                    ? value.toLocaleString() + '%' 
                                    : '$' + value.toLocaleString(undefined, {maximumFractionDigits: 0});
                            }
                        }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    function renderScoreChart(slicedDates, startIdx, endIdx) {
        const ctx = document.getElementById("score-chart").getContext("2d");
        
        const scoreSlice = DATA.indicators.macro_score.slice(startIdx, endIdx + 1);
        const smaSlice = DATA.indicators.sma_state.slice(startIdx, endIdx + 1);
        const unempSlice = DATA.indicators.unemp_state.slice(startIdx, endIdx + 1);
        const fedSlice = DATA.indicators.fed_state.slice(startIdx, endIdx + 1);
        
        if (scoreChart) {
            scoreChart.destroy();
        }
        
        scoreChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Consolidated Macro Score',
                        data: downsampleTimeseries(slicedDates, scoreSlice),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        pointRadius: 0,
                        tension: 0.1,
                        order: 1
                    },
                    {
                        label: 'S&P 500 < 200-SMA',
                        data: downsampleTimeseries(slicedDates, smaSlice),
                        borderColor: 'rgba(239, 68, 68, 0.4)',
                        backgroundColor: 'rgba(239, 68, 68, 0.05)',
                        borderWidth: 0,
                        fill: true,
                        pointRadius: 0,
                        tension: 0,
                        order: 2
                    },
                    {
                        label: 'Sahm Rule Triggered',
                        data: downsampleTimeseries(slicedDates, unempSlice),
                        borderColor: 'rgba(245, 158, 11, 0.4)',
                        backgroundColor: 'rgba(245, 158, 11, 0.05)',
                        borderWidth: 0,
                        fill: true,
                        pointRadius: 0,
                        tension: 0,
                        order: 3
                    },
                    {
                        label: 'Fed Rate Hiking Cycle',
                        data: downsampleTimeseries(slicedDates, fedSlice),
                        borderColor: 'rgba(16, 185, 129, 0.4)',
                        backgroundColor: 'rgba(16, 185, 129, 0.05)',
                        borderWidth: 0,
                        fill: true,
                        pointRadius: 0,
                        tension: 0,
                        order: 4
                    }
                ]
            },
            plugins: [recessionPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'year' },
                        grid: { display: false },
                        ticks: { color: '#555570', font: { size: 10 } }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: { color: '#555570', font: { size: 10 } }
                    }
                },
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }

    // ================================================================
    // Holdings Inspector
    // ================================================================
    function renderHoldingsInspector() {
        const controlsEl = document.getElementById("holdings-controls");
        const gridEl = document.getElementById("holdings-grid");
        if (!controlsEl || !gridEl) return;
        
        const items = [
            { name: "200-SMA Switch (Gold)", key: "sma_gold" },
            { name: "200-SMA Switch (Treasury)", key: "sma_treas" },
            { name: "Macro Score (Gold)", key: "macro_gold" },
            { name: "Macro Score (Treasury)", key: "macro_treas" }
        ];
        
        if (!controlsEl.innerHTML) {
            const options = items.map((it, i) => `<option value="${i}">${it.name}</option>`).join('');
            controlsEl.innerHTML = `
                <div class="control-group">
                    <label>Select Portfolio</label>
                    <select id="holdings-etf-select" style="background:var(--bg-input); border:1px solid var(--border-color); color:#fff; border-radius:6px; padding:6px; outline:none; font-family:'Inter',sans-serif; cursor:pointer;">${options}</select>
                </div>
                <div class="control-group slider-container" style="margin-left: 24px; flex-grow: 1;">
                    <label>Select Rebalance Date</label>
                    <input type="range" id="holdings-date-slider" min="0" max="100" value="0" style="width:100%;">
                </div>
                <div class="control-group" style="margin-left: 24px;">
                    <label>Date</label>
                    <div class="date-display" id="holdings-date-display" style="padding: 6px 12px; background:rgba(255,255,255,0.02); border:1px solid var(--border-color); border-radius:6px; font-family:'JetBrains Mono',monospace;">—</div>
                </div>
            `;
            
            document.getElementById("holdings-etf-select").addEventListener("change", () => setupHoldingsSlider());
            document.getElementById("holdings-date-slider").addEventListener("input", () => updateHoldingsDisplay());
        }
        
        setupHoldingsSlider();
    }
    
    let activeRebalanceDates = [];
    
    function setupHoldingsSlider() {
        const dates = DATA.dates;
        const startDateStr = document.getElementById("custom-start-date").value;
        const endDateStr = document.getElementById("custom-end-date").value;
        
        let startIdx = dates.findIndex(d => d >= startDateStr);
        let endIdx = dates.findIndex(d => d >= endDateStr);
        if (startIdx === -1) startIdx = 0;
        if (endIdx === -1 || endIdx < startIdx) endIdx = dates.length - 1;
        
        activeRebalanceDates = [];
        activeRebalanceDates.push(startIdx);
        
        for (let i = startIdx + 1; i <= endIdx; i++) {
            const d = new Date(dates[i]);
            const prevD = new Date(dates[i - 1]);
            if (d.getMonth() !== prevD.getMonth()) {
                activeRebalanceDates.push(i);
            }
        }
        
        const slider = document.getElementById("holdings-date-slider");
        slider.max = Math.max(0, activeRebalanceDates.length - 1);
        slider.value = 0;
        
        updateHoldingsDisplay();
    }
    
    function updateHoldingsDisplay() {
        const select = document.getElementById("holdings-etf-select");
        const slider = document.getElementById("holdings-date-slider");
        const gridEl = document.getElementById("holdings-grid");
        if (!select || !slider || !gridEl || activeRebalanceDates.length === 0) return;
        
        const pIdx = parseInt(select.value);
        const dateIdx = parseInt(slider.value);
        const dataIdx = activeRebalanceDates[dateIdx];
        
        const dateStr = DATA.dates[dataIdx];
        document.getElementById("holdings-date-display").textContent = dateStr;
        
        const smaState = DATA.indicators.sma_state[dataIdx];
        const score = DATA.indicators.macro_score[dataIdx];
        
        let allocation = [];
        if (pIdx === 0) { // sma_gold
            if (smaState === 100) allocation = [{ ticker: "GOLD", name: "Gold Spot bullion", weight: 1.0, color: COLORS.gold.main }];
            else allocation = [{ ticker: "EQUITY", name: "Equities Composite Index", weight: 1.0, color: COLORS.equity.main }];
        } else if (pIdx === 1) { // sma_treas
            if (smaState === 100) allocation = [{ ticker: "TREASURY", name: "10-Year U.S. Treasury Bond", weight: 1.0, color: COLORS.treasury.main }];
            else allocation = [{ ticker: "EQUITY", name: "Equities Composite Index", weight: 1.0, color: COLORS.equity.main }];
        } else if (pIdx === 2) { // macro_gold
            if (score >= 50.0) allocation = [{ ticker: "GOLD", name: "Gold Spot bullion", weight: 1.0, color: COLORS.gold.main }];
            else allocation = [{ ticker: "EQUITY", name: "Equities Composite Index", weight: 1.0, color: COLORS.equity.main }];
        } else if (pIdx === 3) { // macro_treas
            if (score >= 50.0) allocation = [{ ticker: "TREASURY", name: "10-Year U.S. Treasury Bond", weight: 1.0, color: COLORS.treasury.main }];
            else allocation = [{ ticker: "EQUITY", name: "Equities Composite Index", weight: 1.0, color: COLORS.equity.main }];
        }
        
        gridEl.innerHTML = allocation.map(a => `
            <div class="holding-card" title="${a.name}" style="flex-grow: 1;">
                <div class="holding-card__header">
                    <div class="holding-card__ticker" style="font-weight: 700;">${a.ticker}</div>
                    <div class="holding-card__weight">${(a.weight * 100).toFixed(0)}%</div>
                </div>
                <div class="holding-card__name">${a.name}</div>
                <div class="holding-card__bar" style="background:${a.color}; width:100%;"></div>
            </div>
        `).join('');
    }

    // ================================================================
    // Monthly Returns Heatmap
    // ================================================================
    function getMonthlyReturns(values, dates) {
        const byYear = {};
        const monthlyData = {};
        for (let i = 0; i < dates.length; i++) {
            const d = new Date(dates[i]);
            const yr = d.getFullYear();
            const m = d.getMonth() + 1;
            
            if (!monthlyData[yr]) monthlyData[yr] = {};
            if (!monthlyData[yr][m]) monthlyData[yr][m] = [];
            monthlyData[yr][m].push({ idx: i, val: values[i] });
        }
        
        const years = Object.keys(monthlyData).sort((a,b) => a-b);
        let prevMonthCloseVal = null;
        
        years.forEach(yr => {
            byYear[yr] = {};
            for (let m = 1; m <= 12; m++) {
                const points = monthlyData[yr][m];
                if (!points || points.length === 0) continue;
                
                const endVal = points[points.length - 1].val;
                let startVal = prevMonthCloseVal;
                if (startVal === null) {
                    startVal = points[0].val;
                }
                
                const ret = ((endVal - startVal) / startVal) * 100;
                byYear[yr][m] = ret;
                prevMonthCloseVal = endVal;
            }
        });
        
        return byYear;
    }

    function renderHeatmap() {
        const controlsEl = document.getElementById("heatmap-controls");
        const containerEl = document.getElementById("heatmap-container");
        if (!controlsEl || !containerEl) return;
        
        const items = [
            { name: "Equity Composite", data: DATA.assets.equity },
            { name: "Gold Spot", data: DATA.assets.gold },
            { name: "U.S. Treasuries", data: DATA.assets.treasury },
            { name: "200-SMA Switch (Gold)", data: DATA.portfolios.sma_gold },
            { name: "200-SMA Switch (Treasury)", data: DATA.portfolios.sma_treas },
            { name: "Macro Score (Gold)", data: DATA.portfolios.macro_gold },
            { name: "Macro Score (Treasury)", data: DATA.portfolios.macro_treas }
        ];
        
        if (!controlsEl.innerHTML) {
            const options = items.map((it, i) => `<option value="${i}">${it.name}</option>`).join('');
            const compareOptions = `<option value="-1">None (Absolute Returns)</option>` + options;
            
            controlsEl.innerHTML = `
                <div class="control-group">
                    <label>Select Fund</label>
                    <select id="heatmap-select" style="background:var(--bg-input); border:1px solid var(--border-color); color:#fff; border-radius:6px; padding:6px; outline:none; font-family:'Inter',sans-serif; cursor:pointer;">${options}</select>
                </div>
                <div class="control-group" style="margin-left: 16px;">
                    <label>Compare To</label>
                    <select id="heatmap-compare-select" style="background:var(--bg-input); border:1px solid var(--border-color); color:#fff; border-radius:6px; padding:6px; outline:none; font-family:'Inter',sans-serif; cursor:pointer;">${compareOptions}</select>
                </div>
            `;
            
            document.getElementById("heatmap-select").addEventListener("change", () => renderHeatmapTable());
            document.getElementById("heatmap-compare-select").addEventListener("change", () => renderHeatmapTable());
        }
        
        renderHeatmapTable();
    }
    
    function renderHeatmapTable() {
        const select = document.getElementById("heatmap-select");
        const compareSelect = document.getElementById("heatmap-compare-select");
        const containerEl = document.getElementById("heatmap-container");
        if (!select || !containerEl) return;
        
        const items = [
            { name: "Equity Composite", data: DATA.assets.equity },
            { name: "Gold Spot", data: DATA.assets.gold },
            { name: "U.S. Treasuries", data: DATA.assets.treasury },
            { name: "200-SMA Switch (Gold)", data: DATA.portfolios.sma_gold },
            { name: "200-SMA Switch (Treasury)", data: DATA.portfolios.sma_treas },
            { name: "Macro Score (Gold)", data: DATA.portfolios.macro_gold },
            { name: "Macro Score (Treasury)", data: DATA.portfolios.macro_treas }
        ];
        
        const dates = DATA.dates;
        const startDateStr = document.getElementById("custom-start-date").value;
        const endDateStr = document.getElementById("custom-end-date").value;
        
        let startIdx = dates.findIndex(d => d >= startDateStr);
        let endIdx = dates.findIndex(d => d >= endDateStr);
        if (startIdx === -1) startIdx = 0;
        if (endIdx === -1 || endIdx < startIdx) endIdx = dates.length - 1;
        
        const slicedDates = dates.slice(startIdx, endIdx + 1);
        
        const idx = parseInt(select.value);
        const compareIdx = parseInt(compareSelect.value);
        
        const item = items[idx];
        const slicedVals = item.data.slice(startIdx, endIdx + 1);
        const byYear = getMonthlyReturns(slicedVals, slicedDates);
        
        let compareByYear = null;
        let compareName = "";
        if (compareIdx >= 0) {
            const compItem = items[compareIdx];
            const compVals = compItem.data.slice(startIdx, endIdx + 1);
            compareByYear = getMonthlyReturns(compVals, slicedDates);
            compareName = compItem.name;
        }
        
        const years = Object.keys(byYear).sort((a,b) => b-a);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        
        let maxAbs = 0.1;
        years.forEach(yr => {
            for (let m = 1; m <= 12; m++) {
                const val = byYear[yr][m];
                if (val === undefined) continue;
                
                let diff = val;
                if (compareByYear && compareByYear[yr][m] !== undefined) {
                    diff = val - compareByYear[yr][m];
                }
                if (Math.abs(diff) > maxAbs) maxAbs = Math.abs(diff);
            }
        });
        
        let html = '<table class="heatmap-table"><thead><tr><th>Year</th>';
        months.forEach(m => html += `<th>${m}</th>`);
        html += '<th>Annual</th>';
        html += '</tr></thead><tbody>';
        
        years.forEach(year => {
            html += `<tr><td style="font-weight:700;">${year}</td>`;
            let annualRetMult = 1.0;
            let compAnnualRetMult = 1.0;
            let hasData = false;
            
            months.forEach((mStr, mi) => {
                const mNum = mi + 1;
                const val = byYear[year][mNum];
                
                if (val !== undefined) {
                    hasData = true;
                    annualRetMult *= (1 + val / 100);
                    
                    let diff = val;
                    let titleText = `${mStr} ${year}: ${val.toFixed(2)}%`;
                    
                    if (compareByYear && compareByYear[year][mNum] !== undefined) {
                        const cVal = compareByYear[year][mNum];
                        compAnnualRetMult *= (1 + cVal / 100);
                        diff = val - cVal;
                        titleText = `${mStr} ${year}:\n${item.name}: ${val.toFixed(2)}%\n${compareName}: ${cVal.toFixed(2)}%\nDiff: ${diff.toFixed(2)}%`;
                    }
                    
                    const intensity = Math.min(Math.abs(diff) / maxAbs, 1);
                    const bg = diff >= 0
                        ? `rgba(16, 185, 129, ${0.1 + intensity * 0.6})`
                        : `rgba(239, 68, 68, ${0.1 + intensity * 0.6})`;
                    const textColor = intensity > 0.5 ? '#fff' : (diff >= 0 ? '#10b981' : '#ef4444');
                    
                    html += `<td style="background:${bg};color:${textColor}" title="${titleText}">${diff.toFixed(1)}%</td>`;
                } else {
                    html += '<td style="color:var(--text-muted)">—</td>';
                }
            });
            
            if (hasData) {
                const annVal = (annualRetMult - 1) * 100;
                let diffAnn = annVal;
                let titleText = `Annual ${year}: ${annVal.toFixed(2)}%`;
                
                if (compareByYear) {
                    const compAnn = (compAnnualRetMult - 1) * 100;
                    diffAnn = annVal - compAnn;
                    titleText = `Annual ${year}:\n${item.name}: ${annVal.toFixed(2)}%\n${compareName}: ${compAnn.toFixed(2)}%\nDiff: ${diffAnn.toFixed(2)}%`;
                }
                
                const aColor = diffAnn >= 0 ? '#10b981' : '#ef4444';
                html += `<td style="color:${aColor};font-weight:700" title="${titleText}">${diffAnn.toFixed(1)}%</td>`;
            } else {
                html += '<td style="color:var(--text-muted)">—</td>';
            }
            html += '</tr>';
        });
        
        html += '</tbody></table>';
        containerEl.innerHTML = html;
    }

    // ================================================================
    // Performance Summary Cards
    // ================================================================
    function renderMetrics() {
        const grid = document.getElementById("metrics-grid");
        const filterSelect = document.getElementById("metrics-filter-select");
        if (!grid || !filterSelect) return;
        
        const items = [
            { name: "Equity Composite", data: DATA.assets.equity },
            { name: "Gold Spot", data: DATA.assets.gold },
            { name: "U.S. Treasuries", data: DATA.assets.treasury },
            { name: "200-SMA Switch (Gold)", data: DATA.portfolios.sma_gold },
            { name: "200-SMA Switch (Treasury)", data: DATA.portfolios.sma_treas },
            { name: "Macro Score (Gold)", data: DATA.portfolios.macro_gold },
            { name: "Macro Score (Treasury)", data: DATA.portfolios.macro_treas }
        ];
        
        const idx = parseInt(filterSelect.value);
        const item = items[idx];
        
        const dates = DATA.dates;
        const startDateStr = document.getElementById("custom-start-date").value;
        const endDateStr = document.getElementById("custom-end-date").value;
        
        let startIdx = dates.findIndex(d => d >= startDateStr);
        let endIdx = dates.findIndex(d => d >= endDateStr);
        if (startIdx === -1) startIdx = 0;
        if (endIdx === -1 || endIdx < startIdx) endIdx = dates.length - 1;
        
        const slicedVals = item.data.slice(startIdx, endIdx + 1);
        const startVal = slicedVals[0];
        const endVal = slicedVals[slicedVals.length - 1];
        
        const totalRet = ((endVal - startVal) / startVal) * 100;
        const days = (new Date(dates[endIdx]) - new Date(dates[startIdx])) / (1000 * 60 * 60 * 24);
        const annRet = days > 30 ? (Math.pow(endVal / startVal, 365.25 / days) - 1) * 100 : 0;
        
        let maxDD = 0;
        let peak = -Infinity;
        for (let i = 0; i < slicedVals.length; i++) {
            if (slicedVals[i] > peak) peak = slicedVals[i];
            const dd = ((slicedVals[i] - peak) / peak) * 100;
            if (dd < maxDD) maxDD = dd;
        }
        
        const dailyRets = [];
        for (let i = 1; i < slicedVals.length; i++) {
            dailyRets.push((slicedVals[i] - slicedVals[i - 1]) / slicedVals[i - 1]);
        }
        let sharpe = 0;
        let volatility = 0;
        if (dailyRets.length > 10) {
            const mean = dailyRets.reduce((a, b) => a + b, 0) / dailyRets.length;
            const variance = dailyRets.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (dailyRets.length - 1);
            const dailyStd = Math.sqrt(variance);
            const annStd = dailyStd * Math.sqrt(252);
            volatility = annStd * 100;
            const excess = annRet - 4.0;
            sharpe = volatility > 0.001 ? excess / volatility : 0;
        }
        
        grid.innerHTML = `
            ${metricCard('Total Return', `${totalRet.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}%`, item.name, totalRet >= 0)}
            ${metricCard('Annualized Return', `${annRet.toFixed(2)}%`, 'CAGR over selected period', annRet >= 0)}
            ${metricCard('Max Drawdown', `${maxDD.toFixed(2)}%`, 'Worst peak-to-trough decline', false)}
            ${metricCard('Sharpe Ratio', sharpe.toFixed(2), 'Risk-adjusted return (4% RF)', sharpe >= 0)}
            ${metricCard('Volatility', `${volatility.toFixed(2)}%`, 'Annualized variance', null)}
            ${metricCard('Rebalance Freq', 'Monthly', 'Tactical asset rotation', null)}
        `;
    }
    
    function metricCard(label, value, subtitle, positive) {
        const cls = positive === null ? 'neutral' : (positive ? 'positive' : 'negative');
        return `
            <div class="metric-card metric-card--${cls}">
                <div class="metric-card__label">${label}</div>
                <div class="metric-card__value">${value}</div>
                <div class="metric-card__subtitle">${subtitle}</div>
            </div>`;
    }
