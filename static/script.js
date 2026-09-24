/* =========================================================
   LEVEL 1000 AI — PUBLIC / OPEN MODE
   Üyelik: YOK
   Ödeme: YOK
   Plan: YOK
   Kullanım limiti: YOK
   ========================================================= */

"use strict";

const API_BASE = "";

let allSignals = [];
let filteredSignals = [];
let runPollTimer = null;
let refreshTimer = null;

/* =========================================================
   GENEL API
   ========================================================= */

async function publicFetch(url, options = {}) {
    const config = {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    };

    return fetch(API_BASE + url, config);
}

async function readJson(response) {
    try {
        return await response.json();
    } catch (e) {
        return {};
    }
}

function showToast(message, type = "info") {
    const old = document.querySelector(".level-toast");
    if (old) old.remove();

    const toast = document.createElement("div");
    toast.className = `level-toast ${type}`;
    toast.textContent = message;

    Object.assign(toast.style, {
        position: "fixed",
        right: "20px",
        bottom: "20px",
        zIndex: "99999",
        padding: "14px 18px",
        borderRadius: "10px",
        background: "rgba(20,20,25,.95)",
        color: "#fff",
        fontSize: "14px",
        boxShadow: "0 8px 30px rgba(0,0,0,.35)",
        maxWidth: "380px"
    });

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3500);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setHTML(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
}

/* =========================================================
   OTURUM / PLAN
   PUBLIC MOD
   ========================================================= */

async function checkSession() {
    showAppScreen();
    return true;
}

function showAppScreen() {
    const authScreen = document.getElementById("authScreen");
    const appScreen = document.getElementById("appScreen");

    if (authScreen) {
        authScreen.style.display = "none";
    }

    if (appScreen) {
        appScreen.style.display = "block";
    }
}

function showAuthScreen() {
    // Public modda giriş ekranı kullanılmaz.
    showAppScreen();
}

function requirePlan() {
    // Artık hiçbir plan kontrolü yok.
    return true;
}

function selectPlan() {
    // Plan sistemi kaldırıldı.
    return true;
}

async function loadPlan() {
    // Plan sistemi kaldırıldı.
    setText("userPlan", "OPEN");
    setText("planName", "OPEN");
    return {
        ok: true,
        plan: "OPEN",
        plan_level: 999,
        features: {
            display_limit: null,
            scan_limit: null,
            backtest: true,
            paper: true,
            advanced_ai: true,
            all_signals: true
        }
    };
}

/* =========================================================
   SİNYALLER
   ========================================================= */

async function loadSignals() {
    try {
        const response = await publicFetch("/api/signals");

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await readJson(response);

        let signals = [];

        if (Array.isArray(data)) {
            signals = data;
        } else if (Array.isArray(data.signals)) {
            signals = data.signals;
        } else if (Array.isArray(data.data)) {
            signals = data.data;
        } else if (Array.isArray(data.results)) {
            signals = data.results;
        }

        allSignals = signals;
        filteredSignals = signals;

        renderSignals(signals);
        updateKPIs(signals);

        setText(
            "signalUpdated",
            data.updated_at ||
            data.last_update ||
            new Date().toLocaleString("tr-TR")
        );

        return data;
    } catch (error) {
        console.error("Signals error:", error);

        setHTML(
            "signalsTableBody",
            `
            <tr>
                <td colspan="20" style="text-align:center;padding:30px;">
                    Sinyal verileri alınamadı.
                </td>
            </tr>
            `
        );

        return null;
    }
}

/* =========================================================
   SİNYAL RENDER
   ========================================================= */

