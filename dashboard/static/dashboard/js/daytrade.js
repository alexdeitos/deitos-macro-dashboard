(() => {
  const $ = id => document.getElementById(id);
  const num = (v, d=2) => v == null || !Number.isFinite(Number(v)) ? 'N/D' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pct = (v, d=2) => v == null || !Number.isFinite(Number(v)) ? 'N/D' : `${Number(v)>0?'+':''}${num(v,d)}%`;
  const tone = v => Number(v)>0 ? 'positive' : Number(v)<0 ? 'negative' : 'neutral';
  const csrf = () => document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';
  const esc = s => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\'':'&#39;','"':'&quot;'}[c]));

  function renderComponents(data) {
    const target = $('componentGrid');
    target.innerHTML = (data.components || []).map(c => {
      const score = Number(c.score || 0), cls = tone(score), width = Math.min(100, Math.abs(score));
      return `<article class="dt-component panel ${cls}"><span class="label">${esc(c.label)}</span><strong>${score > 0 ? '+' : ''}${num(score,1)}</strong><div class="weight">Peso ${num(c.weight_percent,0)}%</div><div class="dt-track"><div class="dt-track-fill ${cls}" style="width:${width}%"></div></div><div class="muted" style="margin-top:8px;font-size:10px;line-height:1.35">${esc(c.note)}</div></article>`;
    }).join('');
  }

  function renderDrivers(data) {
    const items = data.global_components || [];
    $('globalDrivers').innerHTML = items.length ? items.slice(0,8).map(x => {
      const raw = Number(x.weighted || 0) * 100;
      const c = tone(raw), width = Math.min(100, Math.abs(raw) * 8);
      return `<div class="dt-driver ${c}"><span class="sym">${esc(x.symbol)}</span><div class="dt-bar"><i style="width:${width}%"></i></div><span class="val">${pct(raw,2)} · ${num(x.weight_percent,1)}%</span></div>`;
    }).join('') : '<div class="muted">Sem drivers externos suficientes.</div>';
  }

  function renderStocks(data) {
    const s = data.radar?.stock_pressure || {};
    $('dtWeighted').textContent = s.weighted_change_percent == null ? 'N/D' : `${pct(s.weighted_change_percent,3)} média coberta`;
    $('dtPositive').textContent = s.positive_weight_percent == null ? 'N/D' : `${num(s.positive_weight_percent,1)}%`;
    $('dtNegative').textContent = s.negative_weight_percent == null ? 'N/D' : `${num(s.negative_weight_percent,1)}%`;
    $('dtCoverage').textContent = `Cobertura ${num(data.radar?.coverage?.ibov_weight_percent,1)}%`;
    const rows = (s.top_positive || []).slice(0,5).concat((s.top_negative || []).slice(0,5));
    $('stockLeaders').innerHTML = rows.map(x => {
      const contribution = Number(x.contribution_percent || 0); const c = tone(contribution); const width = Math.min(100, Math.abs(contribution)*40);
      const raw = Number.isFinite(Number(x.change_percent)) ? Number(x.change_percent) : null;
      const details = raw == null ? '' : ` · Var ${pct(raw,2)} · Peso ${num(x.weight_percent,2)}%`;
      return `<div class="dt-driver ${c}"><span class="sym">${esc(x.symbol)}</span><div class="dt-bar"><i style="width:${width}%"></i></div><span class="val">Contrib ${pct(contribution,3)}${details}</span></div>`;
    }).join('') || '<div class="muted">Sem ações ponderadas capturadas.</div>';
  }

  function renderEvents(data) {
    const cal = data.calendar || {}; const events = cal.events || [];
    const gate = $('dtEventGate');
    gate.textContent = cal.gate || '—';
    gate.className = `event-gate ${cal.active_risk ? 'warning' : cal.warning_risk ? 'warning' : events.some(e => e.analysis?.market_bias === 'NEGATIVO') ? 'negative' : 'neutral'}`;
    $('dtEvents').innerHTML = events.length ? events.map(e => {
      const a=e.analysis||{}; const bias=(a.market_bias||'NEUTRO').toLowerCase();
      const delta = Number.isFinite(Number(a.surprise)) ? `${Number(a.surprise)>0?'+':''}${num(a.surprise,3)}` : 'N/D';
      const mins = Number(e.minutes_to_event); const timing = Number.isFinite(mins) ? (mins < 0 ? `há ${num(Math.abs(mins),0)} min` : `em ${num(mins,0)} min`) : '';
      return `<div class="dt-event"><div class="dt-event-time">${new Date(e.event_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}<small class="muted">${esc(timing)}</small></div><div class="dt-event-country">${esc(e.country_code)}</div><div class="dt-event-main"><strong>${esc(e.event)}</strong><div class="dt-event-values"><span class="dt-value">Anterior <b>${esc(e.previous||'—')}</b></span><span class="dt-value">Consenso <b>${esc(e.forecast||'—')}</b></span><span class="dt-value">Atual <b>${esc(e.actual||'—')}</b></span><span class="dt-value">Surpresa <b>${esc(delta)}</b></span></div><div class="dt-event-analysis">${esc(a.analysis||'—')}</div></div><a class="dt-event-bias ${bias}" href="${esc(e.url||'#')}" target="_blank" rel="noopener">${esc(a.market_bias||'NEUTRO')}</a></div>`;
    }).join('') : '<div class="muted">Nenhum evento 3★ de Brasil, EUA ou China encontrado para hoje.</div>';
  }

  function renderExternal(data) {
    const items = data.radar?.external_factors || [];
    $('externalMatrix').innerHTML = items.map(x => {
      const raw = Number(x.adjusted_change_percent ?? x.change_percent); const c = tone(raw);
      return `<div class="dt-external ${c}"><span>${esc(x.symbol)}</span><small>${esc(x.label)}</small><b>${pct(raw,2)}</b></div>`;
    }).join('') || '<div class="muted">Sem fatores externos suficientes.</div>';
  }

  function renderPlan(data) {
    const pieces = data.components || [];
    const dominant = pieces.slice().sort((a,b)=>Math.abs(Number(b.score||0))-Math.abs(Number(a.score||0))).slice(0,3);
    const plan = [];
    plan.push(`Direção contextual: <strong>${esc(data.direction)}</strong> com score ${esc(data.score)}.`);
    if (data.state === 'EVENTO') plan.push('Não antecipar a divulgação: aguarde o número e o primeiro repricing do WIN.');
    else if (data.state === 'CAUTELA') plan.push('Há evento 3★ próximo: reduza tamanho e evite iniciar posição perto do horário.');
    else if (data.state === 'DADOS DESATUALIZADOS') plan.push('O dado de captura está atrasado: não trate o score como leitura atual.');
    else plan.push('Use a direção como filtro; entrada somente com estrutura, VWAP, fluxo e invalidação definidos.');
    plan.push(`Confluências dominantes: ${dominant.map(x=>x.label).join(', ') || 'N/D'}.`);
    $('dtPlan').innerHTML = plan.map((x,i)=>`<div class="dt-plan-item"><i>${i+1}</i><div>${x}</div></div>`).join('');
  }

  function render(data) {
    const direction = $('dtDirection');
    direction.textContent = data.direction || 'AGUARDAR';
    direction.className = `dt-direction ${data.tone || 'neutral'}`;
    $('dtAction').textContent = data.action || 'Aguardando dados.';
    $('dtScore').textContent = data.score == null ? 'N/D' : `${Number(data.score)>0?'+':''}${num(data.score,1)}`;
    $('dtConfidence').textContent = `Confluência: ${data.confidence || '—'}`;
    $('dtState').textContent = data.state || '—';
    $('dtState').className = data.state === 'EVENTO' || data.state === 'CAUTELA' ? 'warning' : data.state === 'DADOS DESATUALIZADOS' ? 'negative' : 'positive';
    $('dtFreshness').textContent = data.capture_age_minutes == null ? 'Captura: N/D' : `Captura: ${num(data.capture_age_minutes,1)} min atrás`;
    $('dtTarget').textContent = data.market_target || 'WIN';
    renderComponents(data); renderDrivers(data); renderStocks(data); renderEvents(data); renderExternal(data); renderPlan(data);
    $('dtMessage').hidden = true;
  }

  async function load(force=false) {
    try {
      const r = await fetch(force ? '/api/daytrade/refresh/' : '/api/daytrade/', force ? {method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'}} : {headers:{Accept:'application/json'}});
      const data = await r.json(); if(!r.ok) throw new Error(data.message || `HTTP ${r.status}`); render(data);
    } catch (e) { $('dtMessage').hidden=false; $('dtMessage').textContent=e.message||'Falha ao carregar Daytrade.'; }
  }

  function clock(){ $('dtClock').textContent = new Date().toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'medium'}); }
  document.addEventListener('DOMContentLoaded',()=>{ $('dtRefresh')?.addEventListener('click',()=>load(true)); clock(); setInterval(clock,1000); load(false); setInterval(()=>load(false),60000); });
})();
