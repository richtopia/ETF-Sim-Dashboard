/**
 * Risk KPI Dashboard - Application Logic
 * Loads risk_kpi.json and renders interactive risk component chart.
 */

let RAW_DATA = null;
let riskChart = null;

// Color mapping for lines
const LINE_STYLES = [
    { key: "composite", label: "Consolidated Risk Score", color: "#ec4899", width: 3.5, active: true },
    { key: "fed", label: "Fed Funds 12M Change", color: "#8b5cf6", width: 2, active: false },
    { key: "move", label: "MOVE Index (Bonds)", color: "#6366f1", width: 2, active: false },
    { key: "trend", label: "Trend Momentum (SMA)", color: "#a1a1aa", width: 2, active: false },
    { key: "yield", label: "Yield Curve Inversion", color: "#f59e0b", width: 2, active: false },
    { key: "sahm", label: "Sahm Rule (Labor)", color: "#10b981", width: 2, active: false },
    { key: "oil", label: "Oil Price Shock", color: "#06b6d4", width: 2, active: false },
    { key: "spy", label: "S&P 500 Index (RHS)", color: "rgba(255, 255, 255, 0.45)", width: 1.5, active: true, yAxisID: "y2" }
];

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const response = await fetch("risk_kpi.json");
        RAW_DATA = await response.json();
        
        initializeUI();
        renderChart();
        renderStatsBar();
    } catch (err) {
        console.error("Failed to load Risk KPI data:", err);
    }
});

function initializeUI() {
    // Generate Visibility Toggle Cards
    const container = document.getElementById("kpi-toggles-container");
    container.innerHTML = LINE_STYLES.map((style, idx) => {
        return `
            <div class="kpi-toggle-item">
                <div class="kpi-toggle-left">
                    <span class="kpi-color-pill" style="background:${style.color}; color:${style.color}"></span>
                    <span class="kpi-label">${style.label}</span>
                </div>
                <input type="checkbox" class="kpi-checkbox" id="toggle-${style.key}" ${style.active ? "checked" : ""} data-idx="${idx}">
            </div>
        `;
    }).join("");

    // Wire toggle listeners
    LINE_STYLES.forEach((style, idx) => {
        const checkbox = document.getElementById(`toggle-${style.key}`);
        checkbox.addEventListener("change", (e) => {
            LINE_STYLES[idx].active = e.target.checked;
            if (riskChart) {
                riskChart.setDatasetVisibility(idx, e.target.checked);
                riskChart.update();
            }
        });
    });

    // Wire Date Picker Inputs
    const startInput = document.getElementById("kpi-start-date");
    const endInput = document.getElementById("kpi-end-date");

    const firstDate = RAW_DATA.dates[0];
    const lastDate = RAW_DATA.dates[RAW_DATA.dates.length - 1];

    startInput.min = firstDate;
    startInput.max = lastDate;
    endInput.min = firstDate;
    endInput.max = lastDate;

    startInput.value = firstDate;
    endInput.value = lastDate;

    const onDateChange = () => {
        const startVal = startInput.value;
        const endVal = endInput.value;
        
        // Remove active class from presets
        document.querySelectorAll(".preset-btn").forEach(btn => btn.classList.remove("active"));
        
        updateChartData(startVal, endVal);
    };

    startInput.addEventListener("change", onDateChange);
    endInput.addEventListener("change", onDateChange);

    // Wire Preset buttons
    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const start = e.target.dataset.start;
            const end = e.target.dataset.end;

            if (start && end) {
                document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
                e.target.classList.add("active");
                
                startInput.value = start;
                endInput.value = end;
                updateChartData(start, end);
            }
        });
    });

    // Reset button
    document.getElementById("kpi-reset-range").addEventListener("click", (e) => {
        document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
        e.target.classList.add("active");

        const firstDate = RAW_DATA.dates[0];
        const lastDate = RAW_DATA.dates[RAW_DATA.dates.length - 1];

        startInput.value = firstDate;
        endInput.value = lastDate;
        updateChartData(firstDate, lastDate);
    });
}

function downsampleTimeseries(dates, values, maxPoints = 600) {
    if (dates.length <= maxPoints) {
        return dates.map((d, i) => ({ x: new Date(d), y: values[i] }));
    }
    const step = Math.ceil(dates.length / maxPoints);
    const downsampled = [];
    for (let i = 0; i < dates.length; i += step) {
        downsampled.push({ x: new Date(dates[i]), y: values[i] });
    }
    if ((dates.length - 1) % step !== 0) {
        downsampled.push({ x: new Date(dates[dates.length - 1]), y: values[dates.length - 1] });
    }
    return downsampled;
}

function getFilteredData(startDateStr, endDateStr) {
    const start = new Date(startDateStr);
    const end = new Date(endDateStr);

    const filteredDates = [];
    const indices = [];

    RAW_DATA.dates.forEach((dateStr, idx) => {
        const d = new Date(dateStr);
        if (d >= start && d <= end) {
            filteredDates.push(dateStr);
            indices.push(idx);
        }
    });

    const datasetMap = {
        composite: [],
        sahm: [],
        move: [],
        trend: [],
        yield: [],
        fed: [],
        oil: [],
        spy: []
    };

    indices.forEach(idx => {
        datasetMap.composite.push(RAW_DATA.composite[idx]);
        datasetMap.sahm.push(RAW_DATA.components.sahm[idx]);
        datasetMap.move.push(RAW_DATA.components.move[idx]);
        datasetMap.trend.push(RAW_DATA.components.trend[idx]);
        datasetMap.yield.push(RAW_DATA.components.yield[idx]);
        datasetMap.fed.push(RAW_DATA.components.fed[idx]);
        datasetMap.oil.push(RAW_DATA.components.oil[idx]);
        datasetMap.spy.push(RAW_DATA.raw.spy[idx]);
    });

    return { dates: filteredDates, datasetMap };
}

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