function normalizeSignal(row) {
    const ticker =
        row.Ticker ??
        row.ticker ??
        row.Symbol ??
        row.symbol ??
        row.Code ??
        row.code ??
        "-";

    let signal =
        row.Signal ??
        row.signal ??
        row.Action ??
        row.action ??
        row.Sinyal ??
        row.sinyal ??
        "HOLD";

    signal = String(signal).toUpperCase();

    if (signal === "AL") signal = "BUY";
    if (signal === "SAT") signal = "SELL";
    if (signal === "BEKLE") signal = "HOLD";

    const probability =
        row.AI_Probability ??
        row.ai_probability ??
        row.Probability ??
        row.probability ??
        row.Score ??
        row.score ??
        null;

    const predictedReturn =
        row.AI_Predicted_Return ??
        row.ai_predicted_return ??
        row.Predicted_Return ??
        row.predicted_return ??
        row.Expected_Return ??
        row.expected_return ??
        null;

    const price =
        row.Price ??
        row.price ??
        row.Close ??
        row.close ??
        row.Last_Price ??
        row.last_price ??
        null;

    const change =
        row.Daily_Change_Percent ??
        row.daily_change_percent ??
        row.Change_Percent ??
        row.change_percent ??
        null;

    const date =
        row.Date ??
        row.date ??
        row.Timestamp ??
        row.timestamp ??
        "-";

    return {
        raw: row,
        ticker,
        signal,
        probability,
        predictedReturn,
        price,
        change,
        date
    };
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

    let number = Number(value);

    if (Math.abs(number) <= 1) {
        number *= 100;
    }

    return `${number.toFixed(2)}%`;
}

function signalClass(signal) {
    if (signal === "BUY") return "buy";
    if (signal === "SELL") return "sell";
    return "hold";
}

function renderSignals(signals) {
    const tbody =
        document.getElementById("signalsTableBody") ||
        document.querySelector("#signalsTable tbody");

    if (!tbody) return;

    if (!signals || signals.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="20" style="text-align:center;padding:30px;">
                    Henüz sinyal verisi bulunamadı.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = signals.map((row, index) => {
        const s = normalizeSignal(row);
        const cls = signalClass(s.signal);

        return `
            <tr data-ticker="${escapeHtml(s.ticker)}">
                <td>${index + 1}</td>

                <td>
                    <strong>${escapeHtml(s.ticker)}</strong>
                </td>

                <td>
                    <span class="signal-badge ${cls}">
                        ${escapeHtml(s.signal)}
                    </span>
                </td>

                <td>
                    ${formatPercent(s.probability)}
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
                    ${escapeHtml(String(s.date))}
                </td>

                <td>
                    <button
                        class="signal-detail-btn"
                        onclick="openSignal('${escapeJs(s.ticker)}')"
                    >
                        Detay
                    </button>
                </td>
            </tr>
        `;
    }).join("");
}

/* =========================================================
   HTML GÜVENLİK
   ========================================================= */

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function escapeJs(value) {
    return String(value)
        .replaceAll("\\", "\\\\")
        .replaceAll("'", "\\'")
        .replaceAll("\n", "\\n")
        .replaceAll("\r", "\\r");
}

/* =========================================================
   KPI
   ========================================================= */

function updateKPIs(signals) {
    let buy = 0;
    let sell = 0;
    let hold = 0;

    for (const row of signals) {
        const s = normalizeSignal(row);

        if (s.signal === "BUY") buy++;
        else if (s.signal === "SELL") sell++;
        else hold++;
    }

    setText("buyCount", buy.toLocaleString("tr-TR"));
    setText("sellCount", sell.toLocaleString("tr-TR"));
    setText("holdCount", hold.toLocaleString("tr-TR"));
    setText("topCount", Math.min(20, signals.length).toLocaleString("tr-TR"));
    setText("totalCount", signals.length.toLocaleString("tr-TR"));
    setText("signalCount", signals.length.toLocaleString("tr-TR"));
}

/* =========================================================
   ARAMA
   ========================================================= */

function filterSignals() {
    const input =
        document.getElementById("signalSearch") ||
        document.getElementById("searchInput");

    if (!input) return;

    const query = input.value.trim().toLowerCase();

    if (!query) {
        filteredSignals = allSignals;
        renderSignals(allSignals);
        return;
    }

    filteredSignals = allSignals.filter(row => {
        const s = normalizeSignal(row);

        return (
            String(s.ticker).toLowerCase().includes(query) ||
            String(s.signal).toLowerCase().includes(query)
        );
    });

    renderSignals(filteredSignals);
}

function searchSignals() {
    filterSignals();
}

/* =========================================================
   ANA VERİ YENİLEME
   ========================================================= */

async function refreshData() {
    try {
        await Promise.all([
            loadSignals(),
            loadStatus()
        ]);
    } catch (error) {
        console.error("Refresh error:", error);
    }
}

/* =========================================================
   SİSTEM DURUMU
   ========================================================= */

async function loadStatus() {
    try {
        const response = await publicFetch("/api/status");

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await readJson(response);

        const running =
            data.running ??
            data.status === "running" ??
            false;

        if (running === true) {
            setText("systemStatus", "ÇALIŞIYOR");
        } else {
            setText("systemStatus", "HAZIR");
        }

        if (data.last_update) {
            setText("lastUpdate", data.last_update);
        }

        if (data.updated_at) {
            setText("lastUpdate", data.updated_at);
        }

        return data;
    } catch (error) {
        console.error("Status error:", error);
        setText("systemStatus", "BAĞLANTI BEKLENİYOR");
        return null;
    }
}

/* =========================================================
   ANALİZ BAŞLAT
   ========================================================= */

async function runAnalysis() {
    const buttons = document.querySelectorAll(
        "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
    );

    buttons.forEach(btn => {
        btn.disabled = true;
        btn.dataset.oldText = btn.textContent;
        btn.textContent = "Analiz Başlatılıyor...";
    });

    try {
        const response = await publicFetch("/api/run", {
            method: "POST",
            body: JSON.stringify({})
        });

        const data = await readJson(response);

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        showToast(
            data.message || "Analiz başlatıldı.",
            "success"
        );

        monitorRun();

    } catch (error) {
        console.error("Run error:", error);

        showToast(
            error.message || "Analiz başlatılamadı.",
            "error"
        );

        buttons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.dataset.oldText || "Analizi Başlat";
        });
    }
}

