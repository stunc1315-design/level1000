"use strict";

/* ============================================================
   LEVEL 1000 AI TERMINAL
   SCRIPT.JS
   AUTH + JWT + PLAN + DASHBOARD + SIGNALS
   FREE / PRO / MAX PRO
   CANLI FİYAT + GERÇEK GÜNLÜK DEĞİŞİM
   ============================================================ */

let allSignals = [];
let currentUser = null;
let currentPlan = "FREE";
let currentPlanData = null;

let scanRunning = false;
let scanUsed = 0;
let scanLimit = 3;
let scanRemaining = 3;

const TOKEN_KEY = "level1000_token";
const USER_KEY = "level1000_user";


/* ============================================================
   HELPERS
   ============================================================ */

function $(id) {
    return document.getElementById(id);
}

function sleep(ms) {
    return new Promise(function(resolve) {
        setTimeout(resolve, ms);
    });
}

function setText(id, value) {
    const element = $(id);

    if (element) {
        element.innerText = value;
    }
}


/* ============================================================
   TOKEN
   ============================================================ */

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    if (token) {
        localStorage.setItem(TOKEN_KEY, token);
    } else {
        localStorage.removeItem(TOKEN_KEY);
    }
}


/* ============================================================
   USER STORAGE
   ============================================================ */

function getSavedUser() {
    try {
        const raw = localStorage.getItem(USER_KEY);

        if (!raw) {
            return null;
        }

        return JSON.parse(raw);
    } catch (error) {
        console.error("USER STORAGE:", error);
        return null;
    }
}

function saveUser(user) {
    if (!user) {
        localStorage.removeItem(USER_KEY);
        return;
    }

    localStorage.setItem(
        USER_KEY,
        JSON.stringify(user)
    );
}


/* ============================================================
   API
   ============================================================ */

async function apiFetch(url, options) {
    options = options || {};

    const requestOptions = Object.assign({}, options);
    const headers = Object.assign(
        {},
        requestOptions.headers || {}
    );

    const token = getToken();

    if (token) {
        headers["Authorization"] = "Bearer " + token;
    }

    if (
        requestOptions.body &&
        typeof requestOptions.body !== "string"
    ) {
        headers["Content-Type"] = "application/json";
        requestOptions.body = JSON.stringify(
            requestOptions.body
        );
    }

    requestOptions.headers = headers;

    let response;

    try {
        response = await fetch(
            url,
            requestOptions
        );
    } catch (error) {
        console.error("API CONNECTION:", error);

        throw new Error(
            "Sunucuya bağlanılamadı."
        );
    }

    let data = null;

    try {
        data = await response.json();
    } catch (error) {
        data = null;
    }

    if (response.status === 401) {
        if (url !== "/api/login") {
            clearSession();
            showAuthScreen();
            showLogin();
        }

        throw new Error(
            data && (
                data.detail ||
                data.message
            )
                ? (
                    data.detail ||
                    data.message
                )
                : "Oturum geçersiz."
        );
    }

    if (!response.ok) {
        const message =
            data && (
                data.detail ||
                data.error ||
                data.message
            )
                ? (
                    data.detail ||
                    data.error ||
                    data.message
                )
                : "API hatası: " + response.status;

        const error = new Error(message);

        error.status = response.status;
        error.data = data;

        throw error;
    }

    return data;
}


/* ============================================================
   SCREEN
   ============================================================ */

function showAuthScreen() {
    const auth = $("authScreen");
    const app = $("appScreen");

    if (auth) {
        auth.style.display = "flex";
    }

    if (app) {
        app.style.display = "none";
    }
}

function showAppScreen() {
    const auth = $("authScreen");
    const app = $("appScreen");

    if (auth) {
        auth.style.display = "none";
    }

    if (app) {
        app.style.display = "block";
    }
}


/* ============================================================
   LOGIN / REGISTER SCREEN
   ============================================================ */

function showLogin() {
    const login = $("loginBox");
    const register = $("registerBox");

    if (login) {
        login.style.display = "block";
    }

    if (register) {
        register.style.display = "none";
    }

    clearAuthMessage();
}

function showRegister() {
    const login = $("loginBox");
    const register = $("registerBox");

    if (login) {
        login.style.display = "none";
    }

    if (register) {
        register.style.display = "block";
    }

    clearAuthMessage();
}


/* ============================================================
   MESSAGES
   ============================================================ */

function showAuthMessage(text, type) {
    type = type || "error";

    const box = $("authMessage");

    if (!box) {
        return;
    }

    box.innerText = text || "";
    box.style.display = "block";
    box.className = "auth-message " + type;
}

function clearAuthMessage() {
    const box = $("authMessage");

    if (!box) {
        return;
    }

    box.innerText = "";
    box.style.display = "none";
}

function showMessage(text, type) {
    type = type || "info";

    const box = $("message");

    if (!box) {
        return;
    }

    box.innerText = text || "";
    box.style.display = "block";
    box.className = "message " + type;

    setTimeout(function() {
        box.style.display = "none";
    }, 5000);
}


/* ============================================================
   LOGIN
   ============================================================ */

