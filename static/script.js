/* =========================================================
   LEVEL 1000 AI
   PUBLIC / OPEN MODE
   FAST FRONTEND
   ========================================================= */

"use strict";

const API_BASE = "";

const DISPLAY_LIMIT = 300;
const PAGE_SIZE = 50;

let allSignals = [];
let filteredSignals = [];
let currentPage = 1;

let runPollTimer = null;
let refreshTimer = null;
let isLoadingSignals = false;


/* =========================================================
   API
   ========================================================= */

async function publicFetch(url, options = {}) {
    const config = {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {})
        }
    };

    return fetch(API_BASE + url, config);
}


async function readJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}


/* =========================================================
   HELPERS
   ========================================================= */

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}


function setHTML(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function escapeJs(value) {
    return String(value ?? "")
        .replaceAll("\\", "\\\\")
        .replaceAll("'", "\\'")
        .replaceAll("\n", "\\n")
        .replaceAll("\r", "\\r");
}


function formatNumber(value, digits = 2) {
    if (
        value === null ||
        value === undefined ||
        value === "" ||
        Number.isNaN(Number(value))
    ) {
        return "-";
    }

    return Number(value).toLocaleString("tr-TR", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
    });
}


function formatPercent(value) {
    if (
        value === null ||
        value === undefined ||
        value === "" ||
        Number.isNaN(Number(value))
    ) {
        return "-";
    }

    let n = Number(value);

    if (Math.abs(n) <= 1) {
        n *= 100;
    }

    return `${n.toFixed(2)}%`;
}


function signalClass(signal) {
    signal = String(signal || "").toUpperCase();

    if (signal === "BUY" || signal === "AL") {
        return "buy";
    }

    if (signal === "SELL" || signal === "SAT") {
        return "sell";
    }

    return "hold";
}


function normalizeSignal(row) {
    let signal =
        row.signal ??
        row.Signal ??
        row.action ??
        row.Action ??
        row.sinyal ??
        row.Sinyal ??
        "HOLD";

    signal = String(signal).toUpperCase();

    if (signal === "AL") signal = "BUY";
    if (signal === "SAT") signal = "SELL";
    if (signal === "BEKLE") signal = "HOLD";

    return {
        symbol:
            row.symbol ??
            row.Symbol ??
            row.ticker ??
            row.Ticker ??
            "-",

        signal,

        score:
            row.score ??
            row.Score ??
            row.ai_probability ??
            row.AI_Probability ??
            0,

        price:
            row.price ??
            row.Price ??
            row.close ??
            row.Close ??
            null,

        predictedReturn:
            row.predicted_return ??
            row.Predicted_Return ??
            row.ai_predicted_return ??
            row.AI_Predicted_Return ??
            row.expected_return ??
            row.Expected_Return ??
            null,

        change:
            row.change ??
            row.Change ??
            row.daily_change_percent ??
            row.Daily_Change_Percent ??
            null,

        priceStatus:
            row.price_status ??
            row.Price_Status ??
            "",

        priceSource:
            row.price_source ??
            row.Price_Source ??
            "",

        date:
            row.date ??
            row.Date ??
            ""
    };
}


/* =========================================================
   TOAST
   ========================================================= */

function showToast(message, type = "info") {
    const old = document.querySelector(".level-toast");

    if (old) {
        old.remove();
    }

    const toast = document.createElement("div");

    toast.className = `level-toast ${type}`;
    toast.textContent = message;

    Object.assign(toast.style, {
        position: "fixed",
        right: "20px",
        bottom: "20px",
        zIndex: "999999",
        padding: "13px 18px",
        borderRadius: "12px",
        background: "#ffffff",
        color: "#111827",
        border: "1px solid #e5e7eb",
        boxShadow: "0 10px 35px rgba(0,0,0,.18)",
        fontSize: "14px",
        fontWeight: "600",
        maxWidth: "380px"
    });

    document.body.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 3500);
}


/* =========================================================
   PUBLIC SESSION
   ========================================================= */