/* =========================================================
   ANALİZ DURUMU
   ========================================================= */

async function monitorRun() {
    if (runPollTimer) {
        clearInterval(runPollTimer);
    }

    let attempts = 0;

    async function check() {
        attempts++;

        try {
            const response = await publicFetch("/api/run-status");
            const data = await readJson(response);

            const running =
                data.running === true ||
                data.status === "running";

            if (running) {
                setText("systemStatus", "ANALİZ ÇALIŞIYOR");

                const progress =
                    data.progress ??
                    data.percent ??
                    data.message ??
                    "";

                if (progress) {
                    setText("analysisProgress", String(progress));
                }

                return;
            }

            clearInterval(runPollTimer);
            runPollTimer = null;

            setText("systemStatus", "HAZIR");

            const buttons = document.querySelectorAll(
                "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
            );

            buttons.forEach(btn => {
                btn.disabled = false;
                btn.textContent =
                    btn.dataset.oldText ||
                    "Analizi Başlat";
            });

            await refreshData();

            if (
                data.error ||
                data.status === "error"
            ) {
                showToast(
                    data.error || "Analiz sırasında hata oluştu.",
                    "error"
                );
            } else {
                showToast(
                    "Analiz tamamlandı.",
                    "success"
                );
            }

        } catch (error) {
            console.error("Run status error:", error);

            if (attempts >= 10) {
                clearInterval(runPollTimer);
                runPollTimer = null;

                const buttons = document.querySelectorAll(
                    "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
                );

                buttons.forEach(btn => {
                    btn.disabled = false;
                    btn.textContent =
                        btn.dataset.oldText ||
                        "Analizi Başlat";
                });
            }
        }
    }

    await check();

    runPollTimer = setInterval(check, 3000);
}

/* =========================================================
   HİSSE DETAY
   ========================================================= */

