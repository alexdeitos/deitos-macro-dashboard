(() => {
  const $ = id => document.getElementById(id);
  const csrf = () => document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '';
  const money = v => v == null ? 'N/D' : Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const num = (v,d=2) => v == null || !Number.isFinite(Number(v)) ? 'N/D' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
  let currentTrade = null;

  function showMessage(text, bad=false){
    const el=$('validationMessage'); el.hidden=false; el.textContent=text; el.className=`message ${bad?'error':'warning'}`;
  }

  function resultClass(v){ return v>0?'result-win':v<0?'result-loss':'result-flat'; }

  function renderReport(report){
    $('perfTrades').textContent = num(report.total_rows,0);
    $('perfNet').textContent = money(report.total_result);
    $('perfNet').className = report.total_result>0?'positive':report.total_result<0?'negative':'';
    $('perfPF').textContent = `PF: ${report.profit_factor == null ? 'N/D' : num(report.profit_factor,2)}`;
    $('perfWinrate').textContent = `${num(report.win_rate,1)}%`;
    $('perfWL').textContent = `${report.wins} ganhos · ${report.losses} perdas · ${report.breakevens} zero`;
    $('perfExtremes').textContent = `${money(report.max_win)} / ${money(report.max_loss)}`;
    $('perfAccount').textContent = `${report.account_label || 'Conta não informada'} · ${report.period_start || '—'} → ${report.period_end || '—'}`;
    $('perfPeriod').textContent = `${report.period_start || '—'} → ${report.period_end || '—'}`;
    $('instrumentSummary').innerHTML = Object.entries(report.by_instrument||{}).map(([k,v]) =>
      `<div class="instrument-card"><strong>${k}</strong><span>${v.trades} trades · ${num(v.win_rate,1)}%</span><small>Resultado ${money(v.net)}</small></div>`
    ).join('') || '<span class="muted">Sem dados agregados.</span>';
    renderTrades(report.trades||[]);
  }

  function renderTrades(trades){
    $('performanceRows').innerHTML = trades.length ? trades.map(t => `
      <tr>
        <td>${new Date(t.opened_at).toLocaleString('pt-BR')}</td>
        <td><strong>${t.symbol}</strong></td>
        <td>${t.side_label}</td>
        <td>${Math.max(t.buy_qty||0,t.sell_qty||0)}</td>
        <td>${num(t.entry_price,2)}</td>
        <td>${num(t.exit_price,2)}</td>
        <td class="${resultClass(t.result)}">${money(t.result)}</td>
        <td>${t.validation_score ? `${t.validation_score}/10` : 'Não avaliado'}${t.justification ? ' · ✓' : ''}</td>
        <td>
          <button class="small-button" data-edit="${t.id}">Justificar</button>
          <button class="small-button" data-diary="${t.id}" ${t.in_diary?'disabled':''}>${t.in_diary?'No diário ✓':'Salvar no Diário'}</button>
        </td>
      </tr>`).join('') : '<tr><td colspan="9" class="muted">Nenhuma operação encontrada.</td></tr>';
    document.querySelectorAll('[data-edit]').forEach(b=>b.addEventListener('click',()=>openTrade(Number(b.dataset.edit))));
    document.querySelectorAll('[data-diary]').forEach(b=>b.addEventListener('click',()=>saveDiary(Number(b.dataset.diary))));
  }

  async function load(){
    try{
      const r=await fetch('/api/performance/latest/',{headers:{Accept:'application/json'}});
      if(r.status===404){ return; }
      const data=await r.json(); if(!r.ok) throw new Error(data.message||`HTTP ${r.status}`);
      renderReport(data.report);
    }catch(e){ showMessage(e.message||'Falha ao carregar o relatório.',true); }
  }

  async function importReport(file){
    showMessage('Importando relatório do Profit...');
    const form=new FormData(); form.append('file',file);
    try{
      const r=await fetch('/api/performance/import/',{method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'},body:form});
      const data=await r.json(); if(!r.ok) throw new Error(data.message||'Falha na importação.');
      renderReport(data.report); showMessage(`Relatório importado: ${data.report.total_rows} operações.`);
    }catch(e){ showMessage(e.message||'Falha na importação.',true); }
  }

  async function openTrade(id){
    const r=await fetch('/api/performance/latest/',{headers:{Accept:'application/json'}}); const data=await r.json();
    currentTrade=(data.report.trades||[]).find(x=>x.id===id); if(!currentTrade) return;
    $('dialogTitle').textContent=`Validar ${currentTrade.symbol}`;
    $('dialogMeta').innerHTML=`${currentTrade.side_label} · ${new Date(currentTrade.opened_at).toLocaleString('pt-BR')} · ${num(currentTrade.entry_price,2)} → ${num(currentTrade.exit_price,2)} · <strong class="${resultClass(currentTrade.result)}">${money(currentTrade.result)}</strong>`;
    $('justification').value=currentTrade.justification||'';
    $('validationScore').value=currentTrade.validation_score||0;
    $('setupNote').value=currentTrade.setup_note||'';
    $('tradeDialog').showModal();
  }

  async function saveValidation(){
    if(!currentTrade) return;
    const payload={justification:$('justification').value,score:Number($('validationScore').value||0),setup_note:$('setupNote').value};
    const r=await fetch(`/api/performance/trades/${currentTrade.id}/validate/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),Accept:'application/json'},body:JSON.stringify(payload)});
    const data=await r.json(); if(!r.ok) throw new Error(data.message||'Falha ao salvar.');
    currentTrade=data.trade; $('tradeDialog').close(); await load(); showMessage('Validação salva.');
  }

  async function saveDiary(id){
    const r=await fetch(`/api/performance/trades/${id}/diary/`,{method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'}});
    const data=await r.json(); if(!r.ok) throw new Error(data.message||'Falha ao salvar no diário.');
    await load(); showMessage(data.created?'Trade enviado para o Diário de Trade.':'Trade já estava vinculado ao diário.');
  }

  document.addEventListener('DOMContentLoaded',()=>{
    $('performanceFile')?.addEventListener('change',e=>{const f=e.target.files?.[0]; if(f) importReport(f);});
    $('saveValidation')?.addEventListener('click',()=>saveValidation().catch(e=>showMessage(e.message,true)));
    $('saveDiary')?.addEventListener('click',()=>currentTrade&&saveDiary(currentTrade.id).then(()=>$('tradeDialog').close()).catch(e=>showMessage(e.message,true)));
    load();
  });
})();