async function loginUser() {
    clearAuthMessage();

    const emailInput = $("loginEmail");
    const passwordInput = $("loginPassword");

    const email = emailInput
        ? emailInput.value.trim().toLowerCase()
        : "";

    const password = passwordInput
        ? passwordInput.value
        : "";

    if (!email) {
        showAuthMessage(
            "E-posta adresinizi girin."
        );
        return;
    }

    if (!password) {
        showAuthMessage(
            "Şifrenizi girin."
        );
        return;
    }

    const button = document.querySelector(
        "#loginBox .auth-button"
    );

    if (button) {
        button.disabled = true;
        button.innerText = "GİRİŞ YAPILIYOR...";
    }

    try {
        setToken(null);

        const data = await apiFetch(
            "/api/login",
            {
                method: "POST",
                body: {
                    email: email,
                    password: password
                }
            }
        );

        if (!data || data.ok !== true) {
            throw new Error(
                data && (
                    data.message ||
                    data.detail
                )
                    ? (
                        data.message ||
                        data.detail
                    )
                    : "Giriş başarısız."
            );
        }

        const token =
            data.access_token ||
            data.token;

        if (!token) {
            throw new Error(
                "Sunucu token döndürmedi."
            );
        }

        setToken(token);

        if (data.user) {
            currentUser = data.user;
            saveUser(data.user);
        } else {
            const me = await apiFetch("/api/me");

            if (me && me.ok && me.user) {
                currentUser = me.user;
                saveUser(me.user);
            }
        }

        showAppScreen();
        updateUserUI(currentUser);

        await refreshData();

        showMessage(
            "Giriş başarılı.",
            "success"
        );

    } catch (error) {
        console.error("LOGIN:", error);

        setToken(null);

        showAuthMessage(
            error.message ||
            "Giriş yapılamadı."
        );

    } finally {
        if (button) {
            button.disabled = false;
            button.innerText = "GİRİŞ YAP";
        }
    }
}


/* ============================================================
   REGISTER
   ============================================================ */

async function registerUser() {
    clearAuthMessage();

    const emailInput = $("registerEmail");
    const passwordInput = $("registerPassword");
    const password2Input = $("registerPassword2");

    const email = emailInput
        ? emailInput.value.trim().toLowerCase()
        : "";

    const password = passwordInput
        ? passwordInput.value
        : "";

    const password2 = password2Input
        ? password2Input.value
        : "";

    const name = email
        ? email.split("@")[0]
        : "";

    if (!email) {
        showAuthMessage(
            "E-posta adresinizi girin."
        );
        return;
    }

    if (password.length < 8) {
        showAuthMessage(
            "Şifre en az 8 karakter olmalıdır."
        );
        return;
    }

    if (password !== password2) {
        showAuthMessage(
            "Şifreler aynı değil."
        );
        return;
    }

    const button = document.querySelector(
        "#registerBox .auth-button"
    );

    if (button) {
        button.disabled = true;
        button.innerText =
            "HESAP OLUŞTURULUYOR...";
    }

    try {
        setToken(null);

        const data = await apiFetch(
            "/api/register",
            {
                method: "POST",
                body: {
                    name: name,
                    email: email,
                    password: password
                }
            }
        );

        if (!data || data.ok !== true) {
            throw new Error(
                data && (
                    data.message ||
                    data.detail
                )
                    ? (
                        data.message ||
                        data.detail
                    )
                    : "Kayıt başarısız."
            );
        }

        const token =
            data.access_token ||
            data.token;

        if (!token) {
            throw new Error(
                "Kayıt başarılı fakat token alınamadı."
            );
        }

        setToken(token);

        if (data.user) {
            currentUser = data.user;
            saveUser(data.user);
        } else {
            const me = await apiFetch("/api/me");

            if (me && me.ok && me.user) {
                currentUser = me.user;
                saveUser(me.user);
            }
        }

        showAppScreen();
        updateUserUI(currentUser);

        await refreshData();

        showMessage(
            "Hesabınız oluşturuldu.",
            "success"
        );

    } catch (error) {
        console.error("REGISTER:", error);

        setToken(null);

        showAuthMessage(
            error.message ||
            "Kayıt oluşturulamadı."
        );

    } finally {
        if (button) {
            button.disabled = false;
            button.innerText = "HESAP OLUŞTUR";
        }
    }
}


/* ============================================================
   LOGOUT
   ============================================================ */

async function logoutUser() {
    const token = getToken();

    try {
        if (token) {
            await fetch(
                "/api/logout",
                {
                    method: "POST",
                    headers: {
                        "Authorization":
                            "Bearer " + token
                    }
                }
            );
        }
    } catch (error) {
        console.warn("LOGOUT:", error);
    }

    clearSession();
    showAuthScreen();
    showLogin();
}


/* ============================================================
   SESSION
   ============================================================ */

function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    allSignals = [];
    currentUser = null;
    currentPlan = "FREE";
    currentPlanData = null;

    scanRunning = false;
    scanUsed = 0;
    scanLimit = 3;
    scanRemaining = 3;

    updateScanUI();
}

async function checkSession() {
    const token = getToken();

    if (!token) {
        showAuthScreen();
        showLogin();
        return false;
    }

    try {
        const data = await apiFetch("/api/me");

        if (
            data &&
            data.ok &&
            data.user
        ) {
            currentUser = data.user;

            saveUser(data.user);
            updateUserUI(data.user);
            showAppScreen();

            await refreshData();

            return true;
        }
    } catch (error) {
        console.warn(
            "SESSION:",
            error.message
        );
    }

    clearSession();
    showAuthScreen();
    showLogin();

    return false;
}


/* ============================================================
   USER UI
   ============================================================ */

function updateUserUI(user) {
    if (!user) {
        return;
    }

    currentUser = user;

    const emailElement =
        document.querySelector(".user-email");

    const planElement =
        document.querySelector(".user-plan");

    if (emailElement) {
        emailElement.innerText =
            user.email || "Kullanıcı";
    }

    const plan = normalizePlan(user.plan);

    if (planElement) {
        planElement.innerText = plan;
    }

    const adminButton =
        document.querySelector(".admin-button");

    if (adminButton) {
        adminButton.style.display =
            user.is_admin
                ? "inline-block"
                : "none";
    }

    updatePlanUI(plan);
    updateScanUI();
}