async function openSignal(ticker) {
    if (!ticker) return;

    try {
        const response = await publicFetch(
            `/api/signal/${encodeURIComponent(ticker)}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await readJson(response);

        renderAdvancedResult(
            "Hisse Analizi",
            data
        );

        const section =
            document.getElementById("advancedResults") ||
            document.getElementById("advancedResult");

        if (section) {
            section.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        }

    } catch (error) {
        console.error("Signal detail error:", error);

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
    const resultBox =
        document.getElementById("advancedResults") ||
        document.getElementById("backtestResult");

    if (resultBox) {
        resultBox.innerHTML = `
            <div class="loading">
                Backtest çalıştırılıyor...
            </div>
        `;
    }

    try {
        const response = await publicFetch("/api/backtest");

        const data = await readJson(response);

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
        console.error("Backtest error:", error);

        renderAdvancedResult(
            "Backtest",
            {
                error: error.message || "Backtest alınamadı."
            }
        );

        return null;
    }
}

/* =========================================================
   PAPER TRADING
   ========================================================= */

async function loadPaper() {
    const resultBox =
        document.getElementById("advancedResults") ||
        document.getElementById("paperResult");

    if (resultBox) {
        resultBox.innerHTML = `
            <div class="loading">
                Paper Trading verileri yükleniyor...
            </div>
        `;
    }

    try {
        const response = await publicFetch("/api/paper");

        const data = await readJson(response);

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
        console.error("Paper error:", error);

        renderAdvancedResult(
            "Paper Trading",
            {
                error: error.message || "Paper Trading verisi alınamadı."
            }
        );

        return null;
    }
}

/* =========================================================
   MONTE CARLO
   ========================================================= */

async function loadMonteCarlo() {
    const resultBox =
        document.getElementById("advancedResults") ||
        document.getElementById("monteCarloResult");

    if (resultBox) {
        resultBox.innerHTML = `
            <div class="loading">
                Monte Carlo analizi çalıştırılıyor...
            </div>
        `;
    }

    try {
        const response = await publicFetch("/api/montecarlo");

        const data = await readJson(response);

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
        console.error("Monte Carlo error:", error);

        renderAdvancedResult(
            "Monte Carlo",
            {
                error: error.message || "Monte Carlo verisi alınamadı."
            }
        );

        return null;
    }
}

/* =========================================================
   GELİŞMİŞ AI
   ========================================================= */

async function loadAdvancedAI() {
    try {
        const response = await publicFetch("/api/metrics");

        const data = await readJson(response);

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Gelişmiş AI / Metrikler",
            data
        );

        return data;

    } catch (error) {
        console.error("Advanced AI error:", error);

        renderAdvancedResult(
            "Gelişmiş AI",
            {
                error: error.message || "AI metrikleri alınamadı."
            }
        );

        return null;
    }
}

/* =========================================================
   GELİŞMİŞ SONUÇ GÖSTERİMİ
   ========================================================= */

function renderAdvancedResult(title, data) {
    const box =
        document.getElementById("advancedResults") ||
        document.getElementById("advancedResult");

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
                <p>${escapeHtml(String(data.error))}</p>
            </div>
        `;
        return;
    }

    const entries = [];

    function walk(obj, prefix = "") {
        if (obj === null || obj === undefined) return;

        if (
            typeof obj === "string" ||
            typeof obj === "number" ||
            typeof obj === "boolean"
        ) {
            entries.push([
                prefix,
                String(obj)
            ]);
            return;
        }

        if (Array.isArray(obj)) {
            entries.push([
                prefix || "Sonuç",
                `${obj.length} kayıt`
            ]);

            return;
        }

        if (typeof obj === "object") {
            for (const [key, value] of Object.entries(obj)) {
                const label = prefix
                    ? `${prefix} / ${key}`
                    : key;

                if (
                    value !== null &&
                    typeof value === "object" &&
                    !Array.isArray(value)
                ) {
                    walk(value, label);
                } else if (Array.isArray(value)) {
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
            }
        }
    }

    walk(data);

    const limitedEntries = entries.slice(0, 100);

    box.innerHTML = `
        <div class="advanced-result">
            <h3>${escapeHtml(title)}</h3>

            <div class="advanced-result-grid">
                ${
                    limitedEntries.length
                        ? limitedEntries.map(([key, value]) => `
                            <div class="advanced-item">
                                <div class="advanced-key">
                                    ${escapeHtml(key)}
                                </div>

                                <div class="advanced-value">
                                    ${escapeHtml(String(value))}
                                </div>
                            </div>
                        `).join("")
                        : `
                            <div class="advanced-item">
                                Sonuç verisi bulunamadı.
                            </div>
                        `
                }
            </div>
        </div>
    `;
}

/* =========================================================
   METRİKLER
   ========================================================= */

async function loadMetrics() {
    try {
        const response = await publicFetch("/api/metrics");
        const data = await readJson(response);

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Sistem Metrikleri",
            data
        );

        return data;

    } catch (error) {
        console.error("Metrics error:", error);
        return null;
    }
}

/* =========================================================
   DEBUG
   ========================================================= */

async function loadDebugData() {
    try {
        const response = await publicFetch("/api/debug/data");
        const data = await readJson(response);

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                `HTTP ${response.status}`
            );
        }

        renderAdvancedResult(
            "Veri Durumu",
            data
        );

        return data;

    } catch (error) {
        console.error("Debug data error:", error);
        return null;
    }
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
        await publicFetch("/api/logout", {
            method: "POST",
            body: JSON.stringify({})
        });
    } catch (e) {
        console.warn("Logout:", e);
    }

    // Normal kullanıcı zaten oturumsuz çalışıyor.
    showAppScreen();
}

