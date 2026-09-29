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
    if (v === null || v === undefined) return "—";
    return `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} pts`;
  }

  function timeOf(payload, index) {
    return payload.candles[Math.max(0, Math.min(payload.candles.length - 1, Number(index) || 0))].time;
  }

  function setMessage(text, type="warning") {
    const el = $("ictMessage");
    el.textContent = text || "";
    el.className = `message ${type}`;
    el.hidden = !text;
  }

  function renderCards(p) {
    $("ictCurrent").textContent = fmt(p.current);
    $("ictLocation").textContent = p.location;
    $("ictFvg").textContent = `${p.stats.fvg_open} / ${p.stats.fvg_total}`;
    $("ictOb").textContent = `${p.stats.ob_open} / ${p.stats.ob_total}`;
    $("ictLiquidity").textContent = p.stats.liquidity_pools;
    $("ictSweeps").textContent = p.stats.sweeps;
    $("ictMss").textContent = p.stats.mss;
    $("ictHigh").textContent = fmt(p.day_high);
    $("ictLow").textContent = fmt(p.day_low);
    $("chartTitle").textContent = `${p.asset} · ${p.date} · ${p.candle_count} candles de 5 minutos`;
    $("ictStatus").textContent = "Análise concluída";
    $("ictStatus").className = "status ok";
  }

  function zoneShape(z, payload) {
    const x0 = timeOf(payload, z.index);
    const x1 = payload.candles[payload.candles.length - 1].time;
    let fill = "rgba(96,165,250,.10)";
    let line = "rgba(96,165,250,.70)";
    if (z.type === "bullish" && String(z.id).startsWith("FVG")) { fill="rgba(52,211,153,.12)"; line="rgba(52,211,153,.75)"; }
    if (z.type === "bearish" && String(z.id).startsWith("FVG")) { fill="rgba(251,113,133,.12)"; line="rgba(251,113,133,.75)"; }
    if (z.type === "bullish" && String(z.id).startsWith("OB")) { fill="rgba(96,165,250,.13)"; line="rgba(96,165,250,.85)"; }
    if (z.type === "bearish" && String(z.id).startsWith("OB")) { fill="rgba(245,158,11,.13)"; line="rgba(245,158,11,.85)"; }
    if (z.mitigated) { fill="rgba(145,162,186,.035)"; line="rgba(145,162,186,.28)"; }
    return {
      type:"rect", xref:"x", yref:"y", x0, x1, y0:z.bottom, y1:z.top,
      fillcolor:fill, line:{color:line, width:1, dash:z.mitigated ? "dot" : "solid"},
      layer:"below"
    };
  }

  function renderChart(p) {
    const x = p.candles.map(c => c.time);
    const scale = Number(p.display_scale || 1);
    const o = p.candles.map(c => c.open * scale);
    const h = p.candles.map(c => c.high * scale);
    const l = p.candles.map(c => c.low * scale);
    const c = p.candles.map(c => c.close * scale);

    const shapes = [];
    const annotations = [];

    [...(p.fvg || []), ...(p.order_blocks || [])].forEach(z => {
      shapes.push(zoneShape(z, p));
      if (z.active || !z.mitigated) {
        annotations.push({
          x: timeOf(p, z.index), y: z.top,
          text: String(z.id).startsWith("FVG") ? `FVG ${z.type === "bullish" ? "↑" : "↓"}` : `OB ${z.type === "bullish" ? "↑" : "↓"}`,
          showarrow:false, xanchor:"left", yanchor:"bottom",
          font:{size:9,color:"#cbd5e1"}, bgcolor:"rgba(8,17,31,.72)", bordercolor:"rgba(35,54,82,.7)", borderwidth:1
        });
      }
    });

    (p.liquidity || []).forEach(q => {
      const color = q.type === "BSL" ? "rgba(192,132,252,.75)" : "rgba(45,212,191,.75)";
      shapes.push({
        type:"line", xref:"x", yref:"y", x0:x[0], x1:x[x.length-1],
        y0:q.price, y1:q.price, line:{color, width:q.strength >= 5 ? 2 : 1, dash:"dash"},
        layer:"below"
      });
    });

    (p.sweeps || []).forEach(s => {
      shapes.push({
        type:"line", xref:"x", yref:"y", x0:timeOf(p,s.index), x1:timeOf(p,s.index),
        y0:s.type==="buy_side_sweep" ? s.level : s.price,
        y1:s.type==="buy_side_sweep" ? s.price : s.level,
        line:{color:"#fbbf24",width:2,dash:"dot"}, layer:"above"
      });
    });

    const eq = p.equilibrium;
    shapes.push({
      type:"line", xref:"x", yref:"y", x0:x[0], x1:x[x.length-1],
      y0:eq, y1:eq, line:{color:"rgba(148,163,184,.55)",width:1,dash:"dot"}
    });
    annotations.push({x:x[x.length-1],y:eq,text:"EQ 50%",showarrow:false,xanchor:"right",font:{size:9,color:"#94a3b8"}});

    (p.mss || []).forEach(m => {
      annotations.push({
        x:timeOf(p,m.index), y:m.price,
        text:`MSS ${m.type==="bullish"?"↑":"↓"}`,
        showarrow:true, arrowhead:2, arrowsize:.7, arrowwidth:1,
        arrowcolor:"#60a5fa", ax:0, ay:m.type==="bullish"?35:-35,
        font:{size:9,color:"#60a5fa"}, bgcolor:"rgba(8,17,31,.8)"
      });
    });

    const trace = {
      type:"candlestick", x, open:o, high:h, low:l, close:c,
      increasing:{line:{color:"#34d399",width:1},fillcolor:"#34d399"},
      decreasing:{line:{color:"#fb7185",width:1},fillcolor:"#fb7185"},
      whiskerwidth:.5, name:p.asset, hovertemplate:
        "<b>%{x|%H:%M}</b><br>O %{open:,.0f}<br>H %{high:,.0f}<br>L %{low:,.0f}<br>C %{close:,.0f}<extra></extra>"
    };

    const layout = {
      paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(8,17,31,.55)",
      margin:{l:62,r:35,t:10,b:45}, dragmode:"pan",
      xaxis:{type:"date",gridcolor:"rgba(35,54,82,.45)",rangeslider:{visible:false},showspikes:true,spikemode:"across",spikethickness:1,color:"#91a2ba"},
      yaxis:{gridcolor:"rgba(35,54,82,.45)",color:"#91a2ba",fixedrange:false,tickformat:",.0f",side:"right"},
      hovermode:"x unified", shapes, annotations, showlegend:false,
      font:{family:"Inter, system-ui, sans-serif",color:"#e8eef8"}
    };
    Plotly.newPlot("ictChart",[trace],layout,{responsive:true,displaylogo:false,modeBarButtonsToRemove:["lasso2d","select2d","autoScale2d"]});
  }

  function renderPois(p) {
    const list = $("ictPois");
    const pois = (p.pois || []).filter(z => z.active).slice(0, 15);
    if (!pois.length) { list.innerHTML = '<div class="empty-state">Não há POI ativo identificado no dia.</div>'; return; }
    list.innerHTML = pois.map(z => `
      <div class="poi-row">
        <span class="poi-badge ${z.type}">${String(z.id).startsWith("FVG") ? "FVG" : "OB"} ${z.type === "bullish" ? "↑" : "↓"}</span>
        <div><div class="poi-price">${fmt(z.bottom)} — ${fmt(z.top)}</div><div class="poi-distance">${z.mitigated ? "Mitigado" : "Não mitigado"} · ${z.time.slice(11,16)}</div></div>
        <span class="poi-distance">${z.distance === 0 ? "ATIVO" : fmtDistance(z.distance)}</span>
      </div>`).join("");
  }

  function renderCandidates(p) {
    const list = $("ictCandidates");
    if (!(p.candidates || []).length) {
      list.innerHTML = '<div class="empty-state">Nenhum setup condicional ativo agora. O motor não transforma POI isolado em entrada.</div>';
      return;
    }
    list.innerHTML = p.candidates.map(c => `
      <div class="candidate">
        <strong>${c.direction} · ${c.status}</strong>
        <div>${fmt(c.zone_bottom)} — ${fmt(c.zone_top)}</div>
        <small>${c.reason} · distância ${fmtDistance(c.distance)}</small>
      </div>`).join("");
  }

  function renderLiquidity(p) {
    const list = $("ictLiquidityList");
    const rows = (p.liquidity || []).sort((a,b)=>Number(b.strength)-Number(a.strength));
    if (!rows.length) { list.innerHTML = '<div class="empty-state">Nenhuma piscina de liquidez identificada.</div>'; return; }
    list.innerHTML = `<table class="ict-table"><thead><tr><th>Tipo</th><th>Região</th><th>Preço</th><th>Força</th></tr></thead><tbody>
      ${rows.map(q => `<tr><td>${q.type}</td><td>${q.label}</td><td class="num">${fmt(q.price)}</td><td>${"●".repeat(Math.min(5, q.strength))}</td></tr>`).join("")}
    </tbody></table>`;
  }

  function renderEvents(p) {
    const list = $("ictEvents");
    const ev = (p.events || []).slice().reverse().slice(0, 30);
    if (!ev.length) { list.innerHTML = '<div class="empty-state">Nenhum sweep/MSS identificado pelas regras atuais.</div>'; return; }
    list.innerHTML = ev.map(e => `
      <div class="event"><span class="event-name">${e.event}</span><span class="event-time">${e.time.slice(11,16)} · ${fmt(e.price)}</span></div>
    `).join("");
  }

  function renderMethodology(p) {
    $("ictMethodology").innerHTML = Object.entries(p.methodology || {}).map(([k,v]) => `
      <div class="method-item"><span>${k.replaceAll("_"," ")}</span><strong>${v}</strong></div>`).join("");
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
    renderMethodology(p);
    setMessage("", "warning");
  }

  async function analyze() {
    if (!currentFile) {
      setMessage("Selecione o CSV exportado do Profit primeiro.", "warning");
      return;
    }
    const button = $("ictAnalyze");
    button.disabled = true;
    $("ictStatus").textContent = "Processando...";
    $("ictStatus").className = "status neutral";
    const form = new FormData();
    form.append("file", currentFile);
    const date = $("ictDate").value;
    if (date) form.append("date", date);

    try {
      const response = await fetch("/api/ict-analysis/", {
        method:"POST",
        body:form,
        headers:{"X-CSRFToken":csrfToken()},
        credentials:"same-origin"
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.message || "Falha na análise.");
      render(data);
    } catch (err) {
      $("ictStatus").textContent = "Erro";
      $("ictStatus").className = "status error";
      setMessage(err.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  $("ictFile").addEventListener("change", (e) => {
    currentFile = e.target.files[0] || null;
    $("ictDate").disabled = true;
    if (currentFile) {
      $("ictStatus").textContent = "Arquivo selecionado";
      $("ictStatus").className = "status neutral";
      setMessage(`Arquivo pronto: ${currentFile.name}. Clique em "Analisar ICT".`, "warning");
    }
  });

  $("ictAnalyze").addEventListener("click", analyze);
  $("ictDate").addEventListener("change", analyze);
})();