/* ============================================================
   PLAN
   ============================================================ */

function normalizePlan(plan) {
    const value = String(
        plan || "FREE"
    )
        .trim()
        .toUpperCase()
        .replace(/[_-]+/g, " ")
        .replace(/\s+/g, " ");

    if (
        value === "MAX PRO" ||
        value === "MAXPRO"
    ) {
        return "MAX PRO";
    }

    if (value === "PRO") {
        return "PRO";
    }

    return "FREE";
}

function getPlanLevel(plan) {
    const value = normalizePlan(plan);

    if (value === "MAX PRO") {
        return 3;
    }

    if (value === "PRO") {
        return 2;
    }

    return 1;
}

function getFrontendPlanConfig(plan) {
    plan = normalizePlan(plan);

    if (plan === "MAX PRO") {
        return {
            name: "MAX PRO",
            level: 3,
            displayLimit: 300,
            scanLimit: Infinity,
            scanText: "SINIRSIZ"
        };
    }

    if (plan === "PRO") {
        return {
            name: "PRO",
            level: 2,
            displayLimit: 100,
            scanLimit: 30,
            scanText: "30"
        };
    }

    return {
        name: "FREE",
        level: 1,
        displayLimit: 20,
        scanLimit: 3,
        scanText: "3"
    };
}


/* ============================================================
   PLAN API
   ============================================================ */

async function loadPlan() {
    try {
        const data = await apiFetch("/api/plan");

        if (!data) {
            return null;
        }

        currentPlan = normalizePlan(
            data.plan ||
            data.name ||
            data.current_plan ||
            (
                currentUser
                    ? currentUser.plan
                    : "FREE"
            )
        );

        currentPlanData = data;

        updateScanData(data);

        if (currentUser) {
            currentUser.plan = currentPlan;

            if (data.scans_used !== undefined) {
                currentUser.scans_used =
                    data.scans_used;
            }

            if (
                data.scans_remaining !==
                undefined
            ) {
                currentUser.scans_remaining =
                    data.scans_remaining;
            }

            saveUser(currentUser);
        }

        updatePlanUI(currentPlan);

        return data;

    } catch (error) {
        console.warn(
            "PLAN:",
            error.message
        );

        const savedUser = getSavedUser();

        currentPlan = normalizePlan(
            savedUser && savedUser.plan
                ? savedUser.plan
                : currentUser && currentUser.plan
                    ? currentUser.plan
                    : "FREE"
        );

        updatePlanUI(currentPlan);

        return null;
    }
}


/* ============================================================
   SCAN DATA
   ============================================================ */

function updateScanData(data) {
    if (!data) {
        return;
    }

    const plan = normalizePlan(
        data.plan ||
        data.current_plan ||
        currentPlan
    );

    currentPlan = plan;

    if (plan === "MAX PRO") {
        scanLimit = Infinity;

        scanUsed = Number(
            data.scans_used ??
            data.scan_count ??
            0
        );

        if (!Number.isFinite(scanUsed)) {
            scanUsed = 0;
        }

        scanRemaining = Infinity;

        updateScanUI();
        return;
    }

    scanLimit = Number(
        data.scan_limit ??
        data.free_scan_limit ??
        (
            plan === "PRO"
                ? 30
                : 3
        )
    );

    if (
        !Number.isFinite(scanLimit) ||
        scanLimit < 0
    ) {
        scanLimit =
            plan === "PRO"
                ? 30
                : 3;
    }

    scanUsed = Number(
        data.scans_used ??
        data.scan_count ??
        0
    );

    if (
        !Number.isFinite(scanUsed) ||
        scanUsed < 0
    ) {
        scanUsed = 0;
    }

    if (
        data.scans_remaining !==
        undefined
    ) {
        scanRemaining = Number(
            data.scans_remaining
        );
    } else {
        scanRemaining = Math.max(
            0,
            scanLimit - scanUsed
        );
    }

    if (
        !Number.isFinite(scanRemaining)
    ) {
        scanRemaining = Math.max(
            0,
            scanLimit - scanUsed
        );
    }

    updateScanUI();
}


/* ============================================================
   SCAN UI
   ============================================================ */

