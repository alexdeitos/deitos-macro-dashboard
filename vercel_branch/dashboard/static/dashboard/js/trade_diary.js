(() => {
    "use strict";

    const app = document.getElementById("tradeDiaryApp");
    if (!app) return;

    const API = {
        accounts: "/api/trade/accounts/",
        setups: "/api/trade/setups/",
        trades: "/api/trade/trades/",
        day: "/api/trade/day/",
        analytics: "/api/trade/analytics/",
        context: "/api/trade/context/",
        capital: "/api/trade/capital/",
    };
    const pointValues = {WIN: 0.2, WDO: 10, IND: 1, DOL: 50, STOCK: 1, OTHER: 1};
    const emotions = ["Confiante", "Calmo", "Focado", "Atento", "Paciente", "Neutro", "Cauteloso", "Ansioso", "Irritado", "Impulsivo", "Vingativo", "Com medo"];
    const state = {
        accounts: [], setups: [], trades: [], accountId: Number(app.dataset.defaultAccount || 0),
        date: localDateString(new Date()), analytics: null, contextTimer: null,
    };

    const $ = (id) => document.getElementById(id);
    const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    function localDateString(value) {
        const date = value instanceof Date ? value : new Date(value);
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    }
    function csrfToken() {
        const match = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith("csrftoken="));
        return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
    }
    async function request(url, options = {}) {
        const headers = {Accept: "application/json", ...(options.headers || {})};
        if (options.method && options.method !== "GET") headers["X-CSRFToken"] = csrfToken();
        const response = await fetch(url, {...options, headers, cache: "no-store"});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || `Erro HTTP ${response.status}`);
        return data;
    }
    function money(value) {
        return new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(Number(value || 0));
    }
    function number(value, digits = 1) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
        return new Intl.NumberFormat("pt-BR", {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(Number(value));
    }
    function escapeHtml(value) {
        const div = document.createElement("div"); div.textContent = value ?? ""; return div.innerHTML;
    }
    function safeUrl(value) {
        try { const url = new URL(value, window.location.origin); return ["http:", "https:"].includes(url.protocol) ? url.href : ""; }
        catch (error) { return ""; }
    }
    function showMessage(message, type = "success") {
        const node = $("diaryMessage"); node.textContent = message; node.className = `diary-message ${type}`; node.hidden = false;
        window.clearTimeout(showMessage.timer); showMessage.timer = window.setTimeout(() => { node.hidden = true; }, 5000);
    }
    function setTone(node, value) {
        if (!node) return;
        node.classList.remove("positive", "negative");
        if (Number(value) > 0) node.classList.add("positive");
        if (Number(value) < 0) node.classList.add("negative");
    }

    async function loadAccounts(selectPreferred = true) {
        const data = await request(API.accounts);
        state.accounts = data.items || [];
        const select = $("accountSelect");
        select.innerHTML = state.accounts.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
        if (!state.accounts.some(item => item.id === state.accountId)) {
            state.accountId = state.accounts.find(item => item.is_default)?.id || state.accounts[0]?.id || 0;
        }
        if (selectPreferred) select.value = String(state.accountId);
    }
    async function loadSetups() {
        const data = await request(API.setups);
        state.setups = data.items || [];
        $("setupSelect").innerHTML = `<option value="">Selecione</option>${state.setups.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("")}`;
    }

    function weekdayLabel(dateString) {
        const date = new Date(`${dateString}T12:00:00`);
        const label = date.toLocaleDateString("pt-BR", {weekday: "long"});
        return label.charAt(0).toUpperCase() + label.slice(1);
    }
    function updateDayNavigation() {
        $("diaryDate").value = state.date;
        $("diaryWeekday").textContent = weekdayLabel(state.date);
        $("todayButton").hidden = state.date === localDateString(new Date());
    }
    async function loadDay() {
        updateDayNavigation();
        const [tradesData, dayData] = await Promise.all([
            request(`${API.trades}?account=${state.accountId}&date=${state.date}`),
            request(`${API.day}?account=${state.accountId}&date=${state.date}`),
        ]);
        state.trades = tradesData.items || [];
        renderDay(dayData.item || {});
    }
    function renderDay(day) {
        $("noTradeCheckbox").checked = Boolean(day.no_trade);
        $("noTradeReason").value = day.no_trade_reason || "";
        $("premarketNotes").value = day.premarket_notes || "";
        $("openingPlan").value = day.opening_plan || "";
        $("dailyReview").value = day.daily_review || "";
        const closed = state.trades.filter(item => item.net_result !== null);
        const net = closed.reduce((sum, item) => sum + Number(item.net_result || 0), 0);
        const points = closed.reduce((sum, item) => sum + Number(item.result_points || 0), 0);
        const wins = closed.filter(item => Number(item.net_result) > 0).length;
        const assessedPlan = closed.filter(item => item.followed_plan !== null);
        const planRate = assessedPlan.length ? assessedPlan.filter(item => item.followed_plan).length / assessedPlan.length * 100 : null;
        $("dayNet").textContent = money(net); setTone($("dayNet"), net);
        $("dayPoints").textContent = number(points); setTone($("dayPoints"), points);
        $("dayTrades").textContent = String(state.trades.length);
        $("dayWinRate").textContent = closed.length ? `${number(wins / closed.length * 100, 0)}%` : "0%";
        $("dayPlanRate").textContent = planRate === null ? "—" : `${number(planRate, 0)}%`;
        $("dayTitle").textContent = `Operações de ${new Date(`${state.date}T12:00:00`).toLocaleDateString("pt-BR")}`;
        renderTrades(day);
    }
    function renderTrades(day) {
        const list = $("tradesList");
        if (!state.trades.length) {
            list.innerHTML = `<div class="empty-day"><div><strong>${day.no_trade ? "Dia marcado sem operações" : "Nenhum trade registrado"}</strong><p>${escapeHtml(day.no_trade_reason || "Registre uma operação para iniciar a análise deste pregão.")}</p><button class="diary-button subtle compact" data-empty-new type="button">＋ Registrar trade</button></div></div>`;
            list.querySelector("[data-empty-new]")?.addEventListener("click", () => openTradeDialog());
            return;
        }
        list.innerHTML = state.trades.map(item => {
            const opening = item.opening_matched === true ? "Abertura bateu" : item.opening_matched === false ? "Abertura falhou" : "Abertura N/A";
            const news = item.had_relevant_news ? `Notícia: ${item.news_impact_label}` : "Sem notícia marcada";
            return `<article class="trade-row ${item.outcome}">
                <div class="trade-row-time">${escapeHtml(item.entry_time || "--:--")}</div>
                <div class="trade-row-main"><strong>${escapeHtml(item.instrument)} · ${escapeHtml(item.direction_label)} · ${escapeHtml(item.setup)}</strong><small>${item.contracts} contrato(s) · ${escapeHtml(item.technical_quality_label)} · ${escapeHtml(news)}</small></div>
                <div class="trade-row-metric"><small>Resultado</small><b class="${Number(item.net_result) >= 0 ? "positive" : "negative"}">${item.net_result === null ? "Aberta" : money(item.net_result)}</b></div>
                <div class="trade-row-metric"><small>Pontos</small><b>${number(item.result_points)}</b></div>
                <div class="trade-row-metric"><small>MFE / MAE</small><b>${number(item.mfe_points)} / ${number(item.mae_points)}</b></div>
                <div class="trade-row-metric"><small>Contexto</small><b>${escapeHtml(opening)}</b></div>
                <div class="trade-row-actions"><button class="icon-button" data-edit-trade="${item.id}" type="button" title="Editar">✎</button><button class="icon-button" data-delete-trade="${item.id}" type="button" title="Excluir">×</button></div>
            </article>`;
        }).join("");
        qsa("[data-edit-trade]", list).forEach(button => button.addEventListener("click", () => openTradeDialog(Number(button.dataset.editTrade))));
        qsa("[data-delete-trade]", list).forEach(button => button.addEventListener("click", () => deleteTrade(Number(button.dataset.deleteTrade))));
    }

    async function saveTradingDay() {
        const body = new URLSearchParams({
            account_id: String(state.accountId), date: state.date,
            no_trade: String($("noTradeCheckbox").checked), no_trade_reason: $("noTradeReason").value,
            premarket_notes: $("premarketNotes").value, opening_plan: $("openingPlan").value, daily_review: $("dailyReview").value,
        });
        await request(API.day, {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body});
        showMessage("Plano e revisão salvos."); await loadDay();
    }
    function moveDate(days) {
        const date = new Date(`${state.date}T12:00:00`); date.setDate(date.getDate() + days); state.date = localDateString(date); loadDay().catch(error => showMessage(error.message, "error"));
    }

    function buildEmotionChips() {
        qsa("[data-emotion-group]").forEach(group => {
            const prefix = group.dataset.emotionGroup;
            group.innerHTML = emotions.map(label => `<label class="emotion-chip"><input type="checkbox" data-emotion="${prefix}" value="${escapeHtml(label)}"><span>${escapeHtml(label)}</span></label>`).join("");
        });
    }
    function addPartialExit(data = {}) {
        const row = document.createElement("div"); row.className = "partial-row";
        row.innerHTML = `<label><span>Hora</span><input data-partial="exit_time" type="time" value="${escapeHtml(data.exit_time || "")}"></label><label><span>Contratos</span><input data-partial="contracts" type="number" min="1" value="${data.contracts || 1}"></label><label><span>Preço</span><input data-partial="price" type="number" min="0" step="0.0001" value="${data.price ?? ""}"></label><label><span>Taxas</span><input data-partial="fees" type="number" min="0" step="0.01" value="${data.fees || 0}"></label><label><span>Nota</span><input data-partial="notes" type="text" value="${escapeHtml(data.notes || "")}"></label><button class="icon-button" data-remove-partial type="button">×</button>`;
        row.querySelector("[data-remove-partial]").addEventListener("click", () => { row.remove(); updateLiveSummary(); });
        qsa("input", row).forEach(input => input.addEventListener("input", updateLiveSummary));
        $("partialExits").appendChild(row); updateLiveSummary();
    }
    function partialExitsData() {
        return qsa(".partial-row", $("partialExits")).map(row => Object.fromEntries(qsa("[data-partial]", row).map(input => [input.dataset.partial, input.value])));
    }
    function formField(name) { return $("tradeForm").elements.namedItem(name); }
    function setFormValue(name, value) {
        const field = formField(name); if (!field) return;
        if (field instanceof RadioNodeList) { qsa(`[name="${name}"]`, $("tradeForm")).forEach(item => { item.checked = item.value === value; }); }
        else field.value = value ?? "";
    }
    function selectedDirection() { return qsa('[name="direction"]', $("tradeForm")).find(item => item.checked)?.value || "BUY"; }
    function updatePointValue(force = false) {
        const instrument = formField("instrument").value;
        if (force || !formField("point_value").value) formField("point_value").value = pointValues[instrument] || 1;
        updateLiveSummary(); scheduleContext();
    }
    function updateLiveSummary() {
        const contracts = Number(formField("contracts").value || 0);
        const entry = Number(formField("entry_price").value || 0);
        const exit = Number(formField("exit_price").value || 0);
        const pointValue = Number(formField("point_value").value || 0);
        const fees = Number(formField("fees").value || 0);
        const stop = Number(formField("planned_stop_points").value || 0);
        const sign = selectedDirection() === "BUY" ? 1 : -1;
        const partials = partialExitsData().filter(item => Number(item.contracts) > 0 && Number(item.price) > 0);
        let totalPointContracts = 0, exited = 0, partialFees = 0;
        if (partials.length) {
            partials.forEach(item => { const qty = Number(item.contracts); totalPointContracts += sign * (Number(item.price) - entry) * qty; exited += qty; partialFees += Number(item.fees || 0); });
            const remaining = Math.max(contracts - exited, 0);
            if (exit > 0 && remaining > 0) { totalPointContracts += sign * (exit - entry) * remaining; exited += remaining; }
        } else if (exit > 0 && contracts > 0) { totalPointContracts = sign * (exit - entry) * contracts; exited = contracts; }
        const points = exited ? totalPointContracts / exited : 0;
        const gross = totalPointContracts * pointValue;
        const manual = formField("financial_result_override").value;
        const net = manual !== "" ? Number(manual) : gross - fees - partialFees;
        const open = Math.max(contracts - exited, 0);
        const risk = stop * pointValue * contracts;
        $("liveFinancialResult").textContent = money(net); setTone($("liveFinancialResult"), net);
        $("livePoints").textContent = number(points); setTone($("livePoints"), points);
        $("liveOpenContracts").textContent = String(open);
        $("liveRisk").textContent = money(risk);
        $("liveRR").textContent = risk > 0 ? number(net / risk, 2) : "—";
    }
    function qualityBadge() {
        const map = {unrated: "NÃO AVALIADA", forced: "FORÇADA", weak: "FRACA", valid: "VÁLIDA", excellent: "EXCELENTE"};
        $("qualityBadgeText").textContent = map[formField("technical_quality").value] || "NÃO AVALIADA";
    }
    function resetTradeForm() {
        $("tradeForm").reset(); $("tradeId").value = ""; $("partialExits").innerHTML = "";
        qsa("[data-emotion]").forEach(input => { input.checked = false; });
        setFormValue("trade_date", state.date); setFormValue("contracts", 1); setFormValue("fees", 0);
        setFormValue("instrument", "WIN"); setFormValue("direction", "BUY"); setFormValue("technical_quality", "unrated");
        setFormValue("discipline_score", 0); $("disciplineOutput").textContent = "0";
        $("linkedEventSelect").innerHTML = '<option value="">Nenhum</option>'; $("linkedEventSelect").dataset.pendingValue = ""; $("contextStatus").textContent = "Preencha data, horário e ativo para recuperar o contexto.";
        $("screenshotPreview").hidden = true; $("screenshotPreview").innerHTML = ""; updatePointValue(true); qualityBadge();
    }
    async function openTradeDialog(tradeId = null) {
        resetTradeForm(); $("tradeDialogTitle").textContent = tradeId ? "EDITAR OPERAÇÃO" : "REGISTRO DE OPERAÇÃO";
        if (tradeId) {
            const data = await request(`${API.trades}${tradeId}/`); populateTradeForm(data.item);
        }
        $("tradeDialog").showModal();
        if (formField("entry_time").value) loadTradeContext();
    }
    function populateTradeForm(item) {
        $("tradeId").value = item.id;
        ["trade_date","entry_time","exit_time","instrument","symbol","setup_id","setup_label","direction","contracts","entry_price","exit_price","point_value","planned_stop_points","mae_points","mfe_points","fees","financial_result_override","screenshot_url","technical_reading","execution_notes","discipline_score","technical_quality","news_impact","news_notes","opening_bias","opening_score","opening_notes"].forEach(name => setFormValue(name, item[name]));
        setFormValue("had_relevant_news", String(Boolean(item.had_relevant_news)));
        setFormValue("followed_plan", item.followed_plan === null ? "" : String(item.followed_plan));
        setFormValue("opening_matched", item.opening_matched === null ? "" : String(item.opening_matched));
        setFormValue("mistakes", (item.mistakes || []).join(", "));
        qsa('[data-emotion="before"]').forEach(input => { input.checked = (item.emotions_before || []).includes(input.value); });
        qsa('[data-emotion="after"]').forEach(input => { input.checked = (item.emotions_after || []).includes(input.value); });
        $("disciplineOutput").textContent = String(item.discipline_score || 0);
        $("linkedEventSelect").dataset.pendingValue = item.linked_event_id || "";
        (item.partial_exits || []).forEach(addPartialExit);
        if (item.screenshot_url) { $("screenshotPreview").innerHTML = `<img src="${escapeHtml(safeUrl(item.screenshot_url))}" alt="Print da operação">`; $("screenshotPreview").hidden = false; }
        qualityBadge(); updateLiveSummary();
    }
    function scheduleContext() {
        window.clearTimeout(state.contextTimer); state.contextTimer = window.setTimeout(loadTradeContext, 450);
    }
    async function loadTradeContext() {
        const date = formField("trade_date").value, time = formField("entry_time").value, instrument = formField("instrument").value;
        if (!date || !time) return;
        try {
            const data = await request(`${API.context}?date=${encodeURIComponent(date)}&time=${encodeURIComponent(time)}&instrument=${encodeURIComponent(instrument)}`);
            $("contextStatus").textContent = `${data.day_events_count} evento(s) no calendário · ${data.market_news_count} notícia(s) coletada(s) · abertura: ${data.opening_source_label}`;
            if (!formField("opening_score").value && data.opening_score !== null) formField("opening_score").value = data.opening_score;
            if (formField("opening_bias").value === "unknown" && data.opening_bias) formField("opening_bias").value = data.opening_bias;
            const current = formField("linked_event_id").value || $("linkedEventSelect").dataset.pendingValue;
            $("linkedEventSelect").innerHTML = '<option value="">Nenhum</option>' + (data.nearby_events || []).map(event => `<option value="${event.id}">${new Date(event.event_at).toLocaleTimeString("pt-BR", {hour:"2-digit",minute:"2-digit"})} · ${escapeHtml(event.country_code)} · ${"★".repeat(event.importance)} ${escapeHtml(event.event)}</option>`).join("");
            if (current) $("linkedEventSelect").value = current;
            $("linkedEventSelect").dataset.pendingValue = "";
        } catch (error) { $("contextStatus").textContent = `Contexto indisponível: ${error.message}`; }
    }
    async function saveTrade(event) {
        event.preventDefault();
        const button = $("saveTradeButton"); button.disabled = true;
        try {
            const formData = new FormData($("tradeForm"));
            formData.set("account_id", String(state.accountId));
            formData.set("partial_exits", JSON.stringify(partialExitsData()));
            formData.set("emotions_before", JSON.stringify(qsa('[data-emotion="before"]:checked').map(input => input.value)));
            formData.set("emotions_after", JSON.stringify(qsa('[data-emotion="after"]:checked').map(input => input.value)));
            const tradeId = $("tradeId").value;
            await request(tradeId ? `${API.trades}${tradeId}/` : API.trades, {method: "POST", body: formData});
            $("tradeDialog").close(); showMessage(tradeId ? "Operação atualizada." : "Operação registrada.");
            await Promise.all([loadDay(), loadAccounts(false)]);
        } catch (error) { showMessage(error.message, "error"); }
        finally { button.disabled = false; }
    }
    async function deleteTrade(id) {
        if (!window.confirm("Excluir esta operação? Essa ação não pode ser desfeita.")) return;
        try { await request(`${API.trades}${id}/`, {method: "DELETE"}); showMessage("Operação excluída."); await loadDay(); }
        catch (error) { showMessage(error.message, "error"); }
    }

    function switchTab(tab) {
        qsa("[data-diary-tab]").forEach(button => button.classList.toggle("active", button.dataset.diaryTab === tab));
        qsa("[data-diary-view]").forEach(view => { const active = view.dataset.diaryView === tab; view.classList.toggle("active", active); view.hidden = !active; });
        if (tab === "analytics") loadAnalytics(); if (tab === "capital") loadCapital();
    }
    async function loadAnalytics() {
        try {
            const params = new URLSearchParams({account: String(state.accountId)});
            if ($("analyticsStart").value) params.set("start", $("analyticsStart").value);
            if ($("analyticsEnd").value) params.set("end", $("analyticsEnd").value);
            state.analytics = await request(`${API.analytics}?${params}`); renderAnalytics(state.analytics);
        } catch (error) { showMessage(error.message, "error"); }
    }
    function renderAnalytics(data) {
        const s = data.summary, c = data.capital;
        const kpis = [
            ["Capital atual", money(c.current), c.current - c.initial], ["Resultado líquido", money(s.net_profit), s.net_profit], ["Retorno", c.return_pct === null ? "—" : `${number(c.return_pct,1)}%`, c.return_pct],
            ["Profit Factor", s.profit_factor ?? "—", (s.profit_factor || 0) - 1], ["Taxa de acerto", `${number(s.win_rate,1)}%`, s.win_rate - 50], ["Payoff", s.payoff ?? "—", (s.payoff || 0) - 1],
            ["Média por trade", money(s.avg_trade), s.avg_trade], ["Máx. drawdown", money(s.max_drawdown), s.max_drawdown], ["Dias positivos", `${s.positive_days}/${s.trading_days}`, s.positive_day_rate - 50],
            ["Maior seq. ganhos", s.max_win_streak, s.max_win_streak], ["Maior seq. perdas", s.max_loss_streak, -s.max_loss_streak], ["Trades fechados", s.trades, 0],
        ];
        $("analyticsKpis").innerHTML = kpis.map(([label,value,tone]) => `<article><span>${label}</span><strong class="${tone > 0 ? "positive" : tone < 0 ? "negative" : ""}">${value}</strong></article>`).join("");
        const h = data.highlights;
        setHighlight("bestTrade", h.best_trade, item => money(item.net_result));
        setHighlight("bestPoints", h.most_points, item => `${number(item.points)} pts`);
        setBreakdownHighlight("bestHour", h.best_hour);
        setBreakdownHighlight("bestSetup", h.best_setup);
        renderSetupTable(data.breakdowns.setups || []);
        renderCharts(data);
    }
    function setHighlight(prefix, item, valueFn) {
        $(`${prefix}Highlight`).textContent = item ? valueFn(item) : "—";
        $(`${prefix}Meta`).textContent = item ? `${new Date(`${item.date}T12:00:00`).toLocaleDateString("pt-BR")} · ${item.time} · ${item.instrument} · ${item.setup}` : "Sem amostra";
    }
    function setBreakdownHighlight(prefix, item) {
        $(`${prefix}Highlight`).textContent = item ? item.label : "—";
        $(`${prefix}Meta`).textContent = item ? `${item.trades} trades · ${money(item.net_profit)} · ${number(item.win_rate,0)}% acerto` : "Sem amostra";
    }
    function renderSetupTable(items) {
        $("setupTableBody").innerHTML = items.length ? items.map(item => `<tr><td>${escapeHtml(item.label)}</td><td>${item.trades}</td><td>${number(item.win_rate,1)}%</td><td class="${Number(item.net_profit)>=0?"positive":"negative"}">${money(item.net_profit)}</td><td>${money(item.avg_trade)}</td><td>${item.profit_factor ?? "—"}</td><td>${number(item.avg_points)}</td></tr>`).join("") : '<tr><td colspan="7">Sem operações no período.</td></tr>';
    }
    function plot(id, traces, layout = {}) {
        const node = $(id); if (!node) return;
        if (!window.Plotly) { node.textContent = "Plotly ainda não foi carregado."; return; }
        window.Plotly.react(node, traces, {paper_bgcolor:"transparent",plot_bgcolor:"transparent",font:{color:"#aeb7ba"},margin:{l:55,r:25,t:20,b:50},xaxis:{gridcolor:"rgba(139,162,179,.1)"},yaxis:{gridcolor:"rgba(139,162,179,.1)"},legend:{orientation:"h"},...layout}, {displayModeBar:false,responsive:true});
    }
    function renderCharts(data) {
        const curve = data.curve || [];
        plot("equityChart", [{x:curve.map(i=>i.date),y:curve.map(i=>i.equity),type:"scatter",mode:"lines+markers",name:"Capital"},{x:curve.map(i=>i.date),y:curve.map(i=>i.drawdown),type:"bar",name:"Drawdown",yaxis:"y2",opacity:.35}], {yaxis2:{overlaying:"y",side:"right",gridcolor:"transparent"}});
        breakdownPlot("setupChart", data.breakdowns.setups || []);
        breakdownPlot("hourChart", data.breakdowns.hours || []);
        breakdownPlot("newsChart", data.breakdowns.news || []);
        breakdownPlot("openingChart", data.breakdowns.opening || []);
    }
    function breakdownPlot(id, items) { plot(id, [{x:items.map(i=>i.label),y:items.map(i=>i.net_profit),type:"bar",name:"Resultado"}], {xaxis:{gridcolor:"transparent",automargin:true},yaxis:{gridcolor:"rgba(139,162,179,.1)"}}); }

    async function loadCapital() {
        try {
            const [analytics, movements] = await Promise.all([request(`${API.analytics}?account=${state.accountId}`), request(`${API.capital}?account=${state.accountId}`)]);
            const c = analytics.capital, s = analytics.summary;
            $("capitalOverview").innerHTML = `<article><span>Capital inicial</span><strong>${money(c.initial)}</strong></article><article><span>Aportes/retiradas</span><strong class="${c.movements>=0?"positive":"negative"}">${money(c.movements)}</strong></article><article><span>Lucro operacional</span><strong class="${s.net_profit>=0?"positive":"negative"}">${money(s.net_profit)}</strong></article><article><span>Capital atual</span><strong class="${c.current>=c.initial?"positive":"negative"}">${money(c.current)}</strong></article>`;
            $("capitalMovementsList").innerHTML = (movements.items || []).length ? movements.items.map(item => `<div class="capital-movement-row"><span>${new Date(`${item.movement_date}T12:00:00`).toLocaleDateString("pt-BR")}</span><b>${escapeHtml(item.kind_label)}</b><span>${escapeHtml(item.description || "—")}</span><strong class="${item.signed_amount>=0?"positive":"negative"}">${money(item.signed_amount)}</strong><button class="icon-button" data-delete-movement="${item.id}" type="button">×</button></div>`).join("") : '<div class="empty-day"><p>Nenhuma movimentação registrada.</p></div>';
            qsa("[data-delete-movement]").forEach(button => button.addEventListener("click", () => deleteMovement(Number(button.dataset.deleteMovement))));
        } catch (error) { showMessage(error.message, "error"); }
    }
    async function saveMovement(event) {
        event.preventDefault(); const form = event.currentTarget; const body = new URLSearchParams(new FormData(form)); body.set("account_id", String(state.accountId));
        try { await request(API.capital, {method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}); form.reset(); form.elements.movement_date.value = state.date; showMessage("Movimentação registrada."); await Promise.all([loadCapital(),loadAccounts(false)]); }
        catch (error) { showMessage(error.message,"error"); }
    }
    async function deleteMovement(id) { if (!window.confirm("Excluir esta movimentação?")) return; try { await request(`${API.capital}${id}/`,{method:"DELETE"}); await loadCapital(); } catch(error){ showMessage(error.message,"error"); } }
    async function saveAccount(event) {
        event.preventDefault(); const form = event.currentTarget; const body = new URLSearchParams(new FormData(form)); body.set("is_default", String(form.elements.is_default.checked));
        try { const data = await request(API.accounts,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body}); state.accountId = data.item.id; $("accountDialog").close(); form.reset(); await loadAccounts(); await loadDay(); showMessage("Conta criada."); }
        catch(error){ showMessage(error.message,"error"); }
    }

    function setupEvents() {
        qsa("[data-diary-tab]").forEach(button => button.addEventListener("click", () => switchTab(button.dataset.diaryTab)));
        $("accountSelect").addEventListener("change", async () => { state.accountId = Number($("accountSelect").value); await loadDay(); const active = qsa("[data-diary-tab].active")[0]?.dataset.diaryTab; if(active==="analytics")loadAnalytics(); if(active==="capital")loadCapital(); });
        $("previousDayButton").addEventListener("click",()=>moveDate(-1)); $("nextDayButton").addEventListener("click",()=>moveDate(1));
        $("todayButton").addEventListener("click",()=>{state.date=localDateString(new Date());loadDay();});
        $("diaryDate").addEventListener("change",()=>{state.date=$("diaryDate").value;loadDay();});
        $("saveDayButton").addEventListener("click",()=>saveTradingDay().catch(error=>showMessage(error.message,"error")));
        [$("newTradeButton"),$("newTradeInlineButton")].forEach(button=>button.addEventListener("click",()=>openTradeDialog().catch(error=>showMessage(error.message,"error"))));
        $("newAccountButton").addEventListener("click",()=>$("accountDialog").showModal());
        qsa("[data-close-dialog]").forEach(button=>button.addEventListener("click",()=>$(button.dataset.closeDialog).close()));
        $("tradeForm").addEventListener("submit",saveTrade); $("accountForm").addEventListener("submit",saveAccount);
        $("capitalMovementForm").addEventListener("submit",saveMovement); $("capitalMovementForm").elements.movement_date.value=state.date;
        $("addPartialExitButton").addEventListener("click",()=>addPartialExit());
        ["contracts","entry_price","exit_price","point_value","planned_stop_points","fees","financial_result_override"].forEach(name=>formField(name).addEventListener("input",updateLiveSummary));
        qsa('[name="direction"]').forEach(input=>input.addEventListener("change",updateLiveSummary));
        formField("instrument").addEventListener("change",()=>updatePointValue(true));
        ["trade_date","entry_time"].forEach(name=>formField(name).addEventListener("change",scheduleContext));
        $("linkedEventSelect").addEventListener("change", () => { if ($("linkedEventSelect").value) formField("had_relevant_news").value = "true"; });
        formField("technical_quality").addEventListener("change",qualityBadge);
        formField("discipline_score").addEventListener("input",()=>{$("disciplineOutput").textContent=formField("discipline_score").value;});
        $("analyticsRefreshButton").addEventListener("click",loadAnalytics);
        $("screenshotInput").addEventListener("change",event=>previewFile(event.target.files[0]));
        document.addEventListener("paste",event=>{if(!$("tradeDialog").open)return; const file=Array.from(event.clipboardData?.files||[]).find(item=>item.type.startsWith("image/")); if(file){const transfer=new DataTransfer();transfer.items.add(file);$("screenshotInput").files=transfer.files;previewFile(file);}});
    }
    function previewFile(file) { if(!file)return; if(file.size>5*1024*1024){showMessage("O print deve ter no máximo 5 MB.","error");return;} const url=URL.createObjectURL(file);$("screenshotPreview").innerHTML=`<img src="${url}" alt="Prévia do print">`;$("screenshotPreview").hidden=false; }

    async function init() {
        buildEmotionChips(); setupEvents(); updateDayNavigation();
        try { await Promise.all([loadAccounts(),loadSetups()]); await loadDay(); }
        catch(error){ showMessage(error.message,"error"); }
    }
    init();
})();
