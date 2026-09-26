
"use strict";

/* =========================================================
   LEVEL 1000 AI - PUBLIC FRONTEND
   index.html DEÃ„ÂÃ„Â°Ã…ÂTÃ„Â°RÃ„Â°LMEYECEK
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

    // API:
    // 0.7467 = 74.67%
    // 0.0336 = 3.36%
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

    if (n === null || n === 0) {
        return "neutral";
    }

    if (n > 0) {
        return "positive";
    }

    return "negative";
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
        Accept: "application/json"
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
   SÃ„Â°NYAL NORMALÃ„Â°ZASYONU
   ========================================================= */

function normalizeSignal(row) {
    let signal =
        row?.signal ??
        row?.Signal ??
        row?.action ??
        row?.Action ??
        row?.sinyal ??
        row?.Sinyal ??
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
            row?.symbol ??
            row?.Symbol ??
            row?.ticker ??
            row?.Ticker ??
            "-",

        signal,

        score:
            row?.score ??
            row?.Score ??
            row?.ai_probability ??
            row?.AI_Probability ??
            0,

        price:
            row?.price ??
            row?.Price ??
            row?.close ??
            row?.Close ??
            null,

        change:
            row?.change ??
            row?.Change ??
            row?.daily_change_percent ??
            row?.Daily_Change_Percent ??
            null,

        predictedReturn:
            row?.predicted_return ??
            row?.Predicted_Return ??
            row?.ai_predicted_return ??
            row?.AI_Predicted_Return ??
            row?.expected_return ??
            row?.Expected_Return ??
            null,

        priceStatus:
            row?.price_status ??
            row?.Price_Status ??
            "",

        priceSource:
            row?.price_source ??
            row?.Price_Source ??
            "",

        date:
            row?.date ??
            row?.Date ??
            ""
    };
}


/* =========================================================
   TABLO
   ========================================================= */

function getTableBody() {
    /*
       Senin mevcut index.html dosyandaki ID:
       <tbody id="signalsBody">
    */

    return byId("signalsBody");
}