async function checkSession() {
    showAppScreen();
    return true;
}


function showAppScreen() {
    const auth = document.getElementById("authScreen");
    const app = document.getElementById("appScreen");

    if (auth) {
        auth.style.display = "none";
    }

    if (app) {
        app.style.display = "block";
    }
}


function showAuthScreen() {
    showAppScreen();
}


function requirePlan() {
    return true;
}


function selectPlan() {
    return true;
}


async function loadPlan() {
    setText("userPlan", "OPEN");
    setText("planName", "OPEN");

    return {
        ok: true,
        plan: "OPEN",
        plan_level: 999999
    };
}


/* =========================================================
   SIGNAL DATA
   ========================================================= */

async function loadSignals() {

    if (isLoadingSignals) {
        return;
    }

    isLoadingSignals = true;

    showTableLoading();

    try {

        const response = await publicFetch("/api/signals");

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await readJson(response);

        if (!data || !Array.isArray(data.signals)) {
            throw new Error("Sinyal verisi bulunamadı.");
        }

        /*
         * ÖNEMLİ:
         * 166.200 kayıt bellekte tutulabilir.
         * Ancak HTML'e sadece gerekli sayfa basılır.
         */

        allSignals = data.signals;

        updateKPIsFromAPI(data);

        filteredSignals = allSignals;

        currentPage = 1;

        renderCurrentPage();

        setText(
            "signalUpdated",
            data.updated_at ||
            data.last_update ||
            new Date().toLocaleString("tr-TR")
        );

        setText(
            "totalSignalInfo",
            `${allSignals.length.toLocaleString("tr-TR")} sinyal`
        );

        return data;

    } catch (error) {

        console.error("Signals:", error);

        showTableError(
            "Sinyal verileri yüklenemedi."
        );

        return null;

    } finally {

        isLoadingSignals = false;
    }
}


/* =========================================================
   KPI
   ========================================================= */

function updateKPIsFromAPI(data) {

    const buy = Number(data.buy || 0);
    const sell = Number(data.sell || 0);
    const hold = Number(data.hold || 0);
    const total = Number(data.total || allSignals.length || 0);

    setText(
        "buyCount",
        buy.toLocaleString("tr-TR")
    );

    setText(
        "sellCount",
        sell.toLocaleString("tr-TR")
    );

    setText(
        "holdCount",
        hold.toLocaleString("tr-TR")
    );

    setText(
        "topCount",
        Math.min(20, total).toLocaleString("tr-TR")
    );

    setText(
        "totalCount",
        total.toLocaleString("tr-TR")
    );

    setText(
        "signalCount",
        total.toLocaleString("tr-TR")
    );
}


function updateKPIsFromFilteredData() {

    let buy = 0;
    let sell = 0;
    let hold = 0;

    for (const row of filteredSignals) {

        const signal = normalizeSignal(row).signal;

        if (signal === "BUY") {
            buy++;
        } else if (signal === "SELL") {
            sell++;
        } else {
            hold++;
        }
    }

    setText("buyCount", buy.toLocaleString("tr-TR"));
    setText("sellCount", sell.toLocaleString("tr-TR"));
    setText("holdCount", hold.toLocaleString("tr-TR"));
}


/* =========================================================
   TABLE LOADING
   ========================================================= */

function getTableBody() {

    return (
        document.getElementById("signalsTableBody") ||
        document.querySelector("#signalsTable tbody")
    );
}


function showTableLoading() {

    const tbody = getTableBody();

    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="20" style="
                text-align:center;
                padding:45px 20px;
            ">
                <div style="
                    font-size:30px;
                    margin-bottom:10px;
                ">⏳</div>

                <strong>Veriler yükleniyor...</strong>

                <div style="
                    margin-top:8px;
                    opacity:.7;
                ">
                    Sinyal motorundan veriler alınıyor.
                </div>
            </td>
        </tr>
    `;
}


function showTableError(message) {

    const tbody = getTableBody();

    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="20" style="
                text-align:center;
                padding:40px;
            ">
                <strong>${escapeHtml(message)}</strong>

                <div style="
                    margin-top:8px;
                    opacity:.7;
                ">
                    Sayfayı yenileyerek tekrar deneyin.
                </div>
            </td>
        </tr>
    `;
}


