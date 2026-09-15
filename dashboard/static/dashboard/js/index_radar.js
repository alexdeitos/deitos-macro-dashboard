(() => {
  const $ = (id) => document.getElementById(id);
  const num = (v, d=2) => v == null || !Number.isFinite(Number(v)) ? 'N/D' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pct = (v, d=2) => v == null || !Number.isFinite(Number(v)) ? 'N/D' : `${Number(v)>0?'+':''}${num(v,d)}%`;
  const tone = (v) => v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral';
  const csrf = () => document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';

  function row(item, isContribution=false) {
    const value = isContribution ? item.contribution_percent : (item.adjusted_change_percent ?? item.change_percent);
    const cls = tone(value);
    const width = Math.min(100, Math.abs(Number(value || 0)) * (isContribution ? 30 : 35));
    return `<div class="driver-row ${cls}"><span class="symbol">${item.symbol || ''}</span><div class="bar-shell"><div class="bar" style="width:${width}%"></div></div><span class="value">${pct(value,isContribution?3:2)}${item.weight_percent ? ` · ${num(item.weight_percent,2)}%` : ''}</span></div>`;
  }

  function render(data) {
    $('radarDirection').textContent = data.direction || 'AGUARDAR';
    $('radarDirection').className = data.tone || 'neutral';
    $('radarScore').textContent = data.score == null ? 'N/D' : `${data.score > 0 ? '+' : ''}${num(data.score,1)}`;
    $('radarConfidence').textContent = `Confiança: ${data.confidence || '—'}`;
    $('radarCoverage').textContent = data.coverage?.ibov_weight_percent == null ? 'N/D' : `${num(data.coverage.ibov_weight_percent,1)}%`;
    $('radarAssets').textContent = `${data.coverage?.captured_assets || 0} / ${data.coverage?.ibov_total_assets || 0} ativos`;
    $('radarAgreement').textContent = data.agreement_percent == null ? 'N/D' : `${num(data.agreement_percent,1)}%`;
    $('radarUpdated').textContent = data.generated_at ? new Date(data.generated_at).toLocaleString('pt-BR') : '—';
    $('radarSource').textContent = `Excel/Profit: ${data.excel_capture?.status_label || '—'}${data.excel_capture?.observed_at ? ' · ' + new Date(data.excel_capture.observed_at).toLocaleTimeString('pt-BR') : ''}`;
    $('weightsSource').textContent = `Pesos: ${data.coverage?.weights_source || '—'}`;
    $('targetSymbol').textContent = `Alvo: ${data.target || '—'}`;

    const stocks = data.stock_pressure || {};
    $('weightedChange').textContent = pct(stocks.weighted_change_percent,3);
    $('positiveWeight').textContent = stocks.positive_weight_percent == null ? 'N/D' : `${num(stocks.positive_weight_percent,2)}%`;
    $('negativeWeight').textContent = stocks.negative_weight_percent == null ? 'N/D' : `${num(stocks.negative_weight_percent,2)}%`;
    $('stockDrivers').innerHTML = (stocks.all || []).slice(0,18).map(x=>row(x,true)).join('') || '<div class="muted">Nenhuma ação ponderada capturada.</div>';
    $('topPositive').innerHTML = (stocks.top_positive || []).slice(0,12).map(x=>row(x,true)).join('') || '<div class="muted">Sem pressão compradora disponível.</div>';
    $('topNegative').innerHTML = (stocks.top_negative || []).slice(0,12).map(x=>row(x,true)).join('') || '<div class="muted">Sem pressão vendedora disponível.</div>';
    $('externalDrivers').innerHTML = (data.external_factors || []).map(x=>row(x,false)).join('') || '<div class="muted">Sem drivers externos capturados.</div>';

    const corr = data.correlations || [];
    $('correlationTable').innerHTML = corr.length ? `<div class="corr-row corr-head"><span>Fator</span><span>Corr.</span><span>Força</span><span>N</span></div>` + corr.map(x => {
      const c=Number(x.correlation), cls=tone(c);
      return `<div class="corr-row ${cls}"><span>${x.label}</span><span>${c>0?'+':''}${num(c,3)}</span><span><div class="corr-bar"><div class="corr-fill" style="width:${Math.min(100,Math.abs(c)*100)}%"></div></div></span><span>${x.sample_size}</span></div>`;
    }).join('') : '<div class="muted">Ainda não há amostra coincidente suficiente para calcular correlações.</div>';
    $('contextLines').innerHTML = (data.context || []).map(x=>`<div class="context-line">${x}</div>`).join('') || '<div class="muted">Aguardando captura.</div>';
  }

  async function load(force=false) {
    try {
      const url = force ? '/api/radar-indice/refresh/' : '/api/radar-indice/';
      const opts = force ? {method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'}} : {headers:{Accept:'application/json'}};
      const r = await fetch(url, opts); const data = await r.json();
      if (!r.ok) throw new Error(data.message || `HTTP ${r.status}`);
      render(data);
      $('radarMessage').hidden = true;
    } catch (e) {
      $('radarMessage').hidden = false; $('radarMessage').textContent = e.message || 'Falha ao carregar o radar.';
    }
  }

  async function importFile(file) {
    const form = new FormData(); form.append('file', file);
    $('radarMessage').hidden = false; $('radarMessage').textContent = 'Importando capturas...';
    try {
      const r = await fetch('/api/capturas/import/', {method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'},body:form});
      const data = await r.json(); if (!r.ok) throw new Error(data.message || 'Falha na importação.');
      $('radarMessage').textContent = `Importação concluída: ${data.imported} registros inseridos.`;
      await load(true);
    } catch (e) { $('radarMessage').textContent = e.message || 'Falha na importação.'; }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('refreshRadar')?.addEventListener('click', () => load(true));
    $('captureFile')?.addEventListener('change', e => { const f=e.target.files?.[0]; if(f) importFile(f); });
    load(false);
    window.setInterval(() => load(false), 60000);
  });
})();