function showTableLoading() {
    const tbody = getTableBody();

    if (!tbody) {
        console.error("LEVEL 1000: signalsBody bulunamadÃ„Â±.");
        return;
    }

   tbody.innerHTML = `
    <tr>
        <td colspan="7" style="text-align:center;padding:30px;">
            <div style="font-size:28px;">⏳</div>
            <div style="font-weight:700;margin-top:8px;">
                SİNYALLER YÜKLENİYOR...
            </div>
            <div style="opacity:.7;margin-top:4px;">
                Piyasa verileri hazırlanıyor.
            </div>
        </td>
    </tr>
`;
function showTableError(message) {
    const tbody = getTableBody();

    if (!tbody) {
        return;
    }

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align:center;padding:30px;">
                <div style="font-size:28px;">Ã¢Å¡Â Ã¯Â¸Â</div>
                <div style="font-weight:700;margin-top:8px;">
                    ${escapeHtml(message)}
                </div>
                <div style="opacity:.7;margin-top:4px;">
                    SayfayÃ„Â± yenileyerek tekrar deneyin.
                </div>
            </td>
        </tr>
    `;
}


/* =========================================================
   KPI
   ========================================================= */

function updateKPIs(data) {
    const buy = Number(data?.buy ?? data?.historical_buy ?? 0);
    const sell = Number(data?.sell ?? data?.historical_sell ?? 0);
    const hold = Number(data?.hold ?? data?.historical_hold ?? 0);
    const top = Number(data?.top ?? data?.strong_signals ?? 0);
    const total = Number(data?.total ?? data?.historical_total ?? 0);

    setText("buyCount", buy.toLocaleString("tr-TR"));
    setText("sellCount", sell.toLocaleString("tr-TR"));
    setText("holdCount", hold.toLocaleString("tr-TR"));
    setText("topCount", top.toLocaleString("tr-TR"));
    setText("totalCount", total.toLocaleString("tr-TR"));
}


/* =========================================================
   SÃ„Â°NYALLERÃ„Â° YÃƒÅ“KLE
   ========================================================= */

async function loadSignals(page = currentPage, search = "") {
    if (isLoadingSignals) {
        return null;
    }

    isLoadingSignals = true;
    showTableLoading();

    try {
        const safePage = Math.max(1, Number(page) || 1);
        const params = new URLSearchParams();

        params.set("page", String(safePage));
        params.set("limit", String(PAGE_SIZE));

        if (search && String(search).trim()) {
            params.set("search", String(search).trim());
        }

        console.log(
            "LEVEL 1000: /api/signals yÃ¼kleniyor...",
            params.toString()
        );

        const response = await publicFetch(
            "/api/signals?" + params.toString()
        );

        console.log("LEVEL 1000: FETCH TAMAMLANDI", response.status, response.headers.get("content-type"));

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        console.log("LEVEL 1000: JSON OKUNUYOR...");

        const data = await readJson(response);

        console.log("LEVEL 1000: JSON OKUNDU", data);

        if (!data || !Array.isArray(data.signals)) {
            throw new Error("API geÃ§erli sinyal verisi dÃ¶ndÃ¼rmedi.");
        }

        allSignals = data.signals;
        filteredSignals = [...data.signals];

        currentPage = Number(data.page) || safePage;

        window.signalPagination = {
            total: Number(data.total) || 0,
            pages: Number(data.pages) || 1,
            page: currentPage,
            limit: Number(data.limit) || PAGE_SIZE,
            search: search || ""
        };

        updateKPIs(data);
        renderCurrentPage();

        setText("apiStatus", "ONLINE");
        setText("marketStatus", "AKTÄ°F");
        setText("liveStatus", "Aktif");
        setText("accessStatus", "PUBLIC");

        return data;

    } catch (error) {
        console.error("LEVEL 1000 API HATASI:", error);

        showTableError("Sinyal verileri yÃ¼klenemedi.");

        setText("apiStatus", "HATA");
        setText("marketStatus", "HATA");

        return null;

    } finally {
        isLoadingSignals = false;
    }
}


/* =========================================================
   TABLOYU RENDER ET
   ========================================================= */

function renderCurrentPage() {
    const tbody = getTableBody();

    if (!tbody) {
        console.error("LEVEL 1000: signalsBody bulunamadÄ±!");
        return;
    }

    const rows = filteredSignals;

    if (!rows.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align:center;padding:30px;">
                    SonuÃ§ bulunamadÄ±.
                </td>
            </tr>
        `;

        renderPagination();
        return;
    }

    tbody.innerHTML = rows.map(row => {
        const s = normalizeSignal(row);

        const changeClass = valueClass(s.change);
        const returnClass = valueClass(s.predictedReturn);

        return `
            <tr>
                <td>
                    <button
                        type="button"
                        onclick="openSignal('${escapeHtml(s.symbol)}')"
                        style="
                            background:none;
                            border:0;
                            padding:0;
                            cursor:pointer;
                            font-weight:700;
                            color:inherit;
                        "
                    >
                        ${escapeHtml(s.symbol)}
                    </button>
                </td>

                <td>
                    <span class="${signalClass(s.signal)}">
                        ${escapeHtml(s.signal)}
                    </span>
                </td>

                <td>${formatPercent(s.score)}</td>
                <td>${formatNumber(s.price)}</td>
                <td class="${changeClass}">
                    ${formatPercent(s.change)}
                </td>
                <td class="${returnClass}">
                    ${formatPercent(s.predictedReturn)}
                </td>
                <td>${escapeHtml(s.date)}</td>
            </tr>
        `;
    }).join("");

    renderPagination();
}


/* =========================================================
   ARAMA
   ========================================================= */

let searchTimer = null;

function filterSignals() {
    const input = byId("signalSearch");
    const query = input
        ? String(input.value || "").trim()
        : "";

    currentPage = 1;

    clearTimeout(searchTimer);

    searchTimer = setTimeout(() => {
        loadSignals(1, query);
    }, 350);
}

