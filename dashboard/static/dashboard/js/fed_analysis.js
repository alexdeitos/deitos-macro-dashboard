(() => {
    "use strict";
    const API = "/api/fed-analysis/";
    const REFRESH = "/api/fed-analysis/refresh/";
    const $ = (id) => document.getElementById(id);
    const n = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
    const fmt = (v, d=2) => n(v) === null || !Number.isFinite(n(v)) ? "N/D" : n(v).toLocaleString("pt-BR", {minimumFractionDigits:d, maximumFractionDigits:d});
    const pct = (v) => n(v) === null ? "N/D" : `${fmt(v,2)}%`;

    function csrfToken() {
        const item = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith("csrftoken="));
        return item ? decodeURIComponent(item.split("=").slice(1).join("=")) : "";
    }

    function set(id, value) { if ($(id)) $(id).textContent = value; }
    function tone(el, tone) { if (!el) return; el.className = `fed-badge ${tone}`; }

    function series(data, id, label) {
        const rows = data.series?.[id] || [];
        if (!rows.length) return {x: [], y: [], name: label};
        return {x: rows.map(r => r.date), y: rows.map(r => r.value), name: label, mode:"lines", type:"scatter", line:{width:2}};
    }

    function derivedSeries(data, id, label) {
        const rows = data.derived?.[id] || [];
        if (Array.isArray(rows)) return {x: rows.map(r => r.date), y: rows.map(r => r.value), name: label, mode:"lines", type:"scatter", line:{width:2}};
        return {x: rows.dates || [], y: rows.values || [], name: label, mode:"lines", type:"scatter", line:{width:2}};
    }

    const layout = (title, yTitle) => ({title:{text:title, font:{size:12}}, paper_bgcolor:"transparent", plot_bgcolor:"transparent", font:{color:"#d8e2ef", size:10}, margin:{l:46,r:12,t:34,b:38}, hovermode:"x unified", xaxis:{gridcolor:"rgba(145,162,186,.10)", rangeslider:{visible:false}}, yaxis:{title:yTitle || "", gridcolor:"rgba(145,162,186,.10)"}, legend:{orientation:"h", y:1.12}, showlegend:true});
    const config = {responsive:true, displaylogo:false, modeBarButtonsToRemove:["lasso2d","select2d"]};

    function render(data) {
        if (!data.available) {
            set("fedStatus", data.message || "FRED indisponível");
            $("fedStatus")?.classList.add("bad");
            return;
        }
        const L = data.latest || {};
        const insight = data.insights || {};
        set("kpiDff", pct(L.DFF?.value)); set("kpiDffMeta", L.DFF?.date || "-");
        set("kpiDgs10", pct(L.DGS10?.value)); set("kpiDgs10Meta", L.DGS10?.date || "-");
        set("kpiSpread", insight.spread_10_2 == null ? "N/D" : `${fmt(insight.spread_10_2,2)} pp`); set("kpiSpreadMeta", "10Y − 2Y");
        set("kpiCpi", pct(insight.cpi_yoy)); set("kpiCpiMeta", "CPI YoY");

        set("fedScore", insight.score == null ? "N/D" : (insight.score > 0 ? "+" : "") + fmt(insight.score,0));
        set("fedBias", insight.bias || "N/D");
        tone($("fedBias"), insight.tone || "neutral");
        set("fedBiasText", insight.score >= 3 ? "Contexto de juros/inflacao tende a apoiar USD, mas entrada no WDO exige confirmação de preço e fluxo." : insight.score <= -2 ? "Contexto macro favorece um USD menos pressionado por juros; atenção ao risco de queda do dólar." : "Sinais macro mistos. Priorize estrutura intraday, VWAP e fluxo antes de escolher direção.");
        $("fedDrivers").innerHTML = (insight.drivers || []).slice(0,5).map(x => `<div class="insight-line">${x}</div>`).join("") || "<span class='muted'>Sem drivers suficientes.</span>";

        const gap = insight.policy_gap_2y_fedfunds;
        set("policyGap", gap == null ? "N/D" : `${gap >= 0 ? "+" : ""}${fmt(gap,2)} pp`);
        set("policyGapText", gap == null ? "Sem dados." : gap > 0.25 ? "Curva de 2Y acima do Fed Funds: mercado ainda carrega prêmio de juros." : gap < -0.25 ? "2Y abaixo do Fed Funds: mercado precifica cortes/flexibilização à frente." : "2Y próximo do Fed Funds: sinal neutro.");
        if ($("policyNeedle")) $("policyNeedle").style.setProperty("--dummy", "1");
        set("inflCpi", pct(insight.cpi_yoy)); set("inflPce", pct(insight.pce_yoy)); set("inflBreakeven", pct(L.T10YIE?.value));
        set("inflationText", insight.cpi_yoy > 3 || insight.pce_yoy > 2.5 ? "Inflação ainda relevante: qualquer surpresa hawkish tende a mexer com yields e, por transmissão, com o dólar." : "Inflação mais comportada: o mercado tende a deslocar o foco para emprego e trajetória de cortes.");

        Plotly.react("ratesChart", [series(data,"DGS10","10Y"),series(data,"DGS2","2Y"),series(data,"DFF","Fed Funds")], layout("Taxas de juros","%"), config);
        Plotly.react("spreadChart", [derivedSeries(data,"spread_10_2","10Y − 2Y")], layout("Spread da curva","pp"), config);
        Plotly.react("inflationChart", [derivedSeries(data,"cpi_yoy","CPI YoY"),derivedSeries(data,"pce_yoy","PCE YoY"),series(data,"T10YIE","Breakeven")], layout("Inflação e expectativas","%"), config);
        Plotly.react("laborChart", [series(data,"UNRATE","Desemprego"),series(data,"PAYEMS","Payrolls (milhões)")], layout("Mercado de trabalho",""), config);
        Plotly.react("balanceChart", [series(data,"WALCL","Ativos do Fed")], layout("Ativos totais","US$ tri"), config);
        Plotly.react("rrpChart", [series(data,"RRPONTSYD","ON RRP")], layout("ON RRP","US$ tri"), config);

        const playbook = [
            "1) Antes da abertura: observe direção dos yields 2Y/10Y e compare com DXY/WDO do seu Dashboard.",
            `2) Surpresa hawkish: yields subindo + DXY firme + WDO acima do justo aumenta a qualidade de continuidade; evite perseguir esticado.`,
            `3) Surpresa dovish: yields caindo + DXY cedendo + WDO perdendo suporte favorece venda apenas com confirmação de preço/fluxo.`,
            "4) Dados macro são contexto, não gatilho: confirme VWAP, máximas/mínimas, fluxo e reação do preço nos minutos seguintes.",
            "5) Se sinais do Fed e do mercado estiverem divergentes, reduza confiança e espere estrutura mais limpa."
        ];
        $("tradePlaybook").innerHTML = playbook.map((x,i)=>`<div class="playbook-step"><b>${i+1}</b><p>${x.replace(/^\d\)\s*/,'')}</p></div>`).join("");

        const errors = Object.entries(data.errors || {});
        $("fedErrors").innerHTML = errors.length ? errors.map(([id,msg])=>`<div class="status-row"><strong>${id}</strong><span>${String(msg).slice(0,110)}</span></div>`).join("") : `<div class="status-row"><strong>FRED</strong><span>Todas as séries carregadas.</span></div>`;
        set("fedStatus", `Atualizado · ${data.to}`); $("fedStatus")?.classList.add("ok");
        window.__fedData = data;
    }

    async function load(url=API, options={}) {
        try {
            const response = await fetch(url, {headers:{"Accept":"application/json"}, ...options});
            const payload = await response.json();
            render(payload);
        } catch (error) {
            set("fedStatus", `Erro: ${error.message}`); $("fedStatus")?.classList.add("bad");
        }
    }

    $("fedRefresh")?.addEventListener("click", async () => {
        const btn = $("fedRefresh"); btn.disabled=true; set("fedStatus","Atualizando FRED…");
        await load(REFRESH, {method:"POST", headers:{"X-CSRFToken": csrfToken()}});
        btn.disabled=false;
    });

    document.addEventListener("DOMContentLoaded", () => load());
})();