/* =========================================================
   FILTER
   ========================================================= */

let activeSignalFilter = "ALL";


function filterSignals() {

    const input =
        document.getElementById("signalSearch") ||
        document.getElementById("searchInput");

    const query =
        input ?
        input.value.trim().toLowerCase() :
        "";

    filteredSignals = allSignals.filter(row => {

        const s = normalizeSignal(row);

        const matchesSearch =
            !query ||
            String(s.symbol)
                .toLowerCase()
                .includes(query);

        const matchesFilter =
            activeSignalFilter === "ALL" ||
            s.signal === activeSignalFilter;

        return matchesSearch && matchesFilter;
    });

    currentPage = 1;

    updateKPIsFromFilteredData();

    renderCurrentPage();
}


function searchSignals() {
    filterSignals();
}


function setSignalFilter(filter) {

    activeSignalFilter = String(filter || "ALL").toUpperCase();

    document
        .querySelectorAll("[data-signal-filter]")
        .forEach(button => {

            const value =
                String(
                    button.dataset.signalFilter || "ALL"
                ).toUpperCase();

            button.classList.toggle(
                "active",
                value === activeSignalFilter
            );
        });

    filterSignals();
}


/* =========================================================
   PAGINATION
   ========================================================= */

function getPageCount() {

    return Math.max(
        1,
        Math.ceil(
            filteredSignals.length / PAGE_SIZE
        )
    );
}


function getPageRows() {

    const start =
        (currentPage - 1) * PAGE_SIZE;

    return filteredSignals.slice(
        start,
        start + PAGE_SIZE
    );
}


function changePage(page) {

    const maxPage = getPageCount();

    page = Number(page);

    if (!Number.isFinite(page)) {
        return;
    }

    page = Math.max(
        1,
        Math.min(maxPage, page)
    );

    currentPage = page;

    renderCurrentPage();

    const table =
        document.getElementById("signalsTable");

    if (table) {
        table.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }
}


/* =========================================================
   RENDER
   ========================================================= */

function renderCurrentPage() {

    const tbody = getTableBody();

    if (!tbody) return;

    const rows = getPageRows();

    if (!rows.length) {

        tbody.innerHTML = `
            <tr>
                <td colspan="20" style="
                    text-align:center;
                    padding:40px;
                ">
                    Sonuç bulunamadı.
                </td>
            </tr>
        `;

        renderPagination();

        return;
    }

    /*
     * SADECE 50 SATIR DOM'A BASILIYOR.
     * 166.200 satır asla DOM'a basılmıyor.
     */

    tbody.innerHTML = rows.map((row, index) => {

        const s = normalizeSignal(row);

        const globalIndex =
            (currentPage - 1) * PAGE_SIZE +
            index +
            1;

        const cls = signalClass(s.signal);

        return `
            <tr data-ticker="${escapeHtml(s.symbol)}">

                <td>
                    ${globalIndex}
                </td>

                <td>
                    <strong>
                        ${escapeHtml(s.symbol)}
                    </strong>
                </td>

                <td>
                    <span class="signal-badge ${cls}">
                        ${escapeHtml(s.signal)}
                    </span>
                </td>

                <td>
                    <strong>
                        ${formatPercent(s.score)}
                    </strong>
                </td>

                <td>
                    ${formatPercent(s.predictedReturn)}
                </td>

                <td>
                    ${formatNumber(s.price)}
                </td>

                <td>
                    ${formatPercent(s.change)}
                </td>

                <td>
                    ${
                        s.priceStatus
                            ? escapeHtml(s.priceStatus)
                            : "-"
                    }
                </td>

                <td>
                    ${escapeHtml(s.date)}
                </td>

                <td>
                    <button
                        type="button"
                        class="signal-detail-btn"
                        onclick="openSignal('${escapeJs(s.symbol)}')"
                    >
                        Detay
                    </button>
                </td>

            </tr>
        `;

    }).join("");

    renderPagination();
}