function updateScanUI() {
    const plan = normalizePlan(currentPlan);

    const remainingElements = [
        $("scanRemaining"),
        $("scansRemaining"),
        $("freeScansRemaining")
    ].filter(Boolean);

    const usedElements = [
        $("scanUsed"),
        $("scansUsed"),
        $("freeScansUsed")
    ].filter(Boolean);

    const limitElements = [
        $("scanLimit"),
        $("scansLimit"),
        $("freeScanLimit")
    ].filter(Boolean);

    const scanButton =
        $("runScanButton") ||
        $("scanButton") ||
        $("startScanButton") ||
        $("runAnalysisButton");

    if (plan === "MAX PRO") {
        remainingElements.forEach(
            function(element) {
                element.innerText = "SINIRSIZ";
            }
        );

        usedElements.forEach(
            function(element) {
                element.innerText =
                    formatInteger(scanUsed);
            }
        );

        limitElements.forEach(
            function(element) {
                element.innerText = "SINIRSIZ";
            }
        );

        if (scanButton) {
            scanButton.disabled = scanRunning;

            scanButton.classList.remove(
                "scan-limit-reached"
            );

            scanButton.innerText =
                scanRunning
                    ? "ANALİZ ÇALIŞIYOR..."
                    : "ANALİZİ BAŞLAT";
        }

        return;
    }

    remainingElements.forEach(
        function(element) {
            element.innerText =
                formatInteger(
                    Math.max(
                        0,
                        scanRemaining
                    )
                );
        }
    );

    usedElements.forEach(
        function(element) {
            element.innerText =
                formatInteger(scanUsed);
        }
    );

    limitElements.forEach(
        function(element) {
            element.innerText =
                formatInteger(scanLimit);
        }
    );

    if (scanButton) {
        const noScanLeft =
            scanRemaining <= 0;

        scanButton.disabled =
            scanRunning ||
            noScanLeft;

        scanButton.classList.toggle(
            "scan-limit-reached",
            noScanLeft
        );

        if (scanRunning) {
            scanButton.innerText =
                "ANALİZ ÇALIŞIYOR...";
        } else if (noScanLeft) {
            scanButton.innerText =
                "TARAMA HAKKI BİTTİ";
        } else {
            scanButton.innerText =
                "ANALİZİ BAŞLAT (" +
                scanRemaining +
                " HAK)";
        }
    }
}


/* ============================================================
   RUN ANALYSIS
   ============================================================ */

async function runAnalysis() {
    if (!getToken()) {
        showMessage(
            "Önce giriş yapmalısınız.",
            "error"
        );

        showAuthScreen();
        return;
    }

    if (scanRunning) {
        showMessage(
            "Analiz zaten çalışıyor.",
            "info"
        );

        return;
    }

    const plan = normalizePlan(currentPlan);

    if (
        plan !== "MAX PRO" &&
        scanRemaining <= 0
    ) {
        showMessage(
            plan +
            " planındaki tarama hakkınız bitti.",
            "error"
        );

        if (plan === "FREE") {
            openPlanModal(
                "PRO",
                "Daha fazla tarama"
            );
        }

        updateScanUI();
        return;
    }

    scanRunning = true;
    updateScanUI();

    showMessage(
        "Analiz başlatılıyor...",
        "info"
    );

    try {
        const data = await apiFetch(
            "/api/run",
            {
                method: "POST"
            }
        );

        if (!data || data.ok !== true) {
            throw new Error(
                data && (
                    data.detail ||
                    data.error ||
                    data.message
                )
                    ? (
                        data.detail ||
                        data.error ||
                        data.message
                    )
                    : "Analiz başlatılamadı."
            );
        }

        if (
            data.scans_used !== undefined ||
            data.scans_remaining !== undefined
        ) {
            updateScanData({
                ...data,
                plan:
                    data.plan ||
                    currentPlan
            });
        } else if (plan !== "MAX PRO") {
            scanUsed += 1;

            scanRemaining = Math.max(
                0,
                scanLimit - scanUsed
            );

            updateScanUI();
        }

        showMessage(
            data.message ||
            "Analiz başlatıldı.",
            "success"
        );

        await monitorRunStatus();

    } catch (error) {
        console.error(
            "RUN ANALYSIS:",
            error
        );

        if (error.status === 403) {
            showMessage(
                (
                    error.data &&
                    error.data.detail
                )
                    ? error.data.detail
                    : error.message ||
                        "Tarama hakkınız kalmadı.",
                "error"
            );

            if (
                error.data &&
                error.data.scans_remaining !==
                undefined
            ) {
                updateScanData({
                    ...error.data,
                    plan: currentPlan
                });
            }

            if (
                normalizePlan(currentPlan) ===
                "FREE"
            ) {
                openPlanModal(
                    "PRO",
                    "Daha fazla tarama"
                );
            }

        } else {
            showMessage(
                error.message ||
                "Analiz başlatılamadı.",
                "error"
            );
        }

    } finally {
        scanRunning = false;
        updateScanUI();

        setTimeout(
            function() {
                refreshData();
            },
            1000
        );
    }
}


/* ============================================================
   RUN STATUS
   ============================================================ */

async function getRunStatus() {
    try {
        return await apiFetch(
            "/api/run-status"
        );
    } catch (error) {
        console.warn(
            "RUN STATUS:",
            error
        );

        return null;
    }
}

async function monitorRunStatus() {
    const maxChecks = 360;
    let checks = 0;

    while (checks < maxChecks) {
        checks++;

        const data =
            await getRunStatus();

        if (!data) {
            await sleep(3000);
            continue;
        }

        const running = Boolean(
            data.running ??
            (
                data.status ===
                "RUNNING"
            )
        );

        if (!running) {
            if (
                data.scans_used !==
                undefined ||
                data.scans_remaining !==
                undefined
            ) {
                updateScanData({
                    ...data,
                    plan:
                        data.plan ||
                        currentPlan
                });
            }

            await refreshData();

            return data;
        }

        const statusElements =
            document.querySelectorAll(
                ".status-value"
            );

        statusElements.forEach(
            function(element) {
                element.innerText =
                    data.message ||
                    data.status ||
                    "ANALİZ ÇALIŞIYOR...";
            }
        );

        await sleep(3000);
    }

    return null;
}


/* ============================================================
   PLAN UI
   ============================================================ */

