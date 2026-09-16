(() => {
  const $ = id => document.getElementById(id);
  const num = (v,d=2) => v==null || !Number.isFinite(Number(v)) ? 'N/D' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pct = (v,d=2) => v==null || !Number.isFinite(Number(v)) ? 'N/D' : `${Number(v)>0?'+':''}${num(v,d)}%`;
  const tone = v => Number(v)>0?'positive':Number(v)<0?'negative':'neutral';
  const csrf = () => document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';
  const esc = s => String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\'':'&#39;','"':'&quot;'}[c]));

  function setValue(id, value, digits=2){ $(id).textContent = value==null ? 'N/D' : num(value,digits); }
  function setSigned(id, value, digits=2, suffix=''){ const el=$(id); if(value==null || !Number.isFinite(Number(value))){ el.textContent='N/D'; el.className=''; return; } const n=Number(value); el.textContent=`${n>0?'+':''}${num(n,digits)}${suffix}`; el.className=tone(n); }
  function buildIndexFallback(quotes){
    const ib = quotes?.IBOV || {};
    const base = Number.isFinite(Number(ib.previous_close)) && Number(ib.previous_close) !== 0
      ? Number(ib.previous_close)
      : (Number.isFinite(Number(ib.value)) ? Number(ib.value) : null);
    const observed = Number.isFinite(Number(ib.value)) ? Number(ib.value) : null;
    const us = [
      {value: quotes?.DJI?.change_percent, weight: 0.70},
      {value: quotes?.SP500?.change_percent, weight: 0.20},
      {value: quotes?.NASDAQ?.change_percent, weight: 0.10}
    ].filter(x => Number.isFinite(Number(x.value)));
    const totalW = us.reduce((a,x)=>a+x.weight,0);
    const weighted = totalW ? us.reduce((a,x)=>a+Number(x.value)*x.weight,0)/totalW : null;
    const opening = base!=null && weighted!=null ? base*(1+weighted/100) : null;
    return {
      observed_points: observed,
      base_points: base,
      fair_value_points: base,
      opening_estimate_points: opening,
      deviation_points: observed!=null && base!=null ? observed-base : null,
      expected_change_percent: weighted,
      confidence: {coverage_percent: totalW*100},
      bias: weighted==null ? 'dados insuficientes' : weighted>0.15 ? 'abertura potencialmente positiva' : weighted<-0.15 ? 'abertura potencialmente negativa' : 'abertura neutra/lateral'
    };
  }

  function renderPriceModels(dollar, index, quotes, radar, collectedAt){
    const d=dollar?.automatic?.forward||{}, dm=dollar?.market||{};
    const captured = radar?.captured_instruments || {};
    const wdo = captured.WDOFUT || {};
    const win = captured.WINFUT || {};
    const ifnc = captured.IFNC || {};

    // Contract prices/VAR/volume are authoritative from CONFIG_CAPTURA.
    const wdoCurrent = wdo.value ?? dm.future_points ?? quotes?.WDOFUT?.value ?? quotes?.DOL_FUT?.value;
    const winCurrent = win.value ?? quotes?.WINFUT?.value ?? quotes?.WIN?.value ?? index?.observed_points ?? index?.base_points;
    const ibovCurrent = quotes?.IBOV?.value;

    setValue('cpDollarCurrent', wdoCurrent, 3);
    setValue('cpDollarFair', d.fair_forward_points, 3);
    setValue('cpDollarOpen', d.opening_proxy_points ?? d.fair_forward_points, 3);
    const wdoDeviation = d.future_minus_fair_points != null && wdoCurrent != null
      ? Number(d.future_minus_fair_points) : null;
    setSigned('cpDollarDeviation', wdoDeviation, 3, ' pts');

    setValue('cpIndexCurrent', winCurrent, 3);
    setValue('cpIndexFair', index?.fair_value_points ?? null, 3);
    setValue('cpIndexOpen', index?.opening_estimate_points ?? null, 3);
    setSigned('cpIndexDeviation', index?.deviation_points, 3, ' pts');

    $('cpDollarDirection').textContent = wdo.change_percent==null ? 'N/D' : (Number(wdo.change_percent)>0?'WDO ↑':'WDO ↓');
    $('cpDollarDirection').className = `pill ${tone(wdo.change_percent)}`;
    $('cpIndexDirection').textContent = i?.bias ? String(i.bias).toUpperCase() : 'N/D';
    $('cpIndexDirection').className = `pill ${tone(i?.expected_change_percent)}`;

    $('cpDollarRead').textContent = d.fair_forward_points==null
      ? 'Preço justo indisponível: faltam dados de spot/taxas.'
      : (wdo.change_percent!=null ? `WDOFUT ${pct(wdo.change_percent,3)} · volume ${num(wdo.volume,0)} · ${Number(d.future_minus_fair_points||0)>0?'acima':'abaixo'} do justo.` : 'Modelo disponível; VAR do Profit não capturada.');

    $('cpIndexRead').textContent = i?.fair_value_points==null
      ? 'Modelo do índice indisponível: faltam fatores externos/IBOV para o cálculo.'
      : `WINFUT ${pct(win.change_percent,3)} · volume ${num(win.volume,0)} · IFNC ${pct(ifnc.change_percent,3)} · abertura ${i.opening_estimate_points==null?'N/D':num(i.opening_estimate_points,3)} · cobertura ${i.confidence?.coverage_percent==null?'N/D':num(i.confidence.coverage_percent,1)}%.`;

    $('cpDollarSnapshot').textContent = validTimestamp(wdo.observed_at || collectedAt) ? `Snapshot ${new Date(wdo.observed_at || collectedAt).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}` : 'N/D';
    $('cpIndexSnapshot').textContent = validTimestamp(win.observed_at || collectedAt) ? `Snapshot ${new Date(win.observed_at || collectedAt).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}` : 'N/D';
  }
  function renderStocks(s){
    $('cpWeighted').textContent=s.weighted_change_percent==null?'N/D':pct(s.weighted_change_percent,3);
    $('cpContribution').textContent=s.index_contribution_percent==null?'N/D':`${pct(s.index_contribution_percent,3)} p.p.`;
    $('cpPositive').textContent=s.positive_weight_percent==null?'N/D':`${num(s.positive_weight_percent,1)}%`;
    $('cpNegative').textContent=s.negative_weight_percent==null?'N/D':`${num(s.negative_weight_percent,1)}%`;
    const rows=(s.all||[]).slice().sort((a,b)=>Math.abs(Number(b.contribution_percent||0))-Math.abs(Number(a.contribution_percent||0))).slice(0,8);
    $('cpStocks').innerHTML=rows.map(x=>{const v=Number(x.contribution_percent||0), c=tone(v), w=Math.min(100,Math.abs(v)*260);return `<div class="cp-row ${c}"><span class="name">${esc(x.symbol)}</span><div class="bar"><i style="width:${w}%"></i></div><span class="value">Var ${pct(x.change_percent,2)} · ${pct(x.contribution_percent,3)} p.p.</span></div>`}).join('')||'<div class="muted">Sem ações capturadas.</div>';
    $('cpCoverage').textContent=`Cobertura ${num(s.coverage_percent,1)}%`;
  }
  function renderDrivers(items,id){
    $(id).innerHTML=(items||[]).map(x=>{const v=Number(x.adjusted_change_percent ?? x.change_percent);const c=tone(v);const w=Math.min(100,Math.abs(v)*7);return `<div class="cp-row ${c}"><span class="name">${esc(x.symbol)}</span><div class="bar"><i style="width:${w}%"></i></div><span class="value">${pct(v,2)}</span></div>`}).join('')||'<div class="muted">Sem dados.</div>';
  }
  function renderRates(items){
    const rates=(items||[]).filter(x=>/^(DI1|DAP|PRE|DIF)/i.test(String(x.symbol||''))).slice(0,6);
    $('cpRates').innerHTML=rates.map(x=>`<div class="cp-row ${tone(x.change_percent)}"><span class="name">${esc(x.symbol)}</span><div class="bar"><i style="width:${Math.min(100,Math.abs(Number(x.change_percent||0))*15)}%"></i></div><span class="value">${pct(x.change_percent,3)}</span></div>`).join('')||'<div class="muted">Sem contratos de juros capturados.</div>';
  }
  function renderEvents(events){
    $('cpEvents').innerHTML=(events||[]).slice(0,5).map(e=>{const a=e.analysis||{};const bias=String(a.market_bias||'NEUTRO').toLowerCase();return `<div class="cp-event"><span class="cp-event-time">${new Date(e.event_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}</span><span class="cp-event-country">${esc(e.country_code)}</span><div class="cp-event-main"><strong>${esc(e.event)}</strong><div class="cp-event-values">Anterior ${esc(e.previous||'—')} · Consenso ${esc(e.forecast||e.consensus||'—')} · Atual ${esc(e.actual||'—')}</div></div><span class="cp-event-bias ${bias}">${esc(a.market_bias||'NEUTRO')}</span></div>`}).join('')||'<div class="muted">Nenhum evento 3★ disponível.</div>';
  }
  async function fetchJson(url,opts){const r=await fetch(url,opts);const d=await r.json();if(!r.ok)throw new Error(d.message||`HTTP ${r.status}`);return d;}
  async function load(force=false){
    try{
      const [radar,dash,dt,dollar] = await Promise.allSettled([
        fetchJson(force?'/api/radar-indice/refresh/':'/api/radar-indice/', force?{method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'}}:{headers:{Accept:'application/json'}}),
        fetchJson('/api/dashboard/',{headers:{Accept:'application/json'}}),
        fetchJson('/api/daytrade/',{headers:{Accept:'application/json'}}),
        fetchJson('/api/dollar-analysis/',{headers:{Accept:'application/json'}})
      ]);
      const r = radar.status==='fulfilled'?radar.value:null;
      const q = dash.status==='fulfilled'?(dash.value.quotes||{}):{};
      const d = dt.status==='fulfilled'?dt.value:{};
      const da = dollar.status==='fulfilled'?dollar.value:{};
      const dashboardIndex = dash.status==='fulfilled' ? (dash.value.index_opening || {}) : {};
      const daytradeIndex = d.index_opening || {};
      const hasIndexValues = m => ['observed_points','fair_value_points','opening_estimate_points'].some(k => m && m[k] != null && Number.isFinite(Number(m[k])));
      const indexModel = hasIndexValues(dashboardIndex) ? dashboardIndex : daytradeIndex;
      // Usa o mesmo index_opening do Dashboard original; nao cria uma segunda fonte de dados para o WIN.

      if(!r) throw new Error(radar.reason?.message||'Radar do índice indisponível.');
      $('cpUpdated').textContent=`Atualizado ${new Date().toLocaleTimeString('pt-BR')}`;
      $('cpDirection').textContent=r.direction||'AGUARDAR'; $('cpDirection').className=`cp-direction ${r.tone||'neutral'}`;
      $('cpAction').textContent=d.action||r.context?.[0]||'Leitura contextual disponível no Radar.';
      $('cpScore').textContent=r.score==null?'N/D':(Number(r.score)>0?'+':'')+num(r.score,1);
      $('cpConfidence').textContent=r.confidence||'N/D'; $('cpState').textContent=d.state||'N/D';
      const captured = r.captured_instruments || {}; const win=captured.WINFUT||{}; const wdo=captured.WDOFUT||{}; const ib=q.IBOV||{}; const ifnc=captured.IFNC||{};
      $('cpWin').textContent=win.value!=null?num(win.value,3):(indexModel.observed_points!=null?num(indexModel.observed_points,3):'N/D');
      $('cpWdo').textContent=wdo.value!=null?num(wdo.value,3):'N/D';
      $('cpIbov').textContent=ib.value!=null?num(ib.value,3):'N/D';
      $('cpWinMeta').textContent = `${pct(win.change_percent,3)} · ${num(win.volume,0)}`;
      $('cpWdoMeta').textContent = `${pct(wdo.change_percent,3)} · ${num(wdo.volume,0)}`;
      $('cpIfncMeta').textContent = pct(ifnc.change_percent,3);
      $('cpCapture').textContent=r.excel_capture?.observed_at ? `${r.excel_capture.status_label} · ${new Date(r.excel_capture.observed_at).toLocaleTimeString('pt-BR')}` : 'N/D';
      renderStocks(r.stock_pressure||{}); renderPriceModels(da, indexModel, q, r, r.collected_at || (dash.status==='fulfilled'?dash.value.collected_at:null)); renderDrivers(r.external_factors||[],'cpExternal');
      const ext=r.external_factors||[];
      renderDrivers(ext.filter(x=>['VIX','DXY'].includes(x.symbol)),'cpRisk');
      renderDrivers(ext.filter(x=>['BRENT','WTI','IRON_ORE'].includes(x.symbol)),'cpCommodities');
      renderRates(ext);
      renderEvents(d.calendar?.events||[]);
      $('cpMessage').hidden=true;
    }catch(e){$('cpMessage').hidden=false;$('cpMessage').textContent=e.message||'Falha ao carregar o painel.';}
  }
  document.addEventListener('DOMContentLoaded',()=>{$('cpRefresh')?.addEventListener('click',()=>load(true));load(false);setInterval(()=>load(false),60000);});
})();