/* =========================================================
   PAGINATION UI
   ========================================================= */

function renderPagination() {

    let container =
        document.getElementById("signalsPagination");

    if (!container) {

        const table =
            document.getElementById("signalsTable");

        if (!table) return;

        container =
            document.createElement("div");

        container.id =
            "signalsPagination";

        container.style.cssText = `
            display:flex;
            align-items:center;
            justify-content:center;
            gap:8px;
            flex-wrap:wrap;
            margin:18px 0 8px;
        `;

        table.parentNode.appendChild(container);
    }

    const pages = getPageCount();

    if (pages <= 1) {

        container.innerHTML = `
            <span style="opacity:.7;font-size:13px;">
                ${filteredSignals.length.toLocaleString("tr-TR")} sonuç
            </span>
        `;

        return;
    }

    const buttons = [];

    buttons.push(`
        <button
            type="button"
            class="pagination-btn"
            onclick="changePage(${currentPage - 1})"
            ${currentPage <= 1 ? "disabled" : ""}
        >
            ‹
        </button>
    `);

    let start = Math.max(
        1,
        currentPage - 2
    );

    let end = Math.min(
        pages,
        currentPage + 2
    );

    if (start > 1) {

        buttons.push(`
            <button
                type="button"
                class="pagination-btn"
                onclick="changePage(1)"
            >
                1
            </button>
        `);

        if (start > 2) {
            buttons.push(`<span>…</span>`);
        }
    }

    for (let i = start; i <= end; i++) {

        buttons.push(`
            <button
                type="button"
                class="pagination-btn ${i === currentPage ? "active" : ""}"
                onclick="changePage(${i})"
            >
                ${i}
            </button>
        `);
    }

    if (end < pages) {

        if (end < pages - 1) {
            buttons.push(`<span>…</span>`);
        }

        buttons.push(`
            <button
                type="button"
                class="pagination-btn"
                onclick="changePage(${pages})"
            >
                ${pages}
            </button>
        `);
    }

    buttons.push(`
        <button
            type="button"
            class="pagination-btn"
            onclick="changePage(${currentPage + 1})"
            ${currentPage >= pages ? "disabled" : ""}
        >
            ›
        </button>
    `);

    container.innerHTML = buttons.join("");

    const info = document.createElement("div");

    info.style.cssText = `
        width:100%;
        text-align:center;
        margin-top:5px;
        font-size:12px;
        opacity:.65;
    `;

    const startItem =
        filteredSignals.length
            ? ((currentPage - 1) * PAGE_SIZE) + 1
            : 0;

    const endItem =
        Math.min(
            currentPage * PAGE_SIZE,
            filteredSignals.length
        );

    info.textContent =
        `${startItem.toLocaleString("tr-TR")} - ${endItem.toLocaleString("tr-TR")} / ${filteredSignals.length.toLocaleString("tr-TR")}`;

    container.appendChild(info);
}


/* =========================================================
   MAIN REFRESH
   ========================================================= */

async function refreshData() {

    try {

        await Promise.all([
            loadSignals(),
            loadStatus()
        ]);

    } catch (error) {

        console.error(
            "Refresh:",
            error
        );
    }
}


/* =========================================================
   STATUS
   ========================================================= */

async function loadStatus() {

    try {

        const response =
            await publicFetch("/api/status");

        if (!response.ok) {
            return null;
        }

        const data =
            await readJson(response);

        const running =
            data.running === true ||
            data.status === "running";

        setText(
            "systemStatus",
            running
                ? "ANALİZ ÇALIŞIYOR"
                : "HAZIR"
        );

        if (data.last_update) {
            setText(
                "lastUpdate",
                data.last_update
            );
        }

        if (data.updated_at) {
            setText(
                "lastUpdate",
                data.updated_at
            );
        }

        return data;

    } catch (error) {

        console.error(
            "Status:",
            error
        );

        setText(
            "systemStatus",
            "BAĞLANTI BEKLENİYOR"
        );

        return null;
    }
}