function updatePlanUI(plan) {
    plan = normalizePlan(plan);
    currentPlan = plan;

    if (
        document.documentElement &&
        document.documentElement.dataset
    ) {
        document.documentElement.dataset.plan =
            plan;
    }

    const planElement =
        document.querySelector(
            ".user-plan"
        );

    if (planElement) {
        planElement.innerText = plan;
    }

    setText(
        "currentPlanText",
        plan
    );

    const planInfoBar =
        $("planInfoBar");

    if (planInfoBar) {
        planInfoBar.style.display =
            "flex";
    }

    const plansSection =
        document.querySelector(
            ".plans-section"
        );

    if (plansSection) {
        plansSection.style.display =
            "block";
    }

    const freeButton =
        $("freePlanButton");

    const proButton =
        $("proPlanButton");

    const maxButton =
        $("maxProPlanButton");

    if (freeButton) {
        freeButton.innerText =
            plan === "FREE"
                ? "AKTİF"
                : "FREE";
    }

    if (proButton) {
        proButton.innerText =
            plan === "PRO"
                ? "AKTİF"
                : "PRO'YA GEÇ";
    }

    if (maxButton) {
        maxButton.innerText =
            plan === "MAX PRO"
                ? "AKTİF"
                : "MAX PRO'YA GEÇ";
    }

    const upgrade =
        $("upgradePlanButton");

    if (upgrade) {
        if (plan === "FREE") {
            upgrade.innerText =
                "PRO'YA GEÇ";

            upgrade.style.display =
                "inline-block";

            upgrade.onclick =
                function() {
                    selectPlan("PRO");
                };

        } else if (plan === "PRO") {
            upgrade.innerText =
                "MAX PRO'YA GEÇ";

            upgrade.style.display =
                "inline-block";

            upgrade.onclick =
                function() {
                    selectPlan("MAX PRO");
                };

        } else {
            upgrade.style.display = "none";
        }
    }

    const cards = [
        $("planCardFree"),
        $("planCardPro"),
        $("planCardMaxPro")
    ];

    cards.forEach(
        function(card) {
            if (!card) {
                return;
            }

            card.classList.remove(
                "active-plan",
                "active"
            );
        }
    );

    if (plan === "FREE" && cards[0]) {
        cards[0].classList.add(
            "active-plan"
        );
    }

    if (plan === "PRO" && cards[1]) {
        cards[1].classList.add(
            "active-plan"
        );
    }

    if (plan === "MAX PRO" && cards[2]) {
        cards[2].classList.add(
            "active-plan"
        );
    }

    updateLockedFeatures();
    updateScanUI();
}


/* ============================================================
   LOCKED FEATURES
   ============================================================ */

function updateLockedFeatures() {
    const elements =
        document.querySelectorAll(
            "[data-required-plan]"
        );

    const userLevel =
        getPlanLevel(currentPlan);

    elements.forEach(
        function(element) {
            const requiredPlan =
                normalizePlan(
                    element.dataset.requiredPlan
                );

            const requiredLevel =
                getPlanLevel(
                    requiredPlan
                );

            const allowed =
                userLevel >= requiredLevel;

            if (allowed) {
                element.classList.remove(
                    "locked",
                    "locked-feature"
                );
            } else {
                element.classList.add(
                    "locked",
                    "locked-feature"
                );

                element.dataset.originalLocked =
                    "true";
            }

            const value =
                element.querySelector(
                    ".card-value"
                );

            if (value) {
                value.innerText =
                    allowed
                        ? "AKTİF"
                        : "🔒 " + requiredPlan;
            }

            const lock =
                element.querySelector(
                    ".feature-lock"
                );

            if (lock) {
                lock.innerText =
                    allowed
                        ? "✓"
                        : "🔒";
            }
        }
    );
}


/* ============================================================
   REQUIRE PLAN
   ============================================================ */

function requirePlan(
    requiredPlan,
    featureName
) {
    featureName =
        featureName ||
        "Bu özellik";

    requiredPlan =
        normalizePlan(requiredPlan);

    const userLevel =
        getPlanLevel(currentPlan);

    const requiredLevel =
        getPlanLevel(requiredPlan);

    if (userLevel >= requiredLevel) {
        showMessage(
            featureName +
            " aktif.",
            "success"
        );

        return true;
    }

    openPlanModal(
        requiredPlan,
        featureName
    );

    return false;
}


/* ============================================================
   PLAN MODAL
   ============================================================ */

function openPlanModal(
    requiredPlan,
    featureName
) {
    requiredPlan =
        normalizePlan(
            requiredPlan ||
            "PRO"
        );

    featureName =
        featureName ||
        "";

    const modal = $("planModal");

    if (!modal) {
        showMessage(
            requiredPlan +
            " özelliği kilitli.",
            "info"
        );

        return;
    }

    const title =
        $("planModalTitle");

    const description =
        $("planModalDescription");

    const features =
        $("planModalFeatures");

    const upgrade =
        $("planModalUpgrade");

    const icon =
        $("planModalIcon");

    if (icon) {
        icon.innerText =
            requiredPlan ===
            "MAX PRO"
                ? "∞"
                : "✦";
    }

    if (title) {
        title.innerText =
            requiredPlan +
            " ACCESS";
    }

    if (description) {
        description.innerText =
            featureName
                ? featureName +
                  " özelliği " +
                  requiredPlan +
                  " planında kullanılabilir."
                : "Bu özellik " +
                  requiredPlan +
                  " planına dahildir.";
    }

    if (features) {
        if (requiredPlan === "MAX PRO") {
            features.innerHTML =
                "<div class=\"plan-modal-feature\">✓ 300 AI sinyali</div>" +
                "<div class=\"plan-modal-feature\">✓ Tüm sinyaller</div>" +
                "<div class=\"plan-modal-feature\">✓ Gelişmiş AI</div>" +
                "<div class=\"plan-modal-feature\">✓ Backtest</div>" +
                "<div class=\"plan-modal-feature\">✓ Paper Trading</div>" +
                "<div class=\"plan-modal-feature\">✓ Tam terminal erişimi</div>";
        } else {
            features.innerHTML =
                "<div class=\"plan-modal-feature\">✓ 100 AI sinyali</div>" +
                "<div class=\"plan-modal-feature\">✓ 30 tarama hakkı</div>" +
                "<div class=\"plan-modal-feature\">✓ Gelişmiş AI</div>" +
                "<div class=\"plan-modal-feature\">✓ Backtest</div>" +
                "<div class=\"plan-modal-feature\">✓ Paper Trading</div>";
        }
    }

    if (upgrade) {
        upgrade.innerText =
            requiredPlan === "MAX PRO"
                ? "MAX PRO'YA GEÇ"
                : "PRO'YA GEÇ";

        upgrade.dataset.plan =
            requiredPlan;
    }

    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
}