function searchSignals() {
    filterSignals();
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
        Number(window.signalPagination?.pages) || 1
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
        Math.min(maxPage, Math.floor(requestedPage))
    );

    const input = byId("signalSearch");
    const search = input
        ? String(input.value || "").trim()
        : "";

    loadSignals(currentPage, search).then(() => {
        const section = byId("signalsSection");

        if (section) {
            section.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }
    });
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

    const pagination = window.signalPagination || {};
    const pages = Math.max(1, Number(pagination.pages) || 1);
    const page = Math.max(1, Number(pagination.page) || 1);
    const total = Number(pagination.total) || 0;

    if (!total) {
        container.innerHTML = "";
        return;
    }

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
        border:1px solid #64748b;
        border-radius:8px;
        background:#2563eb;
        color:white;
        cursor:pointer;
        font-weight:700;
    `;

    let html = `
        <button
            type="button"
            style="${buttonStyle}"
            ${page <= 1 ? "disabled" : ""}
            onclick="changePage(${page - 1})"
        >â€¹</button>
    `;

    const start = Math.max(1, page - 2);
    const end = Math.min(pages, page + 2);

    for (let i = start; i <= end; i++) {
        html += `
            <button
                type="button"
                style="${i === page ? activeStyle : buttonStyle}"
                onclick="changePage(${i})"
            >${i}</button>
        `;
    }

    html += `
        <button
            type="button"
            style="${buttonStyle}"
            ${page >= pages ? "disabled" : ""}
            onclick="changePage(${page + 1})"
        >â€º</button>

        <span style="margin-left:10px;opacity:.75;">
            Sayfa ${page.toLocaleString("tr-TR")} /
            ${pages.toLocaleString("tr-TR")}
            Â· ${total.toLocaleString("tr-TR")} kayÄ±t
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

        if (byId("systemStatus")) {
            setText(
                "systemStatus",
                running
                    ? "ANALÃ„Â°Z Ãƒâ€¡ALIÃ…ÂIYOR"
                    : "HAZIR"
            );
        }

        setText(
            "apiStatus",
            "ONLINE"
        );

        return data;

    } catch (error) {
        console.error(
            "LEVEL 1000 Status:",
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
   YENÃ„Â°LE
   ========================================================= */

async function refreshData() {
    await Promise.all([
        loadSignals(),
        loadStatus()
    ]);
}


/* =========================================================
   AI ANALÃ„Â°ZÃ„Â° BAÃ…ÂLAT
   ========================================================= */

async function runAnalysis() {
    const button =
        byId("runAnalysisButton");

    if (button) {
        button.disabled = true;
        button.textContent =
            "Analiz baÃ…Å¸latÃ„Â±lÃ„Â±yor...";
    }

    setText(
        "runStatus",
        "Analiz baÃ…Å¸latÃ„Â±lÃ„Â±yor..."
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
            "Analiz ÃƒÂ§alÃ„Â±Ã…Å¸Ã„Â±yor..."
        );

        monitorRun();

    } catch (error) {
        console.error(
            "LEVEL 1000 Run:",
            error
        );

        setText(
            "runStatus",
            error.message ||
            "Analiz baÃ…Å¸latÃ„Â±lamadÃ„Â±."
        );

        if (button) {
            button.disabled = false;
            button.textContent =
                "Ã¢Å¡Â¡ AI ANALÃ„Â°ZÃ„Â°NÃ„Â° BAÃ…ÂLAT";
        }
    }
}


/* =========================================================
   Ãƒâ€¡ALIÃ…ÂMA DURUMU
   ========================================================= */

async function monitorRun() {
    if (runPollTimer) {
        clearInterval(runPollTimer);
    }

    runPollTimer = setInterval(
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
                        "Analiz ÃƒÂ§alÃ„Â±Ã…Å¸Ã„Â±yor..."
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
                    "Analiz tamamlandÃ„Â±."
                );

                const button =
                    byId(
                        "runAnalysisButton"
                    );

                if (button) {
                    button.disabled = false;
                    button.textContent =
                        "Ã¢Å¡Â¡ AI ANALÃ„Â°ZÃ„Â°NÃ„Â° BAÃ…ÂLAT";
                }

                await loadSignals();

            } catch (error) {
                console.error(
                    "LEVEL 1000 Ãƒâ€¡alÃ„Â±Ã…Å¸ma durumu:",
                    error
                );
            }
        },
        3000
    );
}


/* =========================================================
   GELÃ„Â°Ã…ÂMÃ„Â°Ã…Â ANALÃ„Â°Z SONUÃƒâ€¡LARI
   ========================================================= */

