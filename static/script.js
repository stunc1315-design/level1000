"use strict";

/* =========================================================
   LEVEL 1000 AI - PUBLIC FRONTEND
   ========================================================= */

const API_BASE = "";
const PAGE_SIZE = 50;

let allSignals = [];
let filteredSignals = [];
let currentPage = 1;
let isLoadingSignals = false;
let refreshTimer = null;
let runPollTimer = null;

/* =========================================================
   YARDIMCILAR
   ========================================================= */

function byId(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const el = byId(id);
    if (el) {
        el.textContent = value ?? "";
    }
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function numberValue(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function formatNumber(value, decimals = 2) {
    const n = numberValue(value);

    if (n === null) {
        return "-";
    }

    return n.toLocaleString("tr-TR", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function formatPercent(value) {
    const n = numberValue(value);

    if (n === null) {
        return "-";
    }

    let percent = n;

    /*
       API:
       0.7467 = 74.67%
       0.0336 = 3.36%
       74.67  = 74.67%
    */
    if (Math.abs(percent) <= 1) {
        percent *= 100;
    }

    return percent.toLocaleString("tr-TR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }) + "%";
}

function valueClass(value) {
    const n = numberValue(value);

    if (n === null) {
        return "neutral";
    }

    if (n > 0) {
        return "positive";
    }

    if (n < 0) {
        return "negative";
    }

    return "neutral";
}

function signalClass(signal) {
    const s = String(signal || "").toUpperCase();

    if (s === "BUY" || s === "AL") {
        return "signal-buy";
    }

    if (s === "SELL" || s === "SAT") {
        return "signal-sell";
    }

    return "signal-hold";
}

/* =========================================================
   API
   ========================================================= */

async function publicFetch(url, options = {}) {
    const headers = {
        "Accept": "application/json"
    };

    if (options.body) {
        headers["Content-Type"] = "application/json";
    }

    if (options.headers) {
        Object.assign(headers, options.headers);
    }

    return fetch(API_BASE + url, {
        ...options,
        headers
    });
}

async function readJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}

/* =========================================================
   SİNYAL NORMALİZASYONU
   ========================================================= */

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

    if (signal === "AL") {
        signal = "BUY";
    }

    if (signal === "SAT") {
        signal = "SELL";
    }

    if (signal === "BEKLE") {
        signal = "HOLD";
    }

    return {
        symbol:
            row.symbol ??
            row.Symbol ??
            row.ticker ??
            row.Ticker ??
            "-",

        signal: signal,

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

        change:
            row.change ??
            row.Change ??
            row.daily_change_percent ??
            row.Daily_Change_Percent ??
            null,

        predictedReturn:
            row.predicted_return ??
            row.Predicted_Return ??
            row.ai_predicted_return ??
            row.AI_Predicted_Return ??
            row.expected_return ??
            row.Expected_Return ??
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
   TABLO
   ========================================================= */

function getTableBody() {
    return byId("signalsBody");
}

function showTableLoading() {
    const tbody = getTableBody();

    if (!tbody) {
        console.error("LEVEL 1000: signalsBody bulunamadı.");
        return;
    }

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;padding:35px;">
                <div style="font-size:28px;margin-bottom:8px;">⏳</div>
                <strong>Veriler yükleniyor...</strong>
                <div style="margin-top:6px;opacity:.7;">
                    Sinyal verisi alınıyor.
                </div>
            </td>
        </tr>
    `;
}

function showTableError(message) {
    const tbody = getTableBody();

    if (!tbody) {
        return;
    }

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;padding:35px;">
                <div style="font-size:28px;margin-bottom:8px;">⚠️</div>
                <strong>Veriler yüklenemedi</strong>
                <div style="margin-top:8px;opacity:.8;">
                    ${escapeHtml(message)}
                </div>
                <button
                    onclick="loadSignals()"
                    style="
                        margin-top:15px;
                        padding:9px 15px;
                        border:1px solid #475569;
                        border-radius:8px;
                        cursor:pointer;
                    "
                >
                    Tekrar Dene
                </button>
            </td>
        </tr>
    `;
}

/* =========================================================
   KPI
   ========================================================= */

function updateKPIs(data) {
    const buy = Number(data.buy || 0);
    const sell = Number(data.sell || 0);
    const hold = Number(data.hold || 0);
    const total = Number(
        data.total ||
        allSignals.length ||
        0
    );

    setText(
        "buyCount",
        buy.toLocaleString("tr-TR")
    );

    setText(
        "satışSayısı",
        sell.toLocaleString("tr-TR")
    );

    setText(
        "tutmaSayısı",
        hold.toLocaleString("tr-TR")
    );

    setText(
        "toplamSayısı",
        total.toLocaleString("tr-TR")
    );
}

/* =========================================================
   SİNYALLERİ YÜKLE
   ========================================================= */

async function loadSignals() {
    if (isLoadingSignals) {
        return null;
    }

    isLoadingSignals = true;

    showTableLoading();

    try {
        console.log("LEVEL 1000: /api/signals yükleniyor...");

        const response = await publicFetch("/api/signals");

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const data = await readJson(response);

        if (!data || !Array.isArray(data.signals)) {
            throw new Error(
                "API geçerli sinyal verisi döndürmedi."
            );
        }

        console.log(
            "LEVEL 1000:",
            data.signals.length,
            "sinyal alındı."
        );

        allSignals = data.signals;
        filteredSignals = [...allSignals];
        currentPage = 1;

        updateKPIs(data);
        renderCurrentPage();

        setText("apiStatus", "ONLINE");
        setText("marketStatus", "AKTİF");
        setText("liveStatus", "Aktif");
        setText("accessStatus", "PUBLIC");

        return data;

    } catch (error) {

        console.error(
            "LEVEL 1000 API HATASI:",
            error
        );

        showTableError(
            "Sinyal verileri yüklenemedi. API bağlantısını kontrol edin."
        );

        setText("apiStatus", "HATA");
        setText("marketStatus", "HATA");

        return null;

    } finally {
        isLoadingSignals = false;
    }
}

/* =========================================================
   TABLOYU RENDER
   ========================================================= */

function renderCurrentPage() {
    const tbody = getTableBody();

    if (!tbody) {
        console.error(
            "LEVEL 1000: signalsBody bulunamadı."
        );
        return;
    }

    const total = filteredSignals.length;

    if (total === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align:center;padding:30px;">
                    Sonuç bulunamadı.
                </td>
            </tr>
        `;

        renderPagination();
        return;
    }

    const start = (currentPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;

    /*
       ÖNEMLİ:
       166.200 kaydın tamamını DOM'a basmıyoruz.
       Sadece 50 kayıt gösteriyoruz.
    */
    const rows = filteredSignals.slice(start, end);

    tbody.innerHTML = rows.map(row => {

        const s = normalizeSignal(row);

        const changeClass = valueClass(s.change);
        const returnClass = valueClass(s.predictedReturn);

        return `
            <tr
                class="signal-row"
                data-symbol="${escapeHtml(s.symbol)}"
                style="cursor:pointer;"
                onclick="openSignal('${String(s.symbol).replaceAll("'", "\\'")}')"
            >

                <td>
                    <strong>
                        ${escapeHtml(s.symbol)}
                    </strong>
                </td>

                <td>
                    <span class="${signalClass(s.signal)}">
                        ${escapeHtml(s.signal)}
                    </span>
                </td>

                <td>
                    <strong>
                        ${formatPercent(s.score)}
                    </strong>
                </td>

                <td>
                    ${formatNumber(s.price)}
                </td>

                <td class="${changeClass}">
                    ${formatPercent(s.change)}
                </td>

                <td class="${returnClass}">
                    <strong>
                        ${formatPercent(s.predictedReturn)}
                    </strong>
                </td>

                <td>
                    ${escapeHtml(s.date)}
                </td>

            </tr>
        `;

    }).join("");

    renderPagination();
}

/* =========================================================
   ARAMA
   ========================================================= */

function filterSignals() {
    const input = byId("signalSearch");

    const query = input
        ? input.value.trim().toLowerCase()
        : "";

    filteredSignals = allSignals.filter(row => {

        const s = normalizeSignal(row);

        return String(s.symbol)
            .toLowerCase()
            .includes(query);

    });

    currentPage = 1;

    renderCurrentPage();
}

function searchSignals() {
    filterSignals();
}

/* =========================================================
   SAYFALAMA
   ========================================================= */

function getPageCount() {
    return Math.max(
        1,
        Math.ceil(
            filteredSignals.length / PAGE_SIZE
        )
    );
}

function changePage(page) {

    const maxPage = getPageCount();

    const requestedPage = Number(page);

    if (!Number.isFinite(requestedPage)) {
        return;
    }

    currentPage = Math.max(
        1,
        Math.min(
            maxPage,
            requestedPage
        )
    );

    renderCurrentPage();

    const section = byId("signalsSection");

    if (section) {
        section.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }
}

function renderPagination() {

    const section = byId("signalsSection");

    if (!section) {
        return;
    }

    let container = byId("signalsPagination");

    if (!container) {

        container = document.createElement("div");

        container.id = "signalsPagination";

        container.style.cssText = `
            display:flex;
            justify-content:center;
            align-items:center;
            flex-wrap:wrap;
            gap:7px;
            padding:18px;
        `;

        section.appendChild(container);
    }

    const pages = getPageCount();

    if (filteredSignals.length === 0) {
        container.innerHTML = "";
        return;
    }

    let html = "";

    const buttonStyle = `
        padding:8px 12px;
        border:1px solid #334155;
        border-radius:8px;
        background:#111827;
        color:white;
        cursor:pointer;
    `;

    const activeStyle = `
        padding:8px 12px;
        border:1px solid #2563eb;
        border-radius:8px;
        background:#2563eb;
        color:white;
        cursor:pointer;
    `;

    html += `
        <button
            onclick="changePage(${currentPage - 1})"
            ${currentPage === 1 ? "disabled" : ""}
            style="${buttonStyle}"
        >
            ‹
        </button>
    `;

    const start = Math.max(
        1,
        currentPage - 2
    );

    const end = Math.min(
        pages,
        currentPage + 2
    );

    if (start > 1) {

        html += `
            <button
                onclick="changePage(1)"
                style="${buttonStyle}"
            >
                1
            </button>
        `;

        if (start > 2) {
            html += `
                <span style="padding:8px;">
                    …
                </span>
            `;
        }
    }

    for (let i = start; i <= end; i++) {

        html += `
            <button
                onclick="changePage(${i})"
                style="${i === currentPage ? activeStyle : buttonStyle}"
            >
                ${i}
            </button>
        `;
    }

    if (end < pages) {

        if (end < pages - 1) {
            html += `
                <span style="padding:8px;">
                    …
                </span>
            `;
        }

        html += `
            <button
                onclick="changePage(${pages})"
                style="${buttonStyle}"
            >
                ${pages}
            </button>
        `;
    }

    html += `
        <button
            onclick="changePage(${currentPage + 1})"
            ${currentPage === pages ? "disabled" : ""}
            style="${buttonStyle}"
        >
            ›
        </button>
    `;

    const startItem =
        (currentPage - 1) * PAGE_SIZE + 1;

    const endItem =
        Math.min(
            currentPage * PAGE_SIZE,
            filteredSignals.length
        );

    html += `
        <span
            style="
                margin-left:10px;
                opacity:.75;
                font-size:14px;
            "
        >
            ${startItem.toLocaleString("tr-TR")}
            -
            ${endItem.toLocaleString("tr-TR")}
            /
            ${filteredSignals.length.toLocaleString("tr-TR")}
        </span>
    `;

    container.innerHTML = html;
}

/* =========================================================
   DURUM
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

        setText(
            "apiStatus",
            "ONLINE"
        );

        return data;

    } catch (error) {

        console.error(
            "Status:",
            error
        );

        setText(
            "apiStatus",
            "HATA"
        );

        return null;
    }
}

/* =========================================================
   YENİLE
   ========================================================= */

async function refreshData() {

    await Promise.all([
        loadSignals(),
        loadStatus()
    ]);
}

/* =========================================================
   AI ANALİZİ BAŞLAT
   ========================================================= */

async function runAnalysis() {

    const button =
        byId("runAnalysisButton");

    if (button) {
        button.disabled = true;
        button.textContent =
            "Analiz başlatılıyor...";
    }

    setText(
        "runStatus",
        "Analiz başlatılıyor..."
    );

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

        setText(
            "runStatus",
            data.message ||
            "Analiz çalışıyor..."
        );

        monitorRun();

    } catch (error) {

        console.error(
            "Run:",
            error
        );

        setText(
            "runStatus",
            error.message ||
            "Analiz başlatılamadı."
        );

        if (button) {
            button.disabled = false;
            button.textContent =
                "⚡ AI ANALİZİNİ BAŞLAT";
        }
    }
}

/* =========================================================
   ANALİZ DURUMU
   ========================================================= */

async function monitorRun() {

    if (runPollTimer) {
        clearInterval(runPollTimer);
    }

    runPollTimer =
        setInterval(
            async () => {

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
                            "runStatus",
                            data.message ||
                            "Analiz çalışıyor..."
                        );

                        return;
                    }

                    clearInterval(
                        runPollTimer
                    );

                    runPollTimer = null;

                    setText(
                        "runStatus",
                        data.error ||
                        data.message ||
                        "Analiz tamamlandı."
                    );

                    const button =
                        byId("runAnalysisButton");

                    if (button) {
                        button.disabled = false;
                        button.textContent =
                            "⚡ AI ANALİZİNİ BAŞLAT";
                    }

                    await loadSignals();

                } catch (error) {

                    console.error(
                        "Çalışma durumu:",
                        error
                    );

                }

            },
            3000
        );
}

/* =========================================================
   GELİŞMİŞ ANALİZ SONUÇLARI
   ========================================================= */

function renderAdvancedResult(title, data) {

    const section =
        byId("advancedResults");

    const box =
        byId("advancedResultsBody");

    if (!section || !box) {
        return;
    }

    section.style.display = "block";

    setText(
        "advancedResultsTitle",
        title
    );

    setText(
        "advancedResultsSubtitle",
        "LEVEL 1000 AI sonuçları"
    );

    if (!data) {

        box.innerHTML = `
            <div style="padding:20px;">
                Veri bulunamadı.
            </div>
        `;

        return;
    }

    if (data.error) {

        box.innerHTML = `
            <div style="padding:20px;">
                ⚠️ ${escapeHtml(data.error)}
            </div>
        `;

        return;
    }

    if (data.loading) {

        box.innerHTML = `
            <div style="padding:20px;">
                ⏳ ${escapeHtml(data.loading)}
            </div>
        `;

        return;
    }

    if (data.yükleniyor) {

        box.innerHTML = `
            <div style="padding:20px;">
                ⏳ ${escapeHtml(data.yükleniyor)}
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

                    } else {

                        entries.push([
                            label,
                            Array.isArray(value)
                                ? `${value.length} kayıt`
                                : value
                        ]);
                    }
                });
        }
    }

    walk(data);

    if (!entries.length) {

        box.innerHTML = `
            <div style="padding:20px;">
                Sonuç bulunamadı.
            </div>
        `;

        return;
    }

    box.innerHTML = entries
        .slice(0, 100)
        .map(([key, value]) => `
            <div
                style="
                    display:flex;
                    justify-content:space-between;
                    gap:20px;
                    padding:10px 12px;
                    border-bottom:1px solid rgba(255,255,255,.08);
                "
            >
                <strong>
                    ${escapeHtml(key)}
                </strong>

                <span>
                    ${escapeHtml(value)}
                </span>
            </div>
        `)
        .join("");
}

/* =========================================================
   BACKTEST
   ========================================================= */

async function loadBacktest() {

    renderAdvancedResult(
        "Backtest",
        {
            loading:
                "Backtest verileri yükleniyor..."
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

    } catch (error) {

        renderAdvancedResult(
            "Backtest",
            {
                error: error.message
            }
        );
    }
}

/* =========================================================
   PAPER TRADING
   ========================================================= */

async function loadPaper() {

    renderAdvancedResult(
        "Paper Trading",
        {
            loading:
                "Paper Trading verileri yükleniyor..."
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

    } catch (error) {

        renderAdvancedResult(
            "Paper Trading",
            {
                error: error.message
            }
        );
    }
}

/* =========================================================
   MONTE CARLO
   ========================================================= */

async function loadMonteCarlo() {

    renderAdvancedResult(
        "Monte Carlo",
        {
            loading:
                "Monte Carlo analizi çalıştırılıyor..."
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
            "Monte Carlo Sonucu",
            data
        );

    } catch (error) {

        renderAdvancedResult(
            "Monte Carlo",
            {
                error: error.message
            }
        );
    }
}

/* =========================================================
   GELİŞMİŞ AI
   ========================================================= */

async function loadAdvancedAI() {

    renderAdvancedResult(
        "Gelişmiş AI",
        {
            loading:
                "AI verileri yükleniyor..."
        }
    );

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

    } catch (error) {

        renderAdvancedResult(
            "Gelişmiş AI",
            {
                error: error.message
            }
        );
    }
}

/* =========================================================
   SİNYAL DETAYI
   ========================================================= */

async function openSignal(ticker) {

    if (!ticker) {
        return;
    }

    try {

        const response =
            await publicFetch(
                "/api/signal/" +
                encodeURIComponent(ticker)
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

    } catch (error) {

        console.error(
            "Sinyal detayı:",
            error
        );

        renderAdvancedResult(
            `${ticker} Analizi`,
            {
                error: error.message
            }
        );
    }
}

/* =========================================================
   PUBLIC MOD
   ========================================================= */

function showAppScreen() {

    const auth =
        byId("authScreen");

    const app =
        byId("appScreen");

    if (auth) {
        auth.style.display = "none";
    }

    if (app) {
        app.style.display = "block";
    }
}

async function checkSession() {
    showAppScreen();
    return true;
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

    setText(
        "userPlan",
        "OPEN"
    );

    setText(
        "planName",
        "OPEN"
    );

    return {
        ok: true,
        plan: "OPEN",
        plan_level: 999999
    };
}

async function loginUser(event) {

    if (event) {
        event.preventDefault();
    }

    showAppScreen();

    return true;
}

async function registerUser(event) {

    if (event) {
        event.preventDefault();
    }

    showAppScreen();

    return true;
}

async function logout() {
    showAppScreen();
    return true;
}

function openAdmin() {
    window.location.href = "/admin";
}

/* =========================================================
   BAŞLAT
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        console.log(
            "LEVEL 1000 AI başlatılıyor..."
        );

        showAppScreen();

        const search =
            byId("signalSearch");

        if (search) {

            search.addEventListener(
                "input",
                filterSignals
            );
        }

        await refreshData();

        if (refreshTimer) {
            clearInterval(refreshTimer);
        }

        /*
           Her 30 saniyede fiyat/sinyal verisini yenile.
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
window.renderAdvancedResult = renderAdvancedResult;
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

console.log(
    "LEVEL 1000 AI frontend hazır."
);