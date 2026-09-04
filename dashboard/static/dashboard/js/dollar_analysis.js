(() => {
    "use strict";

    const API = "/api/dollar-analysis/";
    const ids = (id) => document.getElementById(id);

    function numeric(value) {
        if (value === null || value === undefined || value === "") return null;
        if (typeof value === "number") return Number.isFinite(value) ? value : null;
        let s = String(value).trim().replace(/\s|%/g, "").replace(/[−–—]/g, "-").replace(/^\+/, "");
        if (!s) return null;
        const comma = s.lastIndexOf(",");
        const dot = s.lastIndexOf(".");
        if (comma !== -1 && dot !== -1) s = comma > dot ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
        else if (comma !== -1) s = s.replace(",", ".");
        const n = Number(s);
        return Number.isFinite(n) ? n : null;
    }

    function fmt(value, decimals = 2) {
        const n = numeric(value);
        return n === null ? "N/D" : n.toLocaleString("pt-BR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }

    function pct(value, decimals = 2) {
        const n = numeric(value);
        return n === null ? "N/D" : `${n > 0 ? "+" : ""}${fmt(n, decimals)}%`;
    }

    function inp(id) { return numeric(ids(id)?.value); }

    function setText(id, text, cls = null) {
        const node = ids(id);
        if (!node) return;
        node.textContent = text;
        if (cls !== null) node.className = cls;
    }

    function setBadge(id, text, tone = "neutral") {
        const node = ids(id);
        if (!node) return;
        node.textContent = text;
        node.className = `dollar-badge ${tone}`;
    }

    function calculateManual() {
        const future = inp("inFuture");
        const spot = inp("inSpot");
        const previous = inp("inPreviousPtax");
        const target = inp("inTargetPtax");
        const selic = inp("inSelic");
        const us1y = inp("inUs1y");
        const days = inp("inDays");
        const overnight = inp("inOvernight");
        const range = Math.max(inp("inRange") ?? 24, 0);
        const frp0 = inp("inFrp0");
        const fixings = [inp("inPtax1"), inp("inPtax2"), inp("inPtax3"), inp("inPtax4")];
        const known = fixings.filter((v) => v !== null);
        const remaining = 4 - known.length;
        const neutral = known.length ? known[known.length - 1] : previous;
        const required = target !== null && remaining > 0 ? (target * 4 - known.reduce((a, b) => a + b, 0)) / remaining : null;
        const average = known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;

        setText("manualProjection", fmt(neutral, 4));
        setText("manualAverage", fmt(average, 4));
        setText("manualRequiredRemaining", fmt(required, 4));
        setText("manualVsPrevious", previous !== null && neutral !== null ? `${fmt((neutral - previous) * 1000, 1)} pts` : "N/D");
        setText("manualFutureVsPtax", future !== null && neutral !== null ? `${fmt(future - neutral * 1000, 1)} pts` : "N/D");
        setText("manualPtaxState", neutral !== null && previous !== null ? (neutral > previous ? "acima" : neutral < previous ? "abaixo" : "estável") : "N/D");
        setBadge("manualPtaxState", neutral !== null && previous !== null ? (neutral > previous ? "PTAX subindo" : neutral < previous ? "PTAX caindo" : "PTAX estável") : "N/D", neutral !== null && previous !== null ? (neutral > previous ? "positive" : neutral < previous ? "negative" : "neutral") : "neutral");

        const forward = future !== null && spot !== null && selic !== null && us1y !== null && days !== null && (1 + selic / 100) > 0 && (1 + us1y / 100) > 0
            ? spot * Math.pow(1 + selic / 100, days / 252) / Math.pow(1 + us1y / 100, days / 252)
            : null;
        const fairBasis = forward !== null && spot !== null ? forward - spot : null;
        const deviation = future !== null && forward !== null ? future - forward : null;
        const deviationPct = future !== null && forward ? deviation / forward * 100 : null;
        const opening = future !== null && overnight !== null ? future * (1 + overnight / 100) : forward;
        const low = opening !== null ? opening - range : null;
        const high = opening !== null ? opening + range : null;

        setText("manualFairForward", fmt(forward, 2));
        setText("manualFairBasis", `Base teórica: ${fmt(fairBasis, 2)} pts`);
        setText("manualOpening", fmt(opening, 2));
        setText("manualLow", fmt(low, 2));
        setText("manualHigh", fmt(high, 2));
        setText("manualDeviation", deviation !== null ? `${deviation >= 0 ? "+" : ""}${fmt(deviation, 2)} pts` : "N/D");
        setText("manualDeviationPct", pct(deviationPct, 4));

        let stretch = "Aguardando entradas.";
        if (deviationPct !== null) stretch = Math.abs(deviationPct) >= 0.35 ? "Prêmio/desconto relevante. Evite perseguir preço; procure confirmação ou retorno à região justa." : Math.abs(deviationPct) >= 0.15 ? "Desvio moderado. Contexto útil, mas ainda exige leitura de fluxo." : "Preço próximo do justo. Dê mais peso à estrutura, VWAP e fluxo.";
        setText("manualFairStretch", stretch);
        setText("manualDeviationInsight", frp0 !== null && spot !== null ? `Paridade + FRP0: ${fmt(spot + frp0, 2)} pts. ${stretch}` : stretch);

        if (opening !== null) {
            const marker = ids("manualRangeMarker");
            if (marker) {
                const position = future !== null && high !== low ? Math.max(0, Math.min(100, ((future - low) / (high - low)) * 100)) : 50;
                marker.style.left = `${position}%`;
            }
        }

        const progress = ids("ptaxProgressBar");
        if (progress) progress.style.width = `${known.length / 4 * 100}%`;
        const table = ids("manualFixingTable");
        if (table) {
            table.innerHTML = fixings.map((value, i) => `<div class="fixing-row"><span>PTAX ${i + 1}<small>${["10h", "11h", "12h", "13h"][i]}</small></span><strong>${fmt(value, 4)}</strong><em>${value !== null && previous !== null ? `${value - previous >= 0 ? "+" : ""}${fmt((value - previous) * 1000, 1)} pts` : "—"}</em></div>`).join("");
        }

        return { future, spot, previous, target, selic, us1y, days, overnight, range, frp0, fixings, neutral, required, forward, deviation, deviationPct, opening, low, high };
    }

    function renderAuto(data) {
        const market = data.market || {};
        const auto = data.automatic || {};
        const f = auto.forward || {};
        const p = auto.ptax || {};
        const dt = auto.daytrade || {};
        setText("autoFuture", fmt(market.future_points, 2));
        setText("autoFutureMeta", `WDO futuro · ${market.collected_at ? new Date(market.collected_at).toLocaleString("pt-BR") : "snapshot"}`);
        setText("autoFair", fmt(f.fair_forward_points, 2));
        setText("autoDeviation", f.future_minus_fair_points == null ? "N/D" : `${f.future_minus_fair_points >= 0 ? "+" : ""}${fmt(f.future_minus_fair_points, 1)} pts`);
        setText("autoPtax", market.ptax_points == null ? "N/D" : fmt(market.ptax_points, 2));
        setBadge("autoStretch", f.fair_stretch || "N/D", f.fair_stretch === "esticado" ? "warning" : f.fair_stretch === "alinhado" ? "positive" : "neutral");
        setBadge("autoPtaxState", dt.ptax_state || "N/D", dt.ptax_state?.includes("acima") ? "warning" : dt.ptax_state?.includes("abaixo") ? "positive" : "neutral");
        setBadge("autoWdoBias", market.wdo_bias || "N/D", market.wdo_bias?.includes("comprador") ? "positive" : market.wdo_bias?.includes("vendedor") ? "negative" : "neutral");
        setText("autoDxy", pct(market.dxy_percent));
        setText("autoVix", pct(market.vix_percent));
        setText("autoEwz", pct(market.ewz_percent));
        setText("autoDow", pct(market.dow_percent));
        setText("autoScore", market.wdo_score == null ? "N/D" : fmt(market.wdo_score, 1));
        setText("autoConfidence", market.wdo_confidence?.label || "N/D");
        setText("autoMacroNote", market.macro_bias ? `${market.macro_bias}${market.macro_score != null ? ` · score ${fmt(market.macro_score, 2)}` : ""}` : "Macro sem score disponível.");

        const levels = ids("autoLevels");
        if (levels) {
            levels.innerHTML = (dt.levels || []).map((item) => {
                const [label, value] = Object.entries(item)[0];
                return `<div class="level-row"><span>${label}</span><strong>${fmt(value, 2)}</strong></div>`;
            }).join("");
        }
        renderList("bullishInsights", data.insights?.bullish || []);
        renderList("bearishInsights", data.insights?.bearish || []);
        renderList("cautionInsights", data.insights?.caution || []);
        const steps = ids("decisionFramework");
        if (steps) steps.innerHTML = (data.decision_framework || []).map((x, i) => `<div class="decision-step"><span>${i + 1}</span><p>${x.replace(/^\d\)\s*/, "")}</p></div>`).join("");
        setBadge("decisionState", market.wdo_bias || "aguardar confirmação", market.wdo_bias?.includes("comprador") ? "positive" : market.wdo_bias?.includes("vendedor") ? "negative" : "neutral");
        setText("dollarDataStatus", "Snapshot carregado", "dollar-status ok");
        window.__autoDollar = data;
    }

    function renderList(id, items) {
        const node = ids(id);
        if (!node) return;
        if (!items.length) { node.innerHTML = "<span class='muted'>Sem leitura disponível.</span>"; return; }
        node.innerHTML = items.map((x) => `<div class="insight-item">${x}</div>`).join("");
    }

    function useAutoValues() {
        const data = window.__autoDollar;
        if (!data) return;
        const m = data.market || {};
        const p = data.automatic?.inputs || {};
        const map = {
            inFuture: m.future_points,
            inSpot: m.spot_points,
            inPreviousPtax: m.ptax_previous,
            inTargetPtax: m.future_points != null ? m.future_points / 1000 : null,
            inSelic: p.selic_percent,
            inUs1y: p.us_1y_percent,
            inDays: p.business_days,
            inOvernight: p.overnight_percent,
            inRange: p.range_points,
        };
        Object.entries(map).forEach(([id, value]) => { if (ids(id) && value != null) ids(id).value = String(value).replace(".", ","); });
        const fixingIds = ["inPtax1", "inPtax2", "inPtax3", "inPtax4"];
        (m.ptax_fixings || []).forEach((value, index) => {
            if (fixingIds[index] && value != null && ids(fixingIds[index])) ids(fixingIds[index]).value = String(value).replace(".", ",");
        });
        calculateManual();
    }

    async function loadAuto() {
        setText("dollarDataStatus", "Carregando...", "dollar-status neutral");
        try {
            const response = await fetch(API, { headers: { Accept: "application/json" }, cache: "no-store" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
            renderAuto(data);
            useAutoValues();
        } catch (error) {
            setText("dollarDataStatus", error.message || "Sem snapshot", "dollar-status error");
        }
    }

    function bind() {
        ["inFuture", "inSpot", "inPreviousPtax", "inTargetPtax", "inSelic", "inUs1y", "inDays", "inOvernight", "inRange", "inFrp0", "inPtax1", "inPtax2", "inPtax3", "inPtax4"].forEach((id) => ids(id)?.addEventListener("input", calculateManual));
        ids("useAutoValues")?.addEventListener("click", useAutoValues);
        ids("dollarRefresh")?.addEventListener("click", loadAuto);
        calculateManual();
        loadAuto();
        window.setInterval(loadAuto, 60000);
    }

    document.addEventListener("DOMContentLoaded", bind);
})();