function renderAdvancedResult(
    title,
    data
) {
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
        "LEVEL 1000 AI sonuÃƒÂ§larÃ„Â±"
    );

    if (!data) {
        box.innerHTML = `
            <div style="padding:20px;">
                Veri bulunamadÃ„Â±.
            </div>
        `;
        return;
    }

    if (data.error) {
        box.innerHTML = `
            <div style="
                padding:20px;
                color:#ef4444;
            ">
                ${escapeHtml(data.error)}
            </div>
        `;

        return;
    }

    if (data.loading) {
        box.innerHTML = `
            <div style="padding:20px;">
                Ã¢ÂÂ³ ${escapeHtml(data.loading)}
            </div>
        `;

        return;
    }

    const entries = [];

    function walk(
        object,
        prefix = ""
    ) {
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
                prefix || "SonuÃƒÂ§",
                `${object.length} kayÃ„Â±t`
            ]);

            return;
        }

        if (
            typeof object === "object"
        ) {
            Object.entries(object)
                .forEach(
                    ([key, value]) => {
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
                                    ? `${value.length} kayÃ„Â±t`
                                    : value
                            ]);
                        }
                    }
                );
        }
    }

    walk(data);

    box.innerHTML = entries
        .slice(0, 100)
        .map(
            ([key, value]) => `
                <div style="
                    display:flex;
                    justify-content:space-between;
                    gap:20px;
                    padding:10px 12px;
                    border-bottom:1px solid rgba(148,163,184,.15);
                ">
                    <strong>
                        ${escapeHtml(key)}
                    </strong>

                    <span>
                        ${escapeHtml(value)}
                    </span>
                </div>
            `
        )
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
                "Backtest verileri yÃƒÂ¼kleniyor..."
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
                error:
                    error.message ||
                    "Backtest yÃƒÂ¼klenemedi."
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
                "Paper Trading verileri yÃƒÂ¼kleniyor..."
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
                error:
                    error.message ||
                    "Paper Trading verileri yÃƒÂ¼klenemedi."
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
                "Monte Carlo analizi ÃƒÂ§alÃ„Â±Ã…Å¸tÃ„Â±rÃ„Â±lÃ„Â±yor..."
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
                error:
                    error.message ||
                    "Monte Carlo yÃƒÂ¼klenemedi."
            }
        );
    }
}


/* =========================================================
   GELÃ„Â°Ã…ÂMÃ„Â°Ã…Â AI / METRÃ„Â°KLER
   ========================================================= */

async function loadAdvancedAI() {
    renderAdvancedResult(
        "GeliÃ…Å¸miÃ…Å¸ AI",
        {
            loading:
                "AI verileri yÃƒÂ¼kleniyor..."
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
            "GeliÃ…Å¸miÃ…Å¸ AI",
            data
        );

    } catch (error) {
        renderAdvancedResult(
            "GeliÃ…Å¸miÃ…Å¸ AI",
            {
                error:
                    error.message ||
                    "AI metrikleri yÃƒÂ¼klenemedi."
            }
        );
    }
}


/* =========================================================
   SÃ„Â°NYAL DETAYI
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
            "Sinyal detayÃ„Â±:",
            error
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
   BAÃ…ÂLAT
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    async () => {
        console.log(
            "LEVEL 1000 AI baÃ…Å¸latÃ„Â±lÃ„Â±yor..."
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
            clearInterval(
                refreshTimer
            );
        }

        /*
           30 saniyede bir gÃƒÂ¼ncelle.
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

window.loadSignals =
    loadSignals;

window.renderSignals =
    renderCurrentPage;

window.filterSignals =
    filterSignals;

window.searchSignals =
    searchSignals;

window.changePage =
    changePage;

window.refreshData =
    refreshData;

window.loadStatus =
    loadStatus;

window.runAnalysis =
    runAnalysis;

window.monitorRun =
    monitorRun;

window.loadBacktest =
    loadBacktest;

window.loadPaper =
    loadPaper;

window.loadMonteCarlo =
    loadMonteCarlo;

window.loadAdvancedAI =
    loadAdvancedAI;

window.openSignal =
    openSignal;

window.renderAdvancedResult =
    renderAdvancedResult;

window.openAdmin =
    openAdmin;

window.loginUser =
    loginUser;

window.registerUser =
    registerUser;

window.logout =
    logout;

window.checkSession =
    checkSession;

window.showAppScreen =
    showAppScreen;

window.showAuthScreen =
    showAuthScreen;

window.requirePlan =
    requirePlan;

window.selectPlan =
    selectPlan;

window.loadPlan =
    loadPlan;