/* =========================================================
   AUTH FORM ESKİ FONKSİYONLARI
   ÇAKILMAMASI İÇİN BOŞ / UYUMLU BIRAKILDI
   ========================================================= */

async function loginUser(event) {
    if (event) {
        event.preventDefault();
    }

    showToast(
        "LEVEL 1000 artık üyelik gerektirmeden kullanılabilir.",
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
        "Kayıt gerekli değil. Siteyi doğrudan kullanabilirsiniz.",
        "info"
    );

    showAppScreen();
    return true;
}

/* =========================================================
   KEYBOARD
   ========================================================= */

document.addEventListener("keydown", function(event) {
    if (
        event.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
    ) {
        event.preventDefault();

        const search =
            document.getElementById("signalSearch") ||
            document.getElementById("searchInput");

        if (search) {
            search.focus();
        }
    }
});

/* =========================================================
   EVENT LISTENERS
   ========================================================= */

function setupEvents() {

    const search =
        document.getElementById("signalSearch") ||
        document.getElementById("searchInput");

    if (search) {
        search.addEventListener("input", filterSignals);
    }

    const runButtons = document.querySelectorAll(
        "#runAnalysisBtn, .run-analysis-btn, [data-action='run-analysis']"
    );

    runButtons.forEach(btn => {
        btn.addEventListener("click", function(event) {
            event.preventDefault();
            runAnalysis();
        });
    });

    const backtestButtons = document.querySelectorAll(
        "#backtestBtn, [data-action='backtest']"
    );

    backtestButtons.forEach(btn => {
        btn.addEventListener("click", function(event) {
            event.preventDefault();
            loadBacktest();
        });
    });

    const paperButtons = document.querySelectorAll(
        "#paperBtn, [data-action='paper']"
    );

    paperButtons.forEach(btn => {
        btn.addEventListener("click", function(event) {
            event.preventDefault();
            loadPaper();
        });
    });

    const monteCarloButtons = document.querySelectorAll(
        "#monteCarloBtn, [data-action='montecarlo']"
    );

    monteCarloButtons.forEach(btn => {
        btn.addEventListener("click", function(event) {
            event.preventDefault();
            loadMonteCarlo();
        });
    });

    const advancedButtons = document.querySelectorAll(
        "#advancedAIBtn, [data-action='advanced-ai']"
    );

    advancedButtons.forEach(btn => {
        btn.addEventListener("click", function(event) {
            event.preventDefault();
            loadAdvancedAI();
        });
    });
}

/* =========================================================
   BAŞLANGIÇ
   ========================================================= */

document.addEventListener("DOMContentLoaded", async function() {

    // Public uygulama her zaman açık.
    showAppScreen();

    setupEvents();

    await refreshData();

    // 30 saniyede bir verileri yenile.
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }

    refreshTimer = setInterval(() => {
        refreshData();
    }, 30000);
});

/* =========================================================
   GLOBAL
   Eski HTML / inline onclick uyumluluğu
   ========================================================= */

window.loadSignals = loadSignals;
window.renderSignals = renderSignals;
window.filterSignals = filterSignals;
window.searchSignals = searchSignals;

window.refreshData = refreshData;
window.loadStatus = loadStatus;

window.runAnalysis = runAnalysis;
window.monitorRun = monitorRun;

window.loadBacktest = loadBacktest;
window.loadPaper = loadPaper;
window.loadMonteCarlo = loadMonteCarlo;
window.loadAdvancedAI = loadAdvancedAI;
window.loadMetrics = loadMetrics;
window.loadDebugData = loadDebugData;

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

window.renderAdvancedResult = renderAdvancedResult;