/* =========================================================
   RUN ANALYSIS
   ========================================================= */

async function runAnalysis() {

    const buttons =
        document.querySelectorAll(
            "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
        );

    buttons.forEach(button => {

        button.disabled = true;

        button.dataset.oldText =
            button.textContent;

        button.textContent =
            "Analiz Başlatılıyor...";
    });

    try {

        const response =
            await publicFetch(
                "/api/run",
                {
                    method: "POST",
                    body: JSON.stringify({})
                }
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        showToast(
            data.message ||
            "Analiz başlatıldı.",
            "success"
        );

        monitorRun();

    } catch (error) {

        console.error(
            "Run:",
            error
        );

        showToast(
            error.message ||
            "Analiz başlatılamadı.",
            "error"
        );

        buttons.forEach(button => {

            button.disabled = false;

            button.textContent =
                button.dataset.oldText ||
                "Analizi Başlat";
        });
    }
}


/* =========================================================
   RUN MONITOR
   ========================================================= */

async function monitorRun() {

    if (runPollTimer) {
        clearInterval(runPollTimer);
    }

    let attempts = 0;

    async function check() {

        attempts++;

        try {

            const response =
                await publicFetch(
                    "/api/run-status"
                );

            const data =
                await readJson(response);

            const running =
                data.running === true ||
                data.status === "running";

            if (running) {

                setText(
                    "systemStatus",
                    "ANALİZ ÇALIŞIYOR"
                );

                if (data.message) {

                    setText(
                        "analysisProgress",
                        data.message
                    );
                }

                return;
            }

            clearInterval(
                runPollTimer
            );

            runPollTimer = null;

            setText(
                "systemStatus",
                "HAZIR"
            );

            const buttons =
                document.querySelectorAll(
                    "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
                );

            buttons.forEach(button => {

                button.disabled = false;

                button.textContent =
                    button.dataset.oldText ||
                    "Analizi Başlat";
            });

            await loadSignals();

            showToast(
                data.error
                    ? data.error
                    : "Analiz tamamlandı.",
                data.error
                    ? "error"
                    : "success"
            );

        } catch (error) {

            console.error(
                "Run status:",
                error
            );

            if (attempts >= 10) {

                clearInterval(
                    runPollTimer
                );

                runPollTimer = null;

                const buttons =
                    document.querySelectorAll(
                        "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
                    );

                buttons.forEach(button => {

                    button.disabled = false;

                    button.textContent =
                        button.dataset.oldText ||
                        "Analizi Başlat";
                });
            }
        }
    }

    await check();

    runPollTimer =
        setInterval(
            check,
            3000
        );
}


/* =========================================================
   SINGLE SIGNAL
   ========================================================= */

async function openSignal(ticker) {

    if (!ticker) return;

    try {

        const response =
            await publicFetch(
                `/api/signal/${encodeURIComponent(ticker)}`
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            `${ticker} Analizi`,
            data
        );

        const section =
            document.getElementById(
                "advancedResults"
            ) ||
            document.getElementById(
                "advancedResult"
            );

        if (section) {

            section.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }

    } catch (error) {

        console.error(
            "Signal:",
            error
        );

        showToast(
            `${ticker} detay verisi alınamadı.`,
            "error"
        );
    }
}


/* =========================================================
   BACKTEST
   ========================================================= */

async function loadBacktest() {

    renderAdvancedResult(
        "Backtest",
        {
            loading: "Backtest çalıştırılıyor..."
        }
    );

    try {

        const response =
            await publicFetch(
                "/api/backtest"
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Backtest Sonucu",
            data
        );

        return data;

    } catch (error) {

        renderAdvancedResult(
            "Backtest",
            {
                error: error.message
            }
        );

        return null;
    }
}


/* =========================================================
   PAPER
   ========================================================= */

async function loadPaper() {

    renderAdvancedResult(
        "Paper Trading",
        {
            loading: "Paper Trading verileri yükleniyor..."
        }
    );

    try {

        const response =
            await publicFetch(
                "/api/paper"
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Paper Trading",
            data
        );

        return data;

    } catch (error) {

        renderAdvancedResult(
            "Paper Trading",
            {
                error: error.message
            }
        );

        return null;
    }
}


/* =========================================================
   MONTE CARLO
   ========================================================= */

async function loadMonteCarlo() {

    renderAdvancedResult(
        "Monte Carlo",
        {
            loading: "Monte Carlo analizi çalıştırılıyor..."
        }
    );

    try {

        const response =
            await publicFetch(
                "/api/montecarlo"
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Monte Carlo",
            data
        );

        return data;

    } catch (error) {

        renderAdvancedResult(
            "Monte Carlo",
            {
                error: error.message
            }
        );

        return null;
    }
}


/* =========================================================
   ADVANCED AI
   ========================================================= */

async function loadAdvancedAI() {

    try {

        const response =
            await publicFetch(
                "/api/metrics"
            );

        const data =
            await readJson(response);

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Gelişmiş AI",
            data
        );

        return data;

    } catch (error) {

        renderAdvancedResult(
            "Gelişmiş AI",
            {
                error: error.message
            }
        );

        return null;
    }
}


