(() => {
    "use strict";

    const CALENDAR_API_URL = "/api/calendar/?days=7&importance=1";
    const CALENDAR_REFRESH_URL = "/api/calendar/refresh/";
    const TASK_URL_PREFIX = "/api/tasks/";
    const MAX_RENDERED_ITEMS = 120;

    let allEvents = [];
    let currentCountry = "ALL";
    let currentImportance = 2;

    const byId = (id) => document.getElementById(id);

    function escapeHtml(value) {
        const node = document.createElement("div");
        node.textContent = value ?? "";
        return node.innerHTML;
    }

    function safeUrl(value) {
        try {
            const url = new URL(value, window.location.origin);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
        } catch (error) {
            return "#";
        }
    }

    function csrfToken() {
        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));
        return item ? decodeURIComponent(item.split("=").slice(1).join("=")) : "";
    }

    function validDate(value) {
        return value && Number.isFinite(Date.parse(value));
    }

    function formatTime(value) {
        if (!validDate(value)) return "--:--";
        return new Date(value).toLocaleTimeString("pt-BR", {hour: "2-digit", minute: "2-digit"});
    }

    function dateKey(value) {
        if (!validDate(value)) return "indisponivel";
        const date = new Date(value);
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    }

    function formatDateHeading(value) {
        if (!validDate(value)) return "Data indisponível";
        const date = new Date(value);
        const today = new Date();
        const tomorrow = new Date();
        tomorrow.setDate(today.getDate() + 1);
        if (date.toDateString() === today.toDateString()) return "Hoje";
        if (date.toDateString() === tomorrow.toDateString()) return "Amanhã";
        return date.toLocaleDateString("pt-BR", {weekday: "short", day: "2-digit", month: "2-digit"});
    }

    function valueOrDash(value) {
        const text = String(value ?? "").trim();
        return text || "—";
    }

    function eventMatches(item) {
        const countryMatches = currentCountry === "ALL" || item.country_code === currentCountry;
        const importanceMatches = Number(item.importance || 1) >= currentImportance;
        return countryMatches && importanceMatches;
    }

    function stars(importance) {
        const value = Math.min(Math.max(Number(importance) || 1, 1), 3);
        return `<span class="calendar-stars importance-${value}" title="Impacto ${value} de 3">${"★".repeat(value)}${"☆".repeat(3 - value)}</span>`;
    }

    function renderCalendar() {
        const list = byId("calendarList");
        if (!list) return;
        const filtered = allEvents.filter(eventMatches).slice(0, MAX_RENDERED_ITEMS);
        if (!filtered.length) {
            list.innerHTML = '<div class="calendar-empty">Nenhum evento encontrado neste filtro.</div>';
            return;
        }

        const groups = new Map();
        filtered.forEach((item) => {
            const key = dateKey(item.event_at);
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(item);
        });

        list.innerHTML = Array.from(groups.values()).map((items) => {
            const heading = formatDateHeading(items[0]?.event_at);
            const rows = items.map((item) => {
                const releasedClass = item.released ? "released" : "scheduled";
                const reference = item.reference ? `<span class="calendar-reference">${escapeHtml(item.reference)}</span>` : "";
                return `
                    <article class="calendar-item ${releasedClass}">
                        <div class="calendar-item-head">
                            <span class="calendar-time">${escapeHtml(formatTime(item.event_at))}</span>
                            <span class="calendar-country calendar-country-${escapeHtml((item.country_code || "").toLowerCase())}">${escapeHtml(item.country_code || "--")}</span>
                            ${stars(item.importance)}
                        </div>
                        <a class="calendar-event-title" href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">
                            ${escapeHtml(item.event)} ${reference}
                        </a>
                        <div class="calendar-values">
                            <span><small>Atual</small><strong class="calendar-actual">${escapeHtml(valueOrDash(item.actual))}</strong></span>
                            <span><small>Consenso</small><strong>${escapeHtml(valueOrDash(item.consensus))}</strong></span>
                            <span><small>Anterior</small><strong>${escapeHtml(valueOrDash(item.revised || item.previous))}</strong></span>
                            <span><small>Previsão TE</small><strong>${escapeHtml(valueOrDash(item.forecast))}</strong></span>
                        </div>
                    </article>
                `;
            }).join("");
            return `<section class="calendar-day"><h3>${escapeHtml(heading)}</h3>${rows}</section>`;
        }).join("");
    }

    function updateCalendarStatus(data) {
        const node = byId("calendarStatus");
        if (!node) return;
        const collected = validDate(data.last_collected_at)
            ? `Atualizado ${formatTime(data.last_collected_at)}`
            : "Sem coleta concluída";
        const status = data.collector_status?.status;
        const suffix = status === "failed" ? " · última coleta falhou" : status === "success" ? "" : " · aguardando atualização";
        node.textContent = `${collected} · ${data.count || 0} eventos${suffix}`;
        node.className = `calendar-status ${status === "failed" ? "negative" : "muted"}`;
    }

    async function loadCalendar() {
        const list = byId("calendarList");
        if (!list) return;
        try {
            const response = await fetch(CALENDAR_API_URL, {headers: {Accept: "application/json"}, cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            allEvents = Array.isArray(data.items) ? data.items : [];
            updateCalendarStatus(data);
            renderCalendar();
        } catch (error) {
            const status = byId("calendarStatus");
            if (status) {
                status.textContent = error.message || "Não foi possível carregar o calendário.";
                status.className = "calendar-status negative";
            }
            if (!allEvents.length) {
                list.innerHTML = '<div class="calendar-empty">Calendário temporariamente indisponível.</div>';
            }
        }
    }

    async function waitForTask(taskId) {
        for (let attempt = 0; attempt < 90; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
            const response = await fetch(`${TASK_URL_PREFIX}${encodeURIComponent(taskId)}/`, {cache: "no-store"});
            const data = await response.json();
            if (data.ready) {
                if (data.state === "SUCCESS") return data.result;
                throw new Error(data.error || `Tarefa finalizada em ${data.state}`);
            }
        }
        throw new Error("A coleta do calendário continua em execução.");
    }

    async function refreshCalendar() {
        const button = byId("calendarRefreshButton");
        if (!button) return;
        button.disabled = true;
        button.classList.add("spinning");
        try {
            const response = await fetch(CALENDAR_REFRESH_URL, {
                method: "POST",
                headers: {"X-CSRFToken": csrfToken(), Accept: "application/json"},
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
            const result = data.completed ? data.result : await waitForTask(data.task_id);
            if (result?.status === "failed") throw new Error(result.error || "Falha na coleta da Trading Economics.");
            await loadCalendar();
        } catch (error) {
            const status = byId("calendarStatus");
            if (status) {
                status.textContent = error.message || "Falha ao atualizar o calendário.";
                status.className = "calendar-status negative";
            }
        } finally {
            button.disabled = false;
            button.classList.remove("spinning");
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (!byId("calendarList")) return;
        document.querySelectorAll("[data-calendar-country]").forEach((button) => {
            button.addEventListener("click", () => {
                currentCountry = button.dataset.calendarCountry || "ALL";
                document.querySelectorAll("[data-calendar-country]").forEach((item) => item.classList.toggle("active", item === button));
                renderCalendar();
            });
        });
        document.querySelectorAll("[data-calendar-importance]").forEach((button) => {
            button.addEventListener("click", () => {
                currentImportance = Number(button.dataset.calendarImportance) || 1;
                document.querySelectorAll("[data-calendar-importance]").forEach((item) => item.classList.toggle("active", item === button));
                renderCalendar();
            });
        });
        byId("calendarRefreshButton")?.addEventListener("click", refreshCalendar);
        byId("calendarTabButton")?.addEventListener("click", loadCalendar);
        loadCalendar();
        window.setInterval(loadCalendar, 60000);
    });
})();
