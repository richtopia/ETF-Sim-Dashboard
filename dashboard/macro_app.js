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
            const startInput = document.getElementById("start-date-input");
            const endInput = document.getElementById("end-date-input");
            
            startInput.value = dates[0];
            startInput.min = dates[0];
            startInput.max = dates[dates.length - 1];
            
            endInput.value = dates[dates.length - 1];
            endInput.min = dates[0];
            endInput.max = dates[dates.length - 1];
            
            // Event listeners
            const presetBtns = document.querySelectorAll(".preset-btn");
            
            function clearPresetActiveStates() {
                presetBtns.forEach(b => b.classList.remove("preset-btn--active"));
            }

            startInput.addEventListener("change", () => {
                clearPresetActiveStates();
                updateDashboard();
            });
            endInput.addEventListener("change", () => {
                clearPresetActiveStates();
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
        const startDateStr = document.getElementById("start-date-input").value;
        const endDateStr = document.getElementById("end-date-input").value;
        
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
            const startDateStr = document.getElementById("start-date-input").value;
            const endDateStr = document.getElementById("end-date-input").value;
            
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
                
                // Normalize sliced values to start at 100 on start date for clean comparison
                const normVal = slicedVals[0];
                const normalizedVals = slicedVals.map(v => (v / normVal) * 100);
                
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
                                return value.toLocaleString() + '%';
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
