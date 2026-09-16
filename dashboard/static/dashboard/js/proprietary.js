(() => {
  "use strict";
  const $=id=>document.getElementById(id);
  let selectedId=null;
  const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
  const num=v=>Number(v||0).toLocaleString('pt-BR',{maximumFractionDigits:2});
  const csrf=()=>decodeURIComponent((document.cookie.split(';').find(x=>x.trim().startsWith('csrftoken='))||'').split('=').slice(1).join('='));
  const msg=(text,bad=false)=>{const n=$('propMessage');n.hidden=!text;n.className=`message ${bad?'error':'warning'}`;n.textContent=text};
  function decimalInput(id){
    let text=String($(id).value||'0').trim().replace(/R\$/g,'').replace(/\s/g,'');
    if(!text) return '0';
    const lastComma=text.lastIndexOf(',');
    const lastDot=text.lastIndexOf('.');
    if(lastComma>=0 && lastDot>=0){
      if(lastComma>lastDot) text=text.replace(/\./g,'').replace(',','.');
      else text=text.replace(/,/g,'');
    }else if(lastComma>=0){
      text=text.replace(/\./g,'').replace(',','.');
    }
    return text;
  }
  function fillAccount(a){ selectedId=a?.id||null; $('accountSelect').value=a?.id||''; $('accountName').value=a?.name||''; $('planName').value=a?.plan_name||''; $('planValue').value=a?.plan_value??0; $('startingBalance').value=a?.starting_balance??0; $('maxLoss').value=a?.max_loss??0; $('approvalTarget').value=a?.approval_target??0; $('maxContracts').value=a?.max_contracts_day??0; $('miniIndexFee').value=a?.mini_index_fee??0.35; $('miniDollarFee').value=a?.mini_dollar_fee??1.35; $('accountNotes').value=a?.notes||''; $('startDate').value=a?.start_date||''; }
  async function loadAccounts(){
    const r=await fetch('/api/proprietaria/accounts/');
    const d=await r.json();
    const s=$('accountSelect');
    s.innerHTML='<option value="">Selecione...</option>'+d.accounts.map(a=>`<option value="${a.id}">${a.name}${a.plan_name?' · '+a.plan_name:''}</option>`).join('');
    const selected=d.accounts.find(a=>Number(a.id)===Number(selectedId));
    if(selected){
      selectedId=selected.id;
      fillAccount(selected);
      await loadLatest();
    } else if(d.accounts.length){
      selectedId=d.accounts[0].id;
      fillAccount(d.accounts[0]);
      await loadLatest();
    } else {
      selectedId=null;
      fillAccount(null);
    }
  }
  async function createAccount(){
    const name=String($('newAccountName').value||'').trim();
    if(!name){$('newAccountName').focus();throw Error('Informe o nome da conta.')}
    const payload={name,firm:'MIDE',plan_name:$('newPlanName').value,plan_value:decimalInput('newPlanValue'),starting_balance:decimalInput('newStartingBalance'),max_loss:decimalInput('newMaxLoss'),approval_target:decimalInput('newApprovalTarget'),max_contracts_day:Number($('newMaxContracts').value||0),mini_index_fee:decimalInput('newMiniIndexFee'),mini_dollar_fee:decimalInput('newMiniDollarFee'),notes:$('newAccountNotes').value,start_date:$('newStartDate').value};
    const r=await fetch('/api/proprietaria/accounts/create/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),Accept:'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.message||'Falha ao criar conta');selectedId=d.account.id;await loadAccounts();fillAccount(d.account);$('accountDialog').close();msg('Conta salva no banco.');
  }
  function statusClass(s){return s==='approved'?'ok':s==='eliminated'?'bad':''}
  function render(e){
    const a=e.account,m=e.metrics||{}; $('configStatus').textContent=`${a.firm} · ${a.plan_name||'Plano não informado'}`; const sc=$('statusCard');sc.className=`prop-status-card panel ${statusClass(e.status)}`; $('propStatus').textContent=e.status_label.toUpperCase(); const period=m.period_start?` · desde ${new Date(`${m.period_start}T00:00:00`).toLocaleDateString('pt-BR')}`:''; const excluded=m.excluded_before_start?` · ${m.excluded_before_start} anteriores ignorados`:''; $('propStatusDetail').textContent=`${e.trade_count} trades considerados${period}${excluded} · avaliado em ${new Date(e.evaluated_at).toLocaleString('pt-BR')}`;
    $('propResult').textContent=money(e.current_result);$('propResult').className=e.current_result>0?'positive':e.current_result<0?'negative':'';$('propRemaining').textContent=money(e.remaining_to_target);$('propBuffer').textContent=money(e.remaining_loss_buffer);$('evaluationTime').textContent=new Date(e.evaluated_at).toLocaleString('pt-BR');
    $('riskMetrics').innerHTML=[['Pior dia',money(e.max_daily_loss)],['Maior perda individual',money(e.max_trade_loss)],['Risco individual / limite',num(e.risk_ratio_percent)+'%'],['Margem restante',money(e.remaining_loss_buffer)],['Custos operacionais',money(e.operational_costs)]].map(x=>`<div class="metric-row"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');
    $('planChecks').innerHTML=[['Resultado / plano',e.performance_ok?'OK':'REVISAR',e.performance_ok],['Contratos/dia',`${e.max_contracts_observed} / ${a.max_contracts_day||'sem limite'}`,e.contract_limit_ok],['Controle de risco',e.risk_ok?'OK':'REVISAR',e.risk_ok]].map(x=>`<div class="check-row ${x[2]?'ok':'bad'}"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');
    $('perfMetrics').innerHTML=[['Win rate',num(m.win_rate)+'%'],['Trades ganhos',num(m.winning_trades)],['Trades perdidos',num(m.losing_trades)],['Profit factor',m.profit_factor==null?'N/D':num(m.profit_factor)],['Resultado bruto',money(e.gross_result)],['Custos operacionais',money(e.operational_costs)],['Resultado / saldo inicial',m.result_vs_starting_balance_percent==null?'N/D':num(m.result_vs_starting_balance_percent)+'%']].map(x=>`<div class="metric-row"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('');
    $('guidance').innerHTML=(e.guidance||[]).map(g=>`<div class="guidance-item">${g}</div>`).join('')||'<div class="empty-state">Sem orientações adicionais.</div>';
  }
  async function loadLatest(){if(!selectedId)return;try{const r=await fetch(`/api/proprietaria/accounts/${selectedId}/latest/`);if(r.status===404){msg('Conta selecionada sem avaliação. Importe um relatório do Profit.');return}const d=await r.json();render(d.evaluation);await loadHistory()}catch(e){msg(e.message,true)}}
  async function loadHistory(){if(!selectedId)return;const r=await fetch(`/api/proprietaria/accounts/${selectedId}/history/`);const d=await r.json();$('historyRows').innerHTML=d.evaluations.length?d.evaluations.map(e=>`<tr><td>${new Date(e.evaluated_at).toLocaleString('pt-BR')}</td><td>${e.report_filename}</td><td>${money(e.current_result)}</td><td><span class="status-pill ${e.status}">${e.status_label}</span></td><td>${e.max_contracts_observed}</td><td>${money(e.max_trade_loss)}</td></tr>`).join(''):'<tr><td colspan="6" class="muted">Nenhuma avaliação salva.</td></tr>'}
  async function importReport(file){if(!selectedId){msg('Selecione ou crie uma conta antes de importar o relatório.',true);return}msg('Importando e avaliando o relatório...');const f=new FormData();f.append('file',file);f.append('account_id',selectedId);try{const r=await fetch('/api/proprietaria/evaluate/',{method:'POST',headers:{'X-CSRFToken':csrf(),Accept:'application/json'},body:f});const d=await r.json();if(!r.ok)throw Error(d.message||'Falha na avaliação');render(d.evaluation);await loadHistory();msg(`Avaliação salva: ${d.evaluation.status_label}.`)}catch(e){msg(e.message,true)}}
  $('accountSelect').addEventListener('change',async e=>{selectedId=Number(e.target.value)||null;if(selectedId){await loadAccounts()}else{fillAccount(null)}});
  $('newAccount').addEventListener('click',()=>{$('newAccountForm').reset();$('accountDialog').showModal();setTimeout(()=>$('newAccountName').focus(),50)});
  $('closeAccountDialog').addEventListener('click',()=>$('accountDialog').close());
  $('cancelAccountDialog').addEventListener('click',()=>$('accountDialog').close());
  $('createAccount').addEventListener('click',()=>createAccount().catch(e=>msg(e.message,true)));
  $('saveAccount').addEventListener('click',async()=>{if(!selectedId){$('newAccount').click();return}const payload={name:$('accountName').value,plan_name:$('planName').value,plan_value:decimalInput('planValue'),starting_balance:decimalInput('startingBalance'),max_loss:decimalInput('maxLoss'),approval_target:decimalInput('approvalTarget'),max_contracts_day:Number($('maxContracts').value||0),mini_index_fee:decimalInput('miniIndexFee'),mini_dollar_fee:decimalInput('miniDollarFee'),notes:$('accountNotes').value,start_date:$('startDate').value};try{const r=await fetch(`/api/proprietaria/accounts/${selectedId}/update/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),Accept:'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.message||'Falha ao salvar');await loadAccounts();fillAccount(d.account);await loadLatest();msg('Configuração da conta atualizada. Avaliações históricas permanecem salvas.')}catch(e){msg(e.message,true)}});
  $('propFile').addEventListener('change',e=>{const f=e.target.files?.[0];if(f)importReport(f)});
  document.addEventListener('DOMContentLoaded',loadAccounts);
})();