function renderChart() {
    const ctx = document.getElementById("risk-chart").getContext("2d");
    const startVal = document.getElementById("kpi-start-date").value;
    const endVal = document.getElementById("kpi-end-date").value;

    const { dates, datasetMap } = getFilteredData(startVal, endVal);

    const datasets = LINE_STYLES.map(style => {
        const fullValues = datasetMap[style.key];
        const downsampled = downsampleTimeseries(dates, fullValues);
        
        return {
            label: style.label,
            data: downsampled,
            borderColor: style.color,
            borderWidth: style.width,
            pointRadius: 0,
            pointHitRadius: 8,
            fill: false,
            tension: 0.1,
            hidden: !style.active,
            yAxisID: style.yAxisID || "y"
        };
    });

    riskChart = new Chart(ctx, {
        type: "line",
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: "time",
                    time: {
                        unit: "month",
                        displayFormats: { month: "MMM yyyy" }
                    },
                    grid: { color: "rgba(255, 255, 255, 0.04)" },
                    ticks: { color: "#8888a8" }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: "rgba(255, 255, 255, 0.04)" },
                    ticks: { color: "#8888a8" },
                    title: {
                        display: true,
                        text: "Normalised Risk Value (0 - 100)",
                        color: "#8888a8"
                    }
                },
                y2: {
                    position: "right",
                    grid: { drawOnChartArea: false },
                    ticks: { color: "#8888a8" },
                    title: {
                        display: true,
                        text: "S&P 500 Index ($)",
                        color: "#8888a8"
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    mode: "index",
                    intersect: false,
                    backgroundColor: "rgba(13, 13, 26, 0.95)",
                    titleColor: "#ffffff",
                    bodyColor: "#8888a8",
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderWidth: 1,
                    padding: 12,
                    callbacks: {
                        label: function(context) {
                            return ` ${context.dataset.label}: ${context.raw.y.toFixed(1)}`;
                        }
                    }
                }
            }
        },
        plugins: [recessionBandsPlugin]
    });

    document.getElementById("kpi-meta-period").textContent = `${startVal} to ${endVal}`;
}

function updateChartData(startDateStr, endDateStr) {
    if (!riskChart) return;

    const { dates, datasetMap } = getFilteredData(startDateStr, endDateStr);

    LINE_STYLES.forEach((style, idx) => {
        const fullValues = datasetMap[style.key];
        riskChart.data.datasets[idx].data = downsampleTimeseries(dates, fullValues);
    });

    riskChart.update();
    document.getElementById("kpi-meta-period").textContent = `${startDateStr} to ${endDateStr}`;
}

function renderStatsBar() {
    const latestIdx = RAW_DATA.dates.length - 1;
    const latestDate = RAW_DATA.dates[latestIdx];

    const statsConfig = [
        { label: "Consolidated Risk", val: RAW_DATA.composite[latestIdx], color: "#ec4899", suffix: "", weight: "100%" },
        { label: "Fed Funds (12M Δ)", val: RAW_DATA.components.fed[latestIdx], color: "#8b5cf6", suffix: "", weight: "20% wt" },
        { label: "MOVE Index", val: RAW_DATA.components.move[latestIdx], color: "#6366f1", suffix: "", weight: "20% wt" },
        { label: "Trend (vs SMA)", val: RAW_DATA.components.trend[latestIdx], color: "#a1a1aa", suffix: "", weight: "20% wt" },
        { label: "Yield Inversion", val: RAW_DATA.components.yield[latestIdx], color: "#f59e0b", suffix: "", weight: "15% wt" },
        { label: "Sahm Rule", val: RAW_DATA.components.sahm[latestIdx], color: "#10b981", suffix: "", weight: "15% wt" },
        { label: "Oil Price Shock", val: RAW_DATA.components.oil[latestIdx], color: "#06b6d4", suffix: "", weight: "10% wt" },
        { label: "S&P 500 Price", val: RAW_DATA.raw.spy[latestIdx], color: "#ffffff", suffix: "$", weight: "RHS Index" }
    ];

    const statsBar = document.getElementById("kpi-stats-bar");
    
    let cardsHtml = `
        <div class="kpi-stat-card" style="border-left-color: #64748b;">
            <div class="kpi-stat-card__label" title="As of Date">As of Date</div>
            <div class="kpi-stat-card__value" style="font-size: 1.15rem; margin-top: 5px; color: var(--text-bright);">${latestDate}</div>
            <div class="kpi-stat-card__weight">Latest Trading Day</div>
        </div>
    `;

    cardsHtml += statsConfig.map(c => {
        const displayVal = c.suffix === "$" ? `$${c.val.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})}` : c.val.toFixed(1);
        return `
            <div class="kpi-stat-card" style="border-left-color: ${c.color}">
                <div class="kpi-stat-card__label" title="${c.label}">${c.label}</div>
                <div class="kpi-stat-card__value">${displayVal}</div>
                <div class="kpi-stat-card__weight">${c.weight}</div>
            </div>
        `;
    }).join("");

    statsBar.innerHTML = cardsHtml;

    const headerSub = document.querySelector(".header__subtitle");
    headerSub.innerHTML = `Consolidated Macro-Financial Risk Scoreboard — Current Landscape as of <strong>${latestDate}</strong>`;
}
