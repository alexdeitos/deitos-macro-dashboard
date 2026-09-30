(() => {
  "use strict";

  let currentFile = null;
  let latestPayload = null;

  const $ = (id) => document.getElementById(id);

  function csrfToken() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function fmt(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }

  function fmtDistance(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} pts`;
  }

  function shortTime(iso) {
    return iso ? String(iso).slice(11, 16) : "—";
  }

  function setMessage(text, type = "warning") {
    const el = $("ictMessage");
    el.textContent = text || "";
    el.className = `message ${type}`;
    el.hidden = !text;
  }

  function setStatus(text, type = "neutral") {
    $("ictStatus").textContent = text;
    $("ictStatus").className = `status ${type}`;
  }

  function renderCards(p) {
    $("ictCurrent").textContent = fmt(p.current);
    $("ictLocation").textContent = `${p.location} · EQ ${fmt(p.equilibrium)}`;
    $("ictFvg").textContent = `${p.stats.fvg_fresh}`;
    $("ictFvgSub").textContent = `${p.stats.fvg_partial} parcial · ${p.stats.fvg_total} úteis`;
    $("ictOb").textContent = `${p.stats.ob_fresh}`;
    $("ictObSub").textContent = `${p.stats.ob_mitigated} mitigado · ${p.stats.ob_total} total`;
    $("ictLiquidity").textContent = p.stats.liquidity_pools;
    $("ictSweeps").textContent = p.stats.sweeps;
    $("ictMss").textContent = `${p.stats.mss} / ${p.stats.bos}`;
    $("ictMssSub").textContent = "MSS / BOS";
    $("ictHigh").textContent = fmt(p.day_high);
    $("ictLow").textContent = fmt(p.day_low);
    $("chartTitle").textContent = `${p.asset} · ${p.date} · ${p.candle_count} candles de 5 minutos${p.source_file ? ` · ${p.source_file}` : ""}`;
    setStatus("Análise concluída", "ok");

    const bias = p.structure_bias || "neutral";
    $("ictStructure").textContent = p.structure_label || bias.toUpperCase();
    $("ictStructure").className = bias === "bullish" ? "positive" : bias === "bearish" ? "negative" : "";
    const le = p.last_structure_event;
    $("ictStructureDetail").textContent = le ? `${le.event} · ${shortTime(le.time)} · ${fmt(le.price)}` : "Sem MSS/BOS confirmado";

    const sw = p.last_sweep;
    $("ictLastSweep").textContent = sw ? `${sw.type === "buy_side_sweep" ? "BSL" : "SSL"} SWEEP` : "—";
    $("ictLastSweepDetail").textContent = sw ? `${shortTime(sw.time)} · ${sw.liquidity_label || "liquidez"} · ${fmt(sw.price)}` : "Sem sweep detectado";

    const mss = p.last_mss;
    $("ictLastMss").textContent = mss ? `MSS ${mss.type === "bullish" ? "↑" : "↓"}` : "—";
    $("ictLastMssDetail").textContent = mss ? `${shortTime(mss.time)} · quebra ${fmt(mss.reference)} · ${fmt(mss.price)}` : "—";

    const disp = p.last_displacement;
    $("ictDelivery").textContent = disp ? `DISPLACEMENT ${disp.direction === "bullish" ? "↑" : "↓"}` : "—";
    $("ictDeliveryDetail").textContent = disp ? `${shortTime(disp.time)} · range ${fmt(disp.range)} · corpo ${fmt(disp.body)}` : "Sem displacement relevante";
  }

  function timeOf(payload, index) {
    const i = Math.max(0, Math.min(payload.candles.length - 1, Number(index) || 0));
    return payload.candles[i].time;
  }

  function futureX(lastIso, minutes = 90) {
    const d = new Date(lastIso);
    d.setMinutes(d.getMinutes() + minutes);
    return d.toISOString();
  }

  function zoneShape(z, payload, historyVisible) {
    if (z.state === "FILLED" || z.state === "INVALIDATED") {
      if (!historyVisible) return null;
    }
    const x0 = timeOf(payload, z.index);
    const x1 = futureX(payload.candles[payload.candles.length - 1].time, z.active ? 100 : 25);
    const isFvg = String(z.id).startsWith("FVG");
    const active = Boolean(z.active);
    let fill = "rgba(96,165,250,.10)";
    let line = "rgba(96,165,250,.55)";
    if (z.type === "bullish" && isFvg) { fill = active ? "rgba(52,211,153,.15)" : "rgba(52,211,153,.035)"; line = "rgba(52,211,153,.85)"; }
    if (z.type === "bearish" && isFvg) { fill = active ? "rgba(251,113,133,.15)" : "rgba(251,113,133,.035)"; line = "rgba(251,113,133,.85)"; }
    if (z.type === "bullish" && !isFvg) { fill = active ? "rgba(96,165,250,.14)" : "rgba(96,165,250,.035)"; line = "rgba(96,165,250,.85)"; }
    if (z.type === "bearish" && !isFvg) { fill = active ? "rgba(245,158,11,.14)" : "rgba(245,158,11,.035)"; line = "rgba(245,158,11,.85)"; }
    return {
      type: "rect", xref: "x", yref: "y", x0, x1, y0: z.bottom, y1: z.top,
      fillcolor: fill,
      line: { color: line, width: active ? 1.4 : 1, dash: active ? "solid" : "dot" },
      layer: active ? "below" : "below",
    };
  }

  function renderChart(p) {
    if (!window.Plotly) return;
    const x = p.candles.map(c => c.time);
    const o = p.candles.map(c => c.open);
    const h = p.candles.map(c => c.high);
    const l = p.candles.map(c => c.low);
    const c = p.candles.map(c => c.close);
    const historyVisible = $("showHistory").checked;
    const showSwings = $("showSwings").checked;
    const showLiquidity = $("showLiquidity").checked;
    const shapes = [];
    const annotations = [];
    const traces = [];

    // Premium / discount of the selected session.
    shapes.push({ type: "rect", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.day_low, y1: p.equilibrium,
      fillcolor: "rgba(45,212,191,.035)", line: { width: 0 }, layer: "below" });
    shapes.push({ type: "rect", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.equilibrium, y1: p.day_high,
      fillcolor: "rgba(251,113,133,.028)", line: { width: 0 }, layer: "below" });

    const allZones = [...(p.fvg || []), ...(p.order_blocks || [])];
    const zonesToDraw = allZones.filter(z => (z.active ? z.plot !== false : historyVisible));
    zonesToDraw.forEach(z => {
      const shape = zoneShape(z, p, historyVisible);
      if (shape) shapes.push(shape);
      if (z.active && (z.plot !== false || z.priority >= 4)) {
        annotations.push({
          x: timeOf(p, z.index), y: z.top,
          text: `${String(z.id).startsWith("FVG") ? "FVG" : "OB"} ${z.type === "bullish" ? "↑" : "↓"}`,
          showarrow: false, xanchor: "left", yanchor: "bottom", yshift: 1,
          font: { size: 9, color: "#dbe6f7" },
          bgcolor: "rgba(8,17,31,.72)", bordercolor: "rgba(35,54,82,.75)", borderwidth: 1,
        });
      }
    });

    if (showLiquidity) {
      (p.liquidity || []).filter(q => q.plot !== false).forEach(q => {
        const isBsl = q.type === "BSL";
        const color = isBsl ? "rgba(192,132,252,.82)" : "rgba(45,212,191,.82)";
        const width = Number(q.strength) >= 5 ? 2 : 1;
        shapes.push({ type: "line", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: q.price, y1: q.price,
          line: { color, width, dash: "dash" }, layer: "below" });
        annotations.push({
          x: x[x.length - 1], y: q.price, text: `${q.label}`, showarrow: false, xanchor: "right",
          font: { size: 8, color }, bgcolor: "rgba(8,17,31,.40)", borderwidth: 0,
        });
      });
    }

    shapes.push({ type: "line", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.day_high, y1: p.day_high,
      line: { color: "rgba(96,165,250,.75)", width: 1.6, dash: "dot" }, layer: "above" });
    shapes.push({ type: "line", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.day_low, y1: p.day_low,
      line: { color: "rgba(96,165,250,.75)", width: 1.6, dash: "dot" }, layer: "above" });
    shapes.push({ type: "line", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.equilibrium, y1: p.equilibrium,
      line: { color: "rgba(148,163,184,.65)", width: 1, dash: "dashdot" }, layer: "above" });
    shapes.push({ type: "line", xref: "x", yref: "y", x0: x[0], x1: futureX(x[x.length - 1], 100), y0: p.current, y1: p.current,
      line: { color: "rgba(232,238,248,.42)", width: 1, dash: "dot" }, layer: "above" });
    annotations.push({ x: x[x.length - 1], y: p.current, text: `PRICE ${fmt(p.current)}`, showarrow: false, xanchor: "right", yshift: 0,
      font: { size: 9, color: "#e8eef8" }, bgcolor: "rgba(8,17,31,.72)" });
    annotations.push({ x: x[x.length - 1], y: p.day_high, text: "DAY HIGH / BSL", showarrow: false, xanchor: "right", yshift: 10, font: { size: 9, color: "#60a5fa" } });
    annotations.push({ x: x[x.length - 1], y: p.day_low, text: "DAY LOW / SSL", showarrow: false, xanchor: "right", yshift: -10, font: { size: 9, color: "#60a5fa" } });
    annotations.push({ x: x[x.length - 1], y: p.equilibrium, text: "EQ 50%", showarrow: false, xanchor: "right", font: { size: 9, color: "#94a3b8" } });

    (p.sweeps || []).forEach(s => {
      const y = s.type === "buy_side_sweep" ? s.price : s.price;
      annotations.push({
        x: timeOf(p, s.index), y,
        text: s.type === "buy_side_sweep" ? "BSL SWEEP" : "SSL SWEEP",
        showarrow: true, arrowhead: 2, arrowsize: .7, arrowwidth: 1.3,
        arrowcolor: "#fbbf24", ax: 0, ay: s.type === "buy_side_sweep" ? -34 : 34,
        font: { size: 8, color: "#fbbf24" }, bgcolor: "rgba(8,17,31,.80)"
      });
    });

    (p.mss || []).forEach(m => {
      annotations.push({
        x: timeOf(p, m.index), y: m.price,
        text: `MSS ${m.type === "bullish" ? "↑" : "↓"}`,
        showarrow: true, arrowhead: 2, arrowsize: .7, arrowwidth: 1.2,
        arrowcolor: "#60a5fa", ax: 0, ay: m.type === "bullish" ? 36 : -36,
        font: { size: 9, color: "#60a5fa" }, bgcolor: "rgba(8,17,31,.82)"
      });
    });
    (p.bos || []).forEach(b => {
      annotations.push({
        x: timeOf(p, b.index), y: b.price,
        text: `BOS ${b.type === "bullish" ? "↑" : "↓"}`,
        showarrow: false, yshift: b.type === "bullish" ? 16 : -16,
        font: { size: 8, color: "#94a3b8" }, bgcolor: "rgba(8,17,31,.65)"
      });
    });

    if (showSwings) {
      traces.push({
        type: "scatter", mode: "markers", x: (p.swings?.highs || []).map(s => timeOf(p, s.index)), y: (p.swings?.highs || []).map(s => s.price),
        marker: { size: 5, symbol: "triangle-down", color: "rgba(192,132,252,.82)" },
        name: "Swing High", hovertemplate: "Swing High<br>%{y:,.0f}<extra></extra>",
      });
      traces.push({
        type: "scatter", mode: "markers", x: (p.swings?.lows || []).map(s => timeOf(p, s.index)), y: (p.swings?.lows || []).map(s => s.price),
        marker: { size: 5, symbol: "triangle-up", color: "rgba(45,212,191,.82)" },
        name: "Swing Low", hovertemplate: "Swing Low<br>%{y:,.0f}<extra></extra>",
      });
    }

    traces.unshift({
      type: "candlestick", x, open: o, high: h, low: l, close: c,
      increasing: { line: { color: "#34d399", width: 1 }, fillcolor: "#34d399" },
      decreasing: { line: { color: "#fb7185", width: 1 }, fillcolor: "#fb7185" },
      whiskerwidth: .5, name: p.asset,
      hovertemplate: "<b>%{x|%H:%M}</b><br>O %{open:,.0f}<br>H %{high:,.0f}<br>L %{low:,.0f}<br>C %{close:,.0f}<extra></extra>",
    });

    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(8,17,31,.55)",
      margin: { l: 62, r: 55, t: 10, b: 45 }, dragmode: "pan",
      xaxis: { type: "date", gridcolor: "rgba(35,54,82,.45)", rangeslider: { visible: false }, showspikes: true, spikemode: "across", spikethickness: 1, color: "#91a2ba" },
      yaxis: { gridcolor: "rgba(35,54,82,.45)", color: "#91a2ba", fixedrange: false, tickformat: ",.0f", side: "right" },
      hovermode: "x unified", shapes, annotations, showlegend: false,
      font: { family: "Inter, system-ui, sans-serif", color: "#e8eef8" },
    };
    Plotly.react("ictChart", traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] });
  }

  function renderPois(p) {
    const list = $("ictPois");
    const pois = (p.pois || []).slice(0, 12);
    if (!pois.length) {
      list.innerHTML = '<div class="empty-state">Nenhum POI prioritário identificado.</div>';
      return;
    }
    list.innerHTML = pois.map(z => {
      const kind = String(z.id).startsWith("FVG") ? "FVG" : "OB";
      const activeClass = z.active ? "poi-active" : "poi-muted";
      const state = z.state === "OPEN" ? "FRESH" : z.state === "PARTIAL" ? "PARCIAL" : z.state;
      const conf = (z.confluences || []).join(" · ") || "estrutura isolada";
      return `
        <div class="poi-row ${activeClass}">
          <div class="poi-main">
            <span class="poi-badge ${z.type}">${kind} ${z.type === "bullish" ? "↑" : "↓"}</span>
            <div>
              <div class="poi-title">${fmt(z.bottom)} — ${fmt(z.top)}</div>
              <div class="poi-sub">${state} · ${shortTime(z.time)} · ${z.age} candles de idade</div>
              <div class="poi-conf">${conf}</div>
            </div>
          </div>
          <div class="poi-right">
            <strong>${z.in_zone ? "ATIVO" : fmtDistance(z.distance)}</strong>
            <small>${z.pd_aligned ? "P/D alinhado" : "P/D neutro"}</small>
          </div>
        </div>`;
    }).join("");
  }

  function renderCandidates(p) {
    const list = $("ictCandidates");
    if (!(p.candidates || []).length) {
      list.innerHTML = '<div class="empty-state">Nenhum cenário condicionado. O motor exige contexto estrutural e não transforma POI isolado em entrada.</div>';
      return;
    }
    list.innerHTML = p.candidates.map(c => `
      <div class="candidate ${c.type}">
        <div class="candidate-top"><strong>${c.direction}</strong><span>${c.status}</span></div>
        <div class="candidate-zone">${fmt(c.zone_bottom)} — ${fmt(c.zone_top)} <small>${String(c.zone_id)}</small></div>
        <div class="candidate-grid">
          <div><span>Conf.</span><strong>${c.confluence_count}/5</strong></div>
          <div><span>Invalidação</span><strong>${fmt(c.invalidation)}</strong></div>
          <div><span>Alvo liquidez</span><strong>${c.target ? fmt(c.target) : "—"}</strong></div>
        </div>
        <small class="candidate-reason">${c.reason}</small>
        <div class="candidate-trigger">${c.trigger}</div>
        ${c.target_label ? `<div class="candidate-target">Target: ${c.target_label}</div>` : ""}
      </div>`).join("");
  }

  function renderLiquidity(p) {
    const list = $("ictLiquidityList");
    const rows = (p.liquidity || []).slice().sort((a, b) => Number(b.strength) - Number(a.strength) || Number(a.distance || 0) - Number(b.distance || 0)).slice(0, 18);
    if (!rows.length) { list.innerHTML = '<div class="empty-state">Nenhum nível de liquidez identificado.</div>'; return; }
    list.innerHTML = `<table class="ict-table"><thead><tr><th>Tipo</th><th>Pool</th><th>Preço</th><th>Dist.</th><th>Estado</th></tr></thead><tbody>
      ${rows.map(q => `<tr><td><span class="liquidity-type ${q.type}">${q.type}</span></td><td>${q.label}</td><td class="num">${fmt(q.price)}</td><td class="num">${fmtDistance(q.distance)}</td><td>${q.status || q.relative || "—"}</td></tr>`).join("")}
    </tbody></table>`;
  }

  function renderEvents(p) {
    const list = $("ictEvents");
    const ev = (p.events || []).slice().reverse().slice(0, 35);
    if (!ev.length) { list.innerHTML = '<div class="empty-state">Nenhum sweep/MSS/BOS identificado pelas regras atuais.</div>'; return; }
    list.innerHTML = ev.map(e => `
      <div class="event ${e.event === "MSS" ? "event-mss" : e.event === "BOS" ? "event-bos" : "event-sweep"}">
        <span><strong class="event-name">${e.event}</strong><small>${e.direction || ""}</small></span>
        <span class="event-time">${shortTime(e.time)} · ${fmt(e.price)}${e.reference ? ` · ref ${fmt(e.reference)}` : ""}</span>
      </div>`).join("");
  }

  function renderContext(p) {
    const prior = p.prior_day;
    const nearestAbove = (p.liquidity || []).filter(x => x.price > p.current).sort((a, b) => a.price - b.price)[0];
    const nearestBelow = (p.liquidity || []).filter(x => x.price < p.current).sort((a, b) => b.price - a.price)[0];
    $("ictContextTable").innerHTML = `
      <div class="context-row"><span>Localização</span><strong>${p.location}</strong><small>EQ 50% = ${fmt(p.equilibrium)}</small></div>
      <div class="context-row"><span>PDH / PDL</span><strong>${prior ? `${fmt(prior.high)} / ${fmt(prior.low)}` : "não disponíveis"}</strong><small>${prior ? prior.date : "o CSV precisa conter o pregão anterior"}</small></div>
      <div class="context-row"><span>BSL mais próxima</span><strong>${nearestAbove ? fmt(nearestAbove.price) : "—"}</strong><small>${nearestAbove ? nearestAbove.label : "nenhuma acima"}</small></div>
      <div class="context-row"><span>SSL mais próxima</span><strong>${nearestBelow ? fmt(nearestBelow.price) : "—"}</strong><small>${nearestBelow ? nearestBelow.label : "nenhuma abaixo"}</small></div>
      <div class="context-row"><span>POI prioritário</span><strong>${p.pois?.[0] ? `${fmt(p.pois[0].bottom)}–${fmt(p.pois[0].top)}` : "—"}</strong><small>${p.pois?.[0]?.id || "—"}</small></div>`;
  }

  function renderMethodology(p) {
    $("ictMethodology").innerHTML = Object.entries(p.methodology || {}).map(([k, v]) => `
      <div class="method-item"><span>${k.replaceAll("_", " ")}</span><strong>${v}</strong></div>`).join("");
  }

  function populateDates(dates, selected) {
    const sel = $("ictDate");
    sel.innerHTML = "";
    dates.forEach(d => {
      const o = document.createElement("option");
      o.value = d; o.textContent = d.split("-").reverse().join("/");
      if (d === selected) o.selected = true;
      sel.appendChild(o);
    });
    sel.disabled = false;
  }

  function render(p) {
    latestPayload = p;
    renderCards(p);
    populateDates(p.available_dates || [p.date], p.date);
    renderChart(p);
    renderPois(p);
    renderCandidates(p);
    renderLiquidity(p);
    renderEvents(p);
    renderContext(p);
    renderMethodology(p);
    setMessage("", "warning");
  }

  async function analyzeFile() {
    if (!currentFile) {
      setMessage("Selecione o CSV exportado do Profit primeiro.", "warning");
      return;
    }
    const button = $("ictAnalyze");
    button.disabled = true;
    setStatus("Processando…", "neutral");
    const form = new FormData();
    form.append("file", currentFile);
    const date = $("ictDate").value;
    if (date) form.append("date", date);
    try {
      const response = await fetch("/api/ict-analysis/", {
        method: "POST", body: form,
        headers: { "X-CSRFToken": csrfToken() }, credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || "Falha na análise.");
      render(data);
    } catch (err) {
      setStatus("Erro", "error");
      setMessage(err.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function autoLoad(date = "") {
    const button = $("ictAutoLoad");
    button.disabled = true;
    setStatus("Lendo data/…", "neutral");
    try {
      const url = date ? `/api/ict-analysis/auto/?date=${encodeURIComponent(date)}` : "/api/ict-analysis/auto/";
      const response = await fetch(url, { credentials: "same-origin" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || "Não foi possível carregar o CSV de data/.");
      currentFile = null;
      $("ictFile").value = "";
      render(data);
      setMessage(`Fonte automática: ${data.source_file} em data/.`, "success");
    } catch (err) {
      setStatus("Aguardando arquivo", "neutral");
      setMessage(err.message, "warning");
    } finally {
      button.disabled = false;
    }
  }

  $("ictFile").addEventListener("change", (e) => {
    currentFile = e.target.files[0] || null;
    $("ictDate").disabled = true;
    if (currentFile) {
      setStatus("Arquivo selecionado", "neutral");
      setMessage(`Arquivo pronto: ${currentFile.name}. Clique em “Analisar ICT”.`, "warning");
    }
  });

  $("ictAnalyze").addEventListener("click", analyzeFile);
  $("ictAutoLoad").addEventListener("click", () => autoLoad($("ictDate").value));
  $("ictDate").addEventListener("change", () => {
    if (currentFile) analyzeFile();
    else autoLoad($("ictDate").value);
  });
  ["showHistory", "showSwings", "showLiquidity"].forEach(id => $(id).addEventListener("change", () => latestPayload && renderChart(latestPayload)));

  document.addEventListener("DOMContentLoaded", () => {
    autoLoad();
  });
})();
