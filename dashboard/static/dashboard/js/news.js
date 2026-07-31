(() => {
    "use strict";

    const NEWS_API_URL = "/api/news/?limit=80";
    const NEWS_REFRESH_URL = "/api/news/refresh/";
    const TASK_URL_PREFIX = "/api/tasks/";
    const MAX_RENDERED_ITEMS = 40;

    let allNews = [];
    let currentFilter = "ALL";

    const byId = (id) => document.getElementById(id);

    function activateSidebarTab(tabName) {
        const selected = tabName === "calendar" ? "calendar" : "news";
        document.querySelectorAll("[data-sidebar-tab]").forEach((button) => {
            const active = button.dataset.sidebarTab === selected;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
        document.querySelectorAll("[data-sidebar-panel]").forEach((panel) => {
            const active = panel.dataset.sidebarPanel === selected;
            panel.hidden = !active;
            panel.classList.toggle("active", active);
        });

        const refreshButton = byId("newsRefreshButton");
        if (refreshButton) refreshButton.hidden = selected !== "news";

        if (selected === "calendar") {
            const frame = byId("investingCalendarFrame");
            if (frame && !frame.getAttribute("src")) {
                frame.setAttribute("src", frame.dataset.src || "");
            }
        }

        try {
            window.localStorage.setItem("macro-dashboard-sidebar-tab", selected);
        } catch (error) {
            // O armazenamento local pode estar desabilitado; a aba ainda funciona.
        }
    }

    function initializeSidebarTabs() {
        let initialTab = "news";
        try {
            initialTab = window.localStorage.getItem("macro-dashboard-sidebar-tab") || "news";
        } catch (error) {
            initialTab = "news";
        }
        document.querySelectorAll("[data-sidebar-tab]").forEach((button) => {
            button.addEventListener("click", () => activateSidebarTab(button.dataset.sidebarTab));
        });
        activateSidebarTab(initialTab);
    }

    function escapeHtml(value) {
        const node = document.createElement("div");
        node.textContent = value ?? "";
        return node.innerHTML;
    }

    function csrfToken() {
        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));
        return item ? decodeURIComponent(item.split("=").slice(1).join("=")) : "";
    }

    function formatDate(value) {
        if (!value || !Number.isFinite(Date.parse(value))) {
            return "Horário indisponível";
        }
        const date = new Date(value);
        const today = new Date();
        const sameDay = date.toDateString() === today.toDateString();
        return date.toLocaleString("pt-BR", sameDay
            ? {hour: "2-digit", minute: "2-digit"}
            : {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
    }

    function safeUrl(value) {
        try {
            const url = new URL(value, window.location.origin);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
        } catch (error) {
            return "#";
        }
    }

    function relevanceClass(score) {
        if (score >= 70) return "high";
        if (score >= 40) return "medium";
        return "low";
    }

    function matchesFilter(item) {
        if (currentFilter === "ALL") return true;
        return Array.isArray(item.markets) && item.markets.includes(currentFilter);
    }

    function renderNews() {
        const list = byId("newsList");
        if (!list) return;

        const filtered = allNews.filter(matchesFilter).slice(0, MAX_RENDERED_ITEMS);
        if (!filtered.length) {
            list.innerHTML = '<div class="news-empty">Nenhuma notícia relevante neste filtro.</div>';
            return;
        }

        list.innerHTML = filtered.map((item) => {
            const markets = (item.markets || [])
                .filter((market) => ["WIN", "WDO", "MACRO"].includes(market))
                .map((market) => `<span class="news-market news-market-${market.toLowerCase()}">${escapeHtml(market)}</span>`)
                .join("");
            const topics = (item.topics || []).slice(0, 2)
                .map((topic) => `<span class="news-topic">${escapeHtml(topic)}</span>`)
                .join("");
            const score = Number(item.relevance_score) || 0;

            return `
                <article class="news-item">
                    <div class="news-meta-row">
                        <span>${escapeHtml(formatDate(item.published_at))}</span>
                        <span>${escapeHtml(item.category_label || item.category || "Notícia")}</span>
                        <span class="news-relevance ${relevanceClass(score)}">${score}</span>
                    </div>
                    <a class="news-title" href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">
                        ${escapeHtml(item.title)}
                    </a>
                    <div class="news-tags">${markets}${topics}</div>
                </article>
            `;
        }).join("");
    }

    function updateStatus(data) {
        const statusNode = byId("newsStatus");
        if (!statusNode) return;
        const collected = data.last_collected_at && Number.isFinite(Date.parse(data.last_collected_at))
            ? `Atualizado ${formatDate(data.last_collected_at)}`
            : "Sem coleta concluída";
        const collector = data.collector_status?.status;
        const suffix = collector === "partial" ? " · coleta parcial" : collector === "failed" ? " · fontes indisponíveis" : "";
        statusNode.textContent = `${collected} · ${data.count || 0} manchetes${suffix}`;
        statusNode.className = `news-status ${collector === "failed" ? "negative" : collector === "partial" ? "warning-text" : "muted"}`;
    }

    async function loadNews() {
        const list = byId("newsList");
        if (!list) return;
        try {
            const response = await fetch(NEWS_API_URL, {headers: {Accept: "application/json"}, cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            allNews = Array.isArray(data.items) ? data.items : [];
            updateStatus(data);
            renderNews();
        } catch (error) {
            const status = byId("newsStatus");
            if (status) {
                status.textContent = error.message || "Não foi possível carregar as notícias.";
                status.className = "news-status negative";
            }
            if (!allNews.length) {
                list.innerHTML = '<div class="news-empty">Notícias temporariamente indisponíveis.</div>';
            }
        }
    }

    async function waitForTask(taskId) {
        for (let attempt = 0; attempt < 60; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
            const response = await fetch(`${TASK_URL_PREFIX}${encodeURIComponent(taskId)}/`, {cache: "no-store"});
            const data = await response.json();
            if (data.ready) {
                if (data.state === "SUCCESS") return data.result;
                throw new Error(data.error || `Tarefa finalizada em ${data.state}`);
            }
        }
        throw new Error("A coleta de notícias continua em execução.");
    }

    async function refreshNews() {
        const button = byId("newsRefreshButton");
        if (!button) return;
        button.disabled = true;
        button.classList.add("spinning");
        try {
            const response = await fetch(NEWS_REFRESH_URL, {
                method: "POST",
                headers: {"X-CSRFToken": csrfToken(), Accept: "application/json"},
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            if (!data.completed) await waitForTask(data.task_id);
            await loadNews();
        } catch (error) {
            const status = byId("newsStatus");
            if (status) {
                status.textContent = error.message || "Falha ao atualizar notícias.";
                status.className = "news-status negative";
            }
        } finally {
            button.disabled = false;
            button.classList.remove("spinning");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initializeSidebarTabs();
        if (!byId("newsList")) return;
        document.querySelectorAll("[data-news-filter]").forEach((button) => {
            button.addEventListener("click", () => {
                currentFilter = button.dataset.newsFilter || "ALL";
                document.querySelectorAll("[data-news-filter]").forEach((item) => item.classList.toggle("active", item === button));
                renderNews();
            });
        });
        byId("newsRefreshButton")?.addEventListener("click", refreshNews);
        loadNews();
        window.setInterval(loadNews, 60000);
    });
})();