/* =========================================================
   ADVANCED RESULT
   ========================================================= */

function renderAdvancedResult(title, data) {

    const box =
        document.getElementById(
            "advancedResults"
        ) ||
        document.getElementById(
            "advancedResult"
        );

    if (!box) return;

    if (!data) {

        box.innerHTML = `
            <div class="advanced-result">
                <h3>${escapeHtml(title)}</h3>
                <p>Veri bulunamadı.</p>
            </div>
        `;

        return;
    }

    if (data.error) {

        box.innerHTML = `
            <div class="advanced-result">
                <h3>${escapeHtml(title)}</h3>

                <p>
                    ${escapeHtml(data.error)}
                </p>
            </div>
        `;

        return;
    }

    if (data.loading) {

        box.innerHTML = `
            <div class="advanced-result">
                <h3>${escapeHtml(title)}</h3>

                <p>
                    ⏳ ${escapeHtml(data.loading)}
                </p>
            </div>
        `;

        return;
    }

    const entries = [];

    function walk(object, prefix = "") {

        if (
            object === null ||
            object === undefined
        ) {
            return;
        }

        if (
            typeof object === "string" ||
            typeof object === "number" ||
            typeof object === "boolean"
        ) {

            entries.push([
                prefix,
                String(object)
            ]);

            return;
        }

        if (Array.isArray(object)) {

            entries.push([
                prefix || "Sonuç",
                `${object.length} kayıt`
            ]);

            return;
        }

        if (typeof object === "object") {

            Object.entries(object)
                .forEach(([key, value]) => {

                    const label =
                        prefix
                            ? `${prefix} / ${key}`
                            : key;

                    if (
                        value &&
                        typeof value === "object" &&
                        !Array.isArray(value)
                    ) {

                        walk(
                            value,
                            label
                        );

                    } else if (
                        Array.isArray(value)
                    ) {

                        entries.push([
                            label,
                            `${value.length} kayıt`
                        ]);

                    } else {

                        entries.push([
                            label,
                            value
                        ]);
                    }
                });
        }
    }

    walk(data);

    box.innerHTML = `
        <div class="advanced-result">

            <h3>
                ${escapeHtml(title)}
            </h3>

            <div class="advanced-result-grid">

                ${
                    entries
                        .slice(0, 100)
                        .map(([key, value]) => `
                            <div class="advanced-item">

                                <div class="advanced-key">
                                    ${escapeHtml(key)}
                                </div>

                                <div class="advanced-value">
                                    ${escapeHtml(value)}
                                </div>

                            </div>
                        `)
                        .join("")
                }

            </div>

        </div>
    `;
}


/* =========================================================
   ADMIN
   ========================================================= */