function closePlanModal(event) {
    if (
        event &&
        event.target &&
        event.target.id !== "planModal"
    ) {
        return;
    }

    const modal = $("planModal");

    if (modal) {
        modal.style.display = "none";
    }

    document.body.style.overflow = "";
}

function upgradeFromModal() {
    const button =
        $("planModalUpgrade");

    const target =
        button &&
        button.dataset &&
        button.dataset.plan
            ? button.dataset.plan
            : "PRO";

    closePlanModal();

    selectPlan(target);
}

function selectPlan(plan) {
    plan = normalizePlan(plan);

    const currentLevel =
        getPlanLevel(currentPlan);

    const selectedLevel =
        getPlanLevel(plan);

    if (selectedLevel <= currentLevel) {
        showMessage(
            plan === currentPlan
                ? "Bu plan zaten aktif."
                : "Bu plan mevcut planınızdan düşük.",
            "info"
        );

        return;
    }

    openPlanModal(
        plan,
        plan + " planı"
    );
}


/* ============================================================
   NUMBER FORMAT
   ============================================================ */

function formatNumber(
    value,
    decimals
) {
    decimals =
        decimals === undefined
            ? 2
            : decimals;

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "0";
    }

    return number.toLocaleString(
        "tr-TR",
        {
            minimumFractionDigits:
                decimals,
            maximumFractionDigits:
                decimals
        }
    );
}

function formatInteger(value) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "0";
    }

    return Math.round(number)
        .toLocaleString("tr-TR");
}

function formatChange(value) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "-";
    }

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "-";
    }

    return (
        number >= 0
            ? "+"
            : ""
    ) +
    number.toLocaleString(
        "tr-TR",
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }
    ) +
    "%";
}

function formatPrice(value) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "-";
    }

    const number = Number(value);

    if (
        !Number.isFinite(number) ||
        number <= 0
    ) {
        return "-";
    }

    return number.toLocaleString(
        "tr-TR",
        {
            minimumFractionDigits: 0,
            maximumFractionDigits: 4
        }
    );
}

function formatScore(value) {
    let number = Number(value);

    if (!Number.isFinite(number)) {
        return "0,00%";
    }

    if (Math.abs(number) <= 1) {
        number *= 100;
    }

    return number.toLocaleString(
        "tr-TR",
        {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }
    ) + "%";
}

function getScorePercent(value) {
    let number = Number(value);

    if (!Number.isFinite(number)) {
        return 0;
    }

    if (Math.abs(number) <= 1) {
        number *= 100;
    }

    return number;
}


/* ============================================================
   STATUS
   ============================================================ */

async function loadStatus() {
    try {
        const data =
            await apiFetch(
                "/api/status"
            );

        if (!data || !data.ok) {
            return;
        }

        updateScanData(data);

        const statusElements =
            document.querySelectorAll(
                ".status-value"
            );

        statusElements.forEach(
            function(element) {
                element.innerText =
                    data.status ||
                    "READY";
            }
        );

        setText(
            "buyCount",
            formatInteger(
                data.historical_buy ??
                data.current_buy ??
                0
            )
        );

        setText(
            "sellCount",
            formatInteger(
                data.historical_sell ??
                data.current_sell ??
                0
            )
        );

        setText(
            "holdCount",
            formatInteger(
                data.historical_hold ??
                data.current_hold ??
                0
            )
        );

        setText(
            "topCount",
            formatInteger(
                data.top ?? 0
            )
        );

        setText(
            "totalCount",
            formatInteger(
                data.historical_total ??
                data.current_total ??
                0
            )
        );

        const live =
            document.querySelector(
                ".live-indicator"
            );

        if (live) {
            live.innerText = "● LIVE";
        }

    } catch (error) {
        console.error(
            "STATUS:",
            error
        );
    }
}


/* ============================================================
   SIGNALS
   ============================================================ */

async function loadSignals() {
    try {
        const data =
            await apiFetch(
                "/api/signals"
            );

        if (
            !data ||
            (
                data.ok !== true &&
                data.success !== true
            )
        ) {
            throw new Error(
                data && (
                    data.error ||
                    data.detail
                )
                    ? (
                        data.error ||
                        data.detail
                    )
                    : "Sinyaller alınamadı."
            );
        }

        updateScanData(data);

        allSignals =
            Array.isArray(data.signals)
                ? data.signals
                : [];

        renderSignals(allSignals);

    } catch (error) {
        console.error(
            "SIGNALS:",
            error
        );

        const tbody =
            $("signalsTableBody");

        if (tbody) {
            tbody.innerHTML =
                "<tr>" +
                "<td colspan=\"6\" class=\"empty\">" +
                (
                    getToken()
                        ? "SİNYALLER YÜKLENEMEDİ"
                        : "OTURUM GEREKLİ"
                ) +
                "</td>" +
                "</tr>";
        }
    }
}


/* ============================================================
   RENDER SIGNALS
   ============================================================ */

function renderSignals(signals) {
    signals = signals || allSignals;

    const tbody =
        $("signalsTableBody");

    if (!tbody) {
        return;
    }

    tbody.innerHTML = "";

    if (
        !Array.isArray(signals) ||
        signals.length === 0
    ) {
        tbody.innerHTML =
            "<tr>" +
            "<td colspan=\"6\" class=\"empty\">" +
            "SİNYAL BULUNAMADI" +
            "</td>" +
            "</tr>";

        updateSignalFooter([]);

        return;
    }

    const sortedSignals =
        signals.slice().sort(
            function(a, b) {
                const scoreA =
                    getScorePercent(
                        a &&
                        (
                            a.score ??
                            a.AI_Probability ??
                            a.ai_probability ??
                            0
                        )
                    );

                const scoreB =
                    getScorePercent(
                        b &&
                        (
                            b.score ??
                            b.AI_Probability ??
                            b.ai_probability ??
                            0
                        )
                    );

                return scoreB - scoreA;
            }
        );

    sortedSignals.forEach(
        function(item, index) {

            const symbol =
                String(
                    item &&
                    (
                        item.symbol ??
                        item.ticker ??
                        item.Ticker ??
                        item.Symbol ??
                        "-"
                    )
                ).toUpperCase();

            const signal =
                String(
                    item &&
                    (
                        item.signal ??
                        item.Signal ??
                        "HOLD"
                    )
                ).toUpperCase();

            const scorePercent =
                getScorePercent(
                    item &&
                    (
                        item.score ??
                        item.AI_Probability ??
                        item.ai_probability ??
                        0
                    )
                );

            /*
             * ÖNEMLİ:
             * price = GERÇEK CANLI FİYAT
             * predicted_return burada KULLANILMAZ.
             */

            const priceRaw =
                item &&
                (
                    item.price ??
                    item.Price ??
                    null
                );

            const price =
                priceRaw !== null &&
                priceRaw !== undefined &&
                priceRaw !== ""
                    ? Number(priceRaw)
                    : NaN;

            /*
             * GERÇEK GÜNLÜK DEĞİŞİM
             */

            const changeRaw =
                item &&
                (
                    item.daily_change_percent ??
                    item.change ??
                    item.Daily_Change_Percent ??
                    null
                );

            const change =
                changeRaw !== null &&
                changeRaw !== undefined &&
                changeRaw !== ""
                    ? Number(changeRaw)
                    : NaN;

            let signalClass = "hold";

            if (
                signal === "BUY" ||
                signal === "AL"
            ) {
                signalClass = "buy";
            } else if (
                signal === "SELL" ||
                signal === "SAT"
            ) {
                signalClass = "sell";
            }

            const strongBuy =
                signalClass === "buy" &&
                scorePercent >= 68;

            const mediumBuy =
                signalClass === "buy" &&
                scorePercent >= 66 &&
                scorePercent < 68;

            const weakBuy =
                signalClass === "buy" &&
                scorePercent < 66;

            let scoreClass = "score-weak";

            if (scorePercent >= 68) {
                scoreClass = "score-strong";
            } else if (scorePercent >= 66) {
                scoreClass = "score-medium";
            }

            const changeCls =
                changeClass(change);

            const scoreWidth =
                Math.max(
                    0,
                    Math.min(
                        100,
                        scorePercent
                    )
                );

            const priceText =
                Number.isFinite(price) &&
                price > 0
                    ? formatPrice(price)
                    : "-";

            const row =
                document.createElement("tr");

            row.dataset.symbol = symbol;
            row.dataset.signal = signal;

            if (strongBuy) {
                row.classList.add("strong-buy");
            }

            if (mediumBuy) {
                row.classList.add("medium-buy");
            }

            if (weakBuy) {
                row.classList.add("weak-buy");
            }

            row.innerHTML =
                "<td class=\"signal-rank\">" +
                (index + 1) +
                "</td>" +

                "<td class=\"ticker-cell signal-symbol\">" +
                "<strong>" +
                escapeHtml(symbol) +
                "</strong>" +
                "</td>" +

                "<td class=\"signal-cell\">" +
                "<span class=\"signal-badge " +
                signalClass +
                "\">" +
                escapeHtml(signal) +
                "</span>" +
                "</td>" +

                "<td class=\"score-cell\">" +
                "<div class=\"signal-score " +
                scoreClass +
                "\">" +
                "<span>" +
                formatScore(scorePercent) +
                "</span>" +
                "<div class=\"score-bar\">" +
                "<span class=\"score-bar-fill\" " +
                "style=\"width:" +
                scoreWidth +
                "%\"></span>" +
                "</div>" +
                "</div>" +
                "</td>" +

                "<td class=\"price-cell signal-price\">" +
                priceText +
                "</td>" +

                "<td class=\"" +
                changeCls +
                "\">" +
                formatChange(change) +
                "</td>";

            tbody.appendChild(row);
        }
    );

    updateSignalFooter(sortedSignals);
}


/* ============================================================
   SIGNAL FOOTER
   ============================================================ */

function updateSignalFooter(signals) {
    const footer =
        document.querySelector(
            ".signals-table-footer"
        );

    if (!footer) {
        return;
    }

    let buyCount = 0;
    let sellCount = 0;

    signals.forEach(
        function(item) {
            const signal =
                String(
                    item &&
                    (
                        item.signal ??
                        item.Signal ??
                        ""
                    )
                ).toUpperCase();

            if (
                signal === "BUY" ||
                signal === "AL"
            ) {
                buyCount++;
            }

            if (
                signal === "SELL" ||
                signal === "SAT"
            ) {
                sellCount++;
            }
        }
    );

    footer.innerHTML =
        "<span>" +
        signals.length +
        " SİNYAL</span>" +

        "<span class=\"buy\">" +
        "BUY " +
        buyCount +
        "</span>" +

        "<span class=\"sell\">" +
        "SELL " +
        sellCount +
        "</span>";
}


/* ============================================================
   CHANGE CLASS
   ============================================================ */

function changeClass(value) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "change-neutral";
    }

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "change-neutral";
    }

    if (number > 0) {
        return "change-positive";
    }

    if (number < 0) {
        return "change-negative";
    }

    return "change-neutral";
}


/* ============================================================
   SEARCH
   ============================================================ */

function filterSignals() {
    const input = $("searchInput");

    if (!input) {
        return;
    }

    const query =
        input.value
            .trim()
            .toUpperCase();

    if (!query) {
        renderSignals(allSignals);
        return;
    }

    const filtered =
        allSignals.filter(
            function(item) {
                const symbol =
                    String(
                        item &&
                        (
                            item.symbol ??
                            item.ticker ??
                            item.Ticker ??
                            item.Symbol ??
                            ""
                        )
                    ).toUpperCase();

                const signal =
                    String(
                        item &&
                        (
                            item.signal ??
                            item.Signal ??
                            ""
                        )
                    ).toUpperCase();

                return (
                    symbol.indexOf(query) !== -1 ||
                    signal.indexOf(query) !== -1
                );
            }
        );

    renderSignals(filtered);
}


/* ============================================================
   REFRESH
   ============================================================ */

async function refreshData() {
    if (!getToken()) {
        return;
    }

    try {
        await Promise.allSettled([
            loadPlan(),
            loadStatus(),
            loadSignals()
        ]);

        updatePlanUI(currentPlan);
        updateLockedFeatures();
        updateScanUI();

    } catch (error) {
        console.error(
            "REFRESH:",
            error
        );
    }
}


/* ============================================================
   ESCAPE HTML
   ============================================================ */

function escapeHtml(value) {
    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


/* ============================================================
   ADMIN
   ============================================================ */

function openAdmin() {
    if (
        !currentUser ||
        !currentUser.is_admin
    ) {
        showMessage(
            "Admin yetkiniz yok.",
            "error"
        );

        return;
    }

    showMessage(
        "Admin paneli yakında.",
        "info"
    );
}


/* ============================================================
   KEYBOARD
   ============================================================ */

function setupKeyboard() {
    const loginPassword =
        $("loginPassword");

    const loginEmail =
        $("loginEmail");

    const registerPassword =
        $("registerPassword");

    const registerPassword2 =
        $("registerPassword2");

    if (loginPassword) {
        loginPassword.addEventListener(
            "keydown",
            function(event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    loginUser();
                }
            }
        );
    }

    if (loginEmail) {
        loginEmail.addEventListener(
            "keydown",
            function(event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    loginUser();
                }
            }
        );
    }

    if (registerPassword) {
        registerPassword.addEventListener(
            "keydown",
            function(event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    registerUser();
                }
            }
        );
    }

    if (registerPassword2) {
        registerPassword2.addEventListener(
            "keydown",
            function(event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    registerUser();
                }
            }
        );
    }

    document.addEventListener(
        "keydown",
        function(event) {
            if (event.key === "Escape") {
                closePlanModal();
            }
        }
    );

    document.addEventListener(
        "keydown",
        function(event) {
            if (
                event.key === "/" &&
                document.activeElement &&
                document.activeElement.tagName !== "INPUT" &&
                document.activeElement.tagName !== "TEXTAREA"
            ) {
                event.preventDefault();

                const search =
                    $("searchInput");

                if (search) {
                    search.focus();
                }
            }
        }
    );

    const search =
        $("searchInput");

    if (search) {
        search.addEventListener(
            "input",
            filterSignals
        );
    }

    const scanButtons = [
        $("runScanButton"),
        $("scanButton"),
        $("startScanButton"),
        $("runAnalysisButton")
    ].filter(Boolean);

    scanButtons.forEach(
        function(button) {
            button.addEventListener(
                "click",
                function(event) {
                    event.preventDefault();
                    runAnalysis();
                }
            );
        }
    );
}


/* ============================================================
   GLOBAL FUNCTIONS
   HTML onclick İÇİN ÖNEMLİ
   ============================================================ */

window.loginUser = loginUser;
window.registerUser = registerUser;
window.logoutUser = logoutUser;

window.showLogin = showLogin;
window.showRegister = showRegister;

window.runAnalysis = runAnalysis;
window.openAdmin = openAdmin;

window.openPlanModal = openPlanModal;
window.closePlanModal = closePlanModal;
window.upgradeFromModal = upgradeFromModal;

window.selectPlan = selectPlan;
window.requirePlan = requirePlan;

window.filterSignals = filterSignals;


/* ============================================================
   INIT
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    async function() {

        console.log(
            "LEVEL 1000 AI SCRIPT OK"
        );

        setupKeyboard();
        updateScanUI();

        await checkSession();

        setInterval(
            function() {
                if (!getToken()) {
                    return;
                }

                refreshData();
            },
            30000
        );
    }
);