function openAdmin() {
    window.location.href = "/admin";
}


/* =========================================================
   LOGOUT
   ========================================================= */

async function logout() {

    try {

        await publicFetch(
            "/api/logout",
            {
                method: "POST",
                body: JSON.stringify({})
            }
        );

    } catch {}

    showAppScreen();
}


/* =========================================================
   OLD AUTH COMPATIBILITY
   ========================================================= */

async function loginUser(event) {

    if (event) {
        event.preventDefault();
    }

    showToast(
        "Üyelik gerekmiyor. Site doğrudan kullanılabilir.",
        "info"
    );

    showAppScreen();

    return true;
}


async function registerUser(event) {

    if (event) {
        event.preventDefault();
    }

    showToast(
        "Kayıt gerekmiyor. Site doğrudan kullanılabilir.",
        "info"
    );

    showAppScreen();

    return true;
}


/* =========================================================
   EVENTS
   ========================================================= */

function setupEvents() {

    const search =
        document.getElementById(
            "signalSearch"
        ) ||
        document.getElementById(
            "searchInput"
        );

    if (search) {

        search.addEventListener(
            "input",
            filterSignals
        );
    }


    document
        .querySelectorAll(
            "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    runAnalysis();
                }
            );
        });


    document
        .querySelectorAll(
            "#backtestBtn, [data-action='backtest']"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    loadBacktest();
                }
            );
        });


    document
        .querySelectorAll(
            "#paperBtn, [data-action='paper']"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    loadPaper();
                }
            );
        });


    document
        .querySelectorAll(
            "#monteCarloBtn, [data-action='montecarlo']"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    loadMonteCarlo();
                }
            );
        });


    document
        .querySelectorAll(
            "#advancedAIBtn, [data-action='advanced-ai']"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    loadAdvancedAI();
                }
            );
        });


    document
        .querySelectorAll(
            "[data-signal-filter]"
        )
        .forEach(button => {

            button.addEventListener(
                "click",
                event => {

                    event.preventDefault();

                    setSignalFilter(
                        button.dataset.signalFilter
                    );
                }
            );
        });
}


/* =========================================================
   KEYBOARD SEARCH
   ========================================================= */

document.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "/" &&
            document.activeElement?.tagName !== "INPUT" &&
            document.activeElement?.tagName !== "TEXTAREA"
        ) {

            event.preventDefault();

            const search =
                document.getElementById(
                    "signalSearch"
                ) ||
                document.getElementById(
                    "searchInput"
                );

            if (search) {
                search.focus();
            }
        }
    }
);


/* =========================================================
   START
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        showAppScreen();

        setupEvents();

        await refreshData();

        if (refreshTimer) {
            clearInterval(refreshTimer);
        }

        /*
         * 30 saniyede bir yenile.
         * Her yenilemede sadece 50 satır DOM'a basılır.
         */

        refreshTimer =
            setInterval(
                refreshData,
                30000
            );
    }
);


/* =========================================================
   GLOBAL
   ========================================================= */

window.loadSignals = loadSignals;
window.renderSignals = renderCurrentPage;
window.filterSignals = filterSignals;
window.searchSignals = searchSignals;
window.setSignalFilter = setSignalFilter;

window.changePage = changePage;

window.refreshData = refreshData;
window.loadStatus = loadStatus;

window.runAnalysis = runAnalysis;
window.monitorRun = monitorRun;

window.loadBacktest = loadBacktest;
window.loadPaper = loadPaper;
window.loadMonteCarlo = loadMonteCarlo;
window.loadAdvancedAI = loadAdvancedAI;

window.openSignal = openSignal;
window.openAdmin = openAdmin;

window.loginUser = loginUser;
window.registerUser = registerUser;
window.logout = logout;

window.checkSession = checkSession;
window.showAppScreen = showAppScreen;
window.showAuthScreen = showAuthScreen;

window.requirePlan = requirePlan;
window.selectPlan = selectPlan;
window.loadPlan = loadPlan;

window.renderAdvancedResult =
    renderAdvancedResult;