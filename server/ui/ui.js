const el=id=>document.getElementById(id);
let token=null,who=null,org=null,assets=[],evidences=[],models=[],runs=[],initiatives=[];
let authMode='legacy', csrfCookie=null, refreshGeneration=0;
const follow={draft:'engineering_review',engineering_review:'financial_review',financial_review:'approval_pending',approval_pending:'approved',approved:'in_execution',in_execution:'verification_pending',verification_pending:'verified'};
function info(msg,error=false){el('notice').textContent=msg;el('notice').className='notice'+(error?' error':'')}
async function api(path,method='GET',body=null){
  const headers={'Accept':'application/json'};
  if(token && authMode==='legacy')headers.Authorization='Bearer '+token;
  if(authMode==='oidc' && !['GET','HEAD','OPTIONS'].includes(method)){
    const pair=document.cookie.split('; ').find(x=>x.startsWith(csrfCookie+'='));
    if(pair)headers['X-CSRF-Token']=decodeURIComponent(pair.substring(csrfCookie.length+1));
  }
  if(body!==null)headers['Content-Type']='application/json';
  const r=await fetch(path,{method,headers,body:body!==null?JSON.stringify(body):undefined,cache:'no-store',credentials:'same-origin'});
  const txt=await r.text();let data={};try{data=JSON.parse(txt)}catch{data={detail:txt}}
  if(!r.ok)throw Error(`${r.status}: ${typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)}`);
  return data;
}
function selected(id){return el(id).value}
function choices(id,items,toTitle,choose){const sel=el(id),prior=sel.value;sel.replaceChildren();for(const row of items){let op=document.createElement('option');op.value=row.id;op.textContent=toTitle(row);sel.append(op)}if(items.some(v=>v.id===prior))sel.value=prior;else if(choose)sel.value=choose;}
function own(){if(!org)throw Error('Укажите организацию');return '/v7/orgs/'+encodeURIComponent(org)}
const sample={source_voltage_kv_ll:20,load_p_mw:5,load_q_mvar:2,line_r_ohm_per_phase:.3,line_x_ohm_per_phase:.4,period_hours:100,reference_name:'Synthetic Magadan research feeder — NOT physical network'};
async function refresh(){
  if(!org)return;const base=own(), requestOrg=org, generation=++refreshGeneration;
  const loaded=await Promise.all([
      api(base+'/assets'),api(base+'/evidence'),api(base+'/models'),api(base+'/runs'),api(base+'/initiatives')]);
  if(org!==requestOrg || generation!==refreshGeneration)return;
  [assets,evidences,models,runs,initiatives]=loaded;
  choices('asset',assets,x=>x.name+' ('+x.classification+')');
  choices('evidence-list',evidences,x=>x.kind+' — '+x.status+' — '+x.id.slice(0,8));
  choices('attached-evidence',evidences.filter(x=>x.status==='accepted'),x=>x.kind+' — '+x.id.slice(0,8));
  choices('model-list',models,x=>x.algorithm+' — '+x.status+' — '+x.id.slice(0,8));
  choices('run-list',runs,x=>x.reference_name+' — '+x.id.slice(0,8));
  choices('initiative-list',initiatives,x=>x.title+' — '+x.state);
  updateTransition();
  await refreshStudies();
  await refreshRadial();
  await refreshProgrammes();
  await refreshHandoffs();
  await refreshAssurancePacks();
  refreshV77Selectors();
  await refreshV78();
  await refreshV79();
  await refreshV8();
  refreshV82();
  refreshV83();
}
function updateTransition(){const i=initiatives.find(x=>x.id===selected('initiative-list'));const s=el('next-state');s.replaceChildren();if(i&&follow[i.state]){const op=document.createElement('option');op.value=follow[i.state];op.textContent=follow[i.state]+' · revision '+i.revision;s.append(op)}}
async function perform(fn){try{await fn();await refresh()}catch(e){info(e.message,true)}}
el('login-form').addEventListener('submit',async e=>{e.preventDefault();try{const fd=new FormData(e.target);const t=await api('/v7/auth/login','POST',{email:fd.get('email'),password:fd.get('password')});token=t.access_token;who=await api('/v7/me');el('identity').textContent=who.email;el('auth-card').hidden=true;el('session').hidden=false;el('lab').hidden=false;el('login-result').textContent='';const sel=el('org');sel.replaceChildren();for(const m of who.organizations){const opt=document.createElement('option');opt.value=m.org_id;opt.textContent=m.org_id+' ('+m.role+')';sel.append(opt)}org=sel.value;el('role-info').textContent='Серверные роли: '+who.organizations.map(x=>x.org_id+':'+x.role).join(', ');el('payload').value=JSON.stringify(sample,null,2);await refresh();info('Подключено к серверу. Лабораторные входные данные синтетические.')}catch(e){token=null;info(e.message,true)}});
el('logout').addEventListener('click',async()=>{try{if(token || authMode==='oidc')await api('/v7/auth/logout','POST',{})}catch(e){info(e.message,true);return;}token=null;who=null;org=null;el('lab').hidden=true;el('session').hidden=true;el('auth-card').hidden=false;el('login-form').reset();info('Выход выполнен. Для новой роли нужен новый вход с отдельной учётной записью.')});
el('org').addEventListener('change',()=>perform(async()=>{org=el('org').value;clearTenantView();await refresh();info('Контекст переключён на '+org+'; права проверяются сервером')}));
el('fill-sample').addEventListener('click',()=>{el('kind').value='grid_input';el('source_ref').value='SYNTHETIC-REFERENCE-CASE-2026';el('payload').value=JSON.stringify(sample,null,2);info('Загружен только синтетический эталон; реальные параметры сетей отсутствуют.')});
el('create-evidence').addEventListener('click',()=>perform(async()=>{const body={asset_id:selected('asset'),kind:selected('kind'),source_ref:el('source_ref').value,payload:JSON.parse(el('payload').value)};const x=await api(own()+'/evidence','POST',body);info('Документ добавлен: '+x.id+'. Статус: '+x.status)}));
for(const [id,accepted] of [['accept-evidence',true],['reject-evidence',false]])el(id).addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/evidence/'+selected('evidence-list')+'/review','POST',{accepted,note:'Independent laboratory review with synthetic assumptions'});info('Проверка документа: '+JSON.stringify(x))}));
el('create-model').addEventListener('click',()=>perform(async()=>{const m=await api(own()+'/models','POST',{asset_id:selected('asset'),algorithm:'balanced_two_bus_AC_PQ_lab_v1',params:{}});info('Версия модели создана: '+m.id)}));
el('accept-model').addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/models/'+selected('model-list')+'/review','POST',{accepted:true,note:'Lab numerical solver with analytic reference check'});info('Модель проверена: '+JSON.stringify(x))}));
el('calculate').addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/runs','POST',{asset_id:selected('asset'),evidence_id:selected('evidence-list'),model_id:selected('model-list')});el('calc-result').textContent=JSON.stringify(x,null,2);info('Расчёт на сервере выполнен: '+x.id)}));
el('run-list').addEventListener('change',()=>perform(async()=>{const x=await api(own()+'/runs/'+selected('run-list'));el('calc-result').textContent=JSON.stringify(x,null,2)}));
el('create-initiative').addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/initiatives','POST',{asset_id:selected('asset'),run_id:selected('run-list'),title:el('initiative-title').value,effect_key:el('effect-key').value});info('Черновик инвестиционного решения '+x.id+'; расчёт '+x.run_id)}));
el('attach-evidence').addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/initiatives/'+selected('initiative-list')+'/evidence','POST',{evidence_id:selected('attached-evidence')});info('Проверенный документ добавлен к инициативе '+x.initiative_id)}));
el('initiative-list').addEventListener('change',()=>perform(async()=>{updateTransition();const x=await api(own()+'/initiatives/'+selected('initiative-list')+'/dossier');el('dossier-result').textContent=JSON.stringify(x,null,2)}));
el('transition').addEventListener('click',()=>perform(async()=>{const i=initiatives.find(x=>x.id===selected('initiative-list'));if(!i)throw Error('Выберите инициативу');const x=await api(own()+'/initiatives/'+i.id+'/transition','POST',{to_state:selected('next-state'),expected_revision:i.revision});const d=await api(own()+'/initiatives/'+i.id+'/dossier');el('dossier-result').textContent=JSON.stringify(d,null,2);info('Решение '+i.id+': '+x.state+'; revision '+x.revision)}));
el('verify-audit').addEventListener('click',()=>perform(async()=>{const x=await api(own()+'/audit/verify');el('audit-result').textContent=JSON.stringify(x,null,2);info(x.valid?'HMAC цепочка проверена; внешняя WORM якорная запись ещё не реализована.':'НАРУШЕНИЕ ЦЕЛОСТНОСТИ',!x.valid)}));

function clearTenantView(){
  refreshGeneration++;
  assets=[];evidences=[];models=[];runs=[];initiatives=[];
  studyRuns=[];radialRuns=[];radialDossiers=[];researchProgrammes=[];researchHandoffs=[];assurancePacks=[];annualDossiers78=[];
  for(const id of ['handoff-left','handoff-right','handoff-programme','handoff-list','programme-study-ids','programme-finance-ids','programme-list','radial-asset','radial-baseline','radial-alternative','radial-dossier-list'])el(id).replaceChildren();
  for(const id of ['study-run-list','study-left','study-right','study-asset'])el(id).replaceChildren();
  for(const id of ['asset','evidence-list','attached-evidence','model-list','run-list','initiative-list','next-state'])el(id).replaceChildren();
  for(const id of ['assurance-handoffs','assurance-programme','assurance-routing-handoff','assurance-list'])el(id).replaceChildren();
  for(const id of ['calc-result','dossier-result','audit-result','programme-output','programme-budget-result','handoff-result','handoff-assurance','assurance-output'])el(id).textContent='';
  for(const id of ['reference-study','reference-assurance','v78-programme','v78-baseline','v78-proposed','v78-history'])el(id).replaceChildren();
  for(const id of ['reference-request','reference-submission','reference-comparison-id'])el(id).value='';
  for(const id of ['reference-result','reference-finance-output','v78-output'])el(id).textContent='';
}
  for(const id of ['v79-source','v79-history','v79-mv-list','v79-boundary'])el(id).replaceChildren();
  el('v79-output').textContent='';el('v79-mv-output').textContent='';
  for(const id of ['v8-boundary-asset','v8-boundary-map','v8-overlap-a','v8-overlap-b','v8-parent'])el(id).replaceChildren();
  el('v8-boundary-output').textContent='';
  el('v82-plot').replaceChildren();
  el('v82-output').textContent='';
  el('v82-assessment').textContent='Новый контекст: исходные расчёты очищены.';
  for(const id of ['v82-mae','v82-rmse','v82-coverage','v82-point'])el(id).textContent='—';
  el('v82-case').value='';
async function restoreCorporateSession(){
  who=await api('/v7/me');
  el('identity').textContent=who.email;
  el('auth-card').hidden=true;el('session').hidden=false;el('lab').hidden=false;
  const selector=el('org');selector.replaceChildren();
  for(const m of who.organizations){const option=document.createElement('option');option.value=m.org_id;option.textContent=m.org_id+' ('+m.role+')';selector.append(option);}
  org=selector.value;
  el('role-info').textContent=who.organizations.map(x=>x.org_id+': '+x.role).join(', ');
  el('payload').value=JSON.stringify(sample,null,2);
  await refresh();
  info('\u0412\u0445\u043e\u0434 OIDC: \u0441\u0435\u0441\u0441\u0438\u044f \u0438 \u043f\u0440\u0430\u0432\u0430 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u044b \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c.');
}
async function initializeIdentity(){
  try{
    const r=await fetch('/v71/auth/config',{cache:'no-store',credentials:'same-origin'});
    if(!r.ok)return;
    const config=await r.json();
    if(config.mode!=='oidc')return;
    authMode='oidc';csrfCookie=config.csrf_cookie;
    el('login-form').hidden=true;
    const link=document.createElement('a');link.href=config.start;link.id='corporate-login';link.className='primary';
    link.textContent='\u041a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0432\u0445\u043e\u0434';
    el('auth-card').append(link);
    try{await restoreCorporateSession();}catch{clearTenantView();}
  }catch(e){info(e.message,true);}
}
initializeIdentity();

// V7.2: exploratory multi-domain laboratory. No promotion to investment decisions.
let studySamples={},studyRuns=[];
const studyBase=()=>'/v72/orgs/'+encodeURIComponent(org)+'/studies';
async function loadSamples(){
  try{const r=await fetch('/lab-assets/samples_v72.json',{cache:'no-store'});
    if(r.ok)studySamples=await r.json();
  }catch(e){info('No V7.2 examples available: '+e.message,true)}
}
function studySample(){
 const module=selected('study-module');
 if(studySamples[module])el('study-case').value=JSON.stringify(studySamples[module],null,2);
}
async function refreshStudies(){
 if(!org)return;
 const requestOrg=org;
 const studies=await api(studyBase());
 if(org!==requestOrg)return;
 studyRuns=studies;
 choices('study-asset',assets,x=>x.name);
 for(const name of ['study-run-list','study-left','study-right']){
   choices(name,studyRuns,x=>x.module+' / '+x.id.slice(0,8));
 }
}
el('study-module').addEventListener('change',studySample);
el('study-load').addEventListener('click',studySample);
el('study-execute').addEventListener('click',()=>perform(async()=>{
  const module=selected('study-module');
  const x=await api(studyBase(),'POST',{
   asset_id:selected('study-asset'),module,source_ref:'SYNTHETIC-HYDRO72',
   scenario_group:el('study-group').value,case:JSON.parse(el('study-case').value),
   scope:'SYNTHETIC_LAB_ONLY'
  });
  el('study-result').textContent=JSON.stringify(x,null,2);
  info('Server study '+x.id+' recorded; industrial approval is explicitly prohibited.');
}));
el('study-reproduce').addEventListener('click',()=>perform(async()=>{
 const x=await api(studyBase()+'/'+selected('study-run-list')+'/reproduce','POST',{});
 el('study-result').textContent=JSON.stringify(x,null,2);
 info(x.reproduced?'Study recalculated with pinned engine.':'Study verification failed',!x.reproduced);
}));
el('study-open').addEventListener('click',()=>perform(async()=>{
 const x=await api(studyBase()+'/'+selected('study-run-list'));
 el('study-result').textContent=JSON.stringify(x,null,2);
}));
el('study-compare').addEventListener('click',()=>perform(async()=>{
 const x=await api(studyBase()+'/compare-pair','POST',{
  left_run_id:selected('study-left'),right_run_id:selected('study-right')
 });
 el('study-comparison').textContent=JSON.stringify(x,null,2);
 info('Comparison is illustrative only. Equivalent physical baselines are NOT confirmed.');
}));
loadSamples().then(studySample);


// V7.3 synthetic radial feeder and finance evidence, separate from approval.
let radialRuns=[],radialDossiers=[],radialExamples={};
const radialBase=()=>'/v73/orgs/'+encodeURIComponent(org);
async function loadRadialSamples(){
 try{const r=await fetch('/lab-assets/radial_sample_v73.json',{cache:'no-store'});
  if(r.ok){radialExamples=await r.json();el('radial-case').value=JSON.stringify(radialExamples.case,null,2);
   el('radial-finance').value=JSON.stringify(radialExamples.finance,null,2)}
 }catch(e){info('V7.3 samples unavailable: '+e.message,true)}
}
async function refreshRadial(){
 if(!org)return;
 const requested=org;
 const [a,b]=await Promise.all([api(radialBase()+'/radial-runs'),api(radialBase()+'/economic-dossiers')]);
 if(org!==requested)return;
 radialRuns=a;radialDossiers=b;
 choices('radial-asset',assets,x=>x.name+' ('+x.classification+')');
 for(const id of ['radial-baseline','radial-alternative'])
  choices(id,radialRuns,x=>x.id.slice(0,8)+' · '+Number(x.loss_mwh).toFixed(5)+' МВт·ч');
 choices('radial-dossier-list',radialDossiers,x=>x.benefit_key+' / '+x.id.slice(0,8));
}
el('radial-sample').addEventListener('click',()=>{
 el('radial-case').value=JSON.stringify(radialExamples.case,null,2);
 info('Загружен учебный исходный сценарий — не параметры объектов Магаданской области.');
});
el('radial-improve').addEventListener('click',()=>{
 try{const x=JSON.parse(el('radial-case').value);
  const baseNode=x.nodes.find(z=>z.node_id==='n1');
  if(!baseNode)throw Error('В примере отсутствует n1');
  baseNode.r_ohm_per_phase=0.13;
  el('radial-case').value=JSON.stringify(x,null,2);
  info('Изменено учебное сопротивление n1, прочие условия сохранены. Создайте второй расчёт.');
 }catch(e){info(e.message,true)}
});
el('radial-create').addEventListener('click',()=>perform(async()=>{
 const x=await api(radialBase()+'/radial-runs','POST',{
  asset_id:selected('radial-asset'),scenario_group:el('radial-group').value,
  source_ref:'SYNTHETIC-V73-MAGADAN-LAB',scope:'SYNTHETIC_LAB_ONLY',
  case:JSON.parse(el('radial-case').value)});
 el('radial-output').textContent=JSON.stringify(x,null,2);
 info('Создан SYNTHETIC расчёт '+x.run_id+'. Запрещён для инвестиционного утверждения.');
}));
el('radial-compare').addEventListener('click',()=>perform(async()=>{
 const x=await api(radialBase()+'/radial-runs/compare','POST',{
  baseline_run_id:selected('radial-baseline'),proposed_run_id:selected('radial-alternative')});
 el('radial-comparison').textContent=JSON.stringify(x,null,2);
 info(x.comparability==='MATCHED_SYNTHETIC_INVARIANTS'?'Сопоставимость допущений проверена; фактическая экономия не доказана.':'Сценарии несопоставимы',x.comparability!=='MATCHED_SYNTHETIC_INVARIANTS');
}));
el('radial-create-dossier').addEventListener('click',()=>perform(async()=>{
 const x=await api(radialBase()+'/economic-dossiers','POST',{
  asset_id:selected('radial-asset'),benefit_key:el('radial-benefit-key').value,
  baseline_run_id:selected('radial-baseline'),proposed_run_id:selected('radial-alternative'),
  finance:JSON.parse(el('radial-finance').value)});
 el('radial-dossier').textContent=JSON.stringify(x,null,2);
 info('Лабораторное экономическое досье создано. Инвестиционный допуск: НЕТ.');
}));
el('radial-open-dossier').addEventListener('click',()=>perform(async()=>{
 const x=await api(radialBase()+'/economic-dossiers/'+selected('radial-dossier-list'));
 el('radial-dossier').textContent=JSON.stringify(x,null,2);
}));
el('radial-reproduce-dossier').addEventListener('click',()=>perform(async()=>{
 const x=await api(radialBase()+'/economic-dossiers/'+selected('radial-dossier-list')+'/reproduce','POST',{});
 el('radial-dossier').textContent=JSON.stringify(x,null,2);
 info(x.reproduced?'Физический и финансовый расчёты воспроизведены по сохранённой версии.':'Воспроизведение не подтверждено.',!x.reproduced);
}));
loadRadialSamples();


// V7.4 immutable interdisciplinary research programme, WBS and heat economics.
let researchProgrammes=[];
const programmeBase=()=>'/v74/orgs/'+encodeURIComponent(org);
function multiChoices(id,items,label){
 const node=el(id);const prior=new Set([...node.selectedOptions].map(x=>x.value));
 node.replaceChildren();for(const item of items){const option=document.createElement('option');
   option.value=item.id;option.textContent=label(item);option.selected=prior.has(item.id);node.append(option);}
}
function multiSelected(id){return [...el(id).selectedOptions].map(x=>x.value)}
const syntheticCapital={title:'Synthetic WBS / research only',currency:'RUB',tax_basis:'EXCL_VAT_SYNTHETIC',
 annual_caps_rub:{'2027':'2200000'},contingency_percent:'0',
 lines:[{code:'01.01',title:'Synthetic engineering survey',category:'survey',year:2027,quantity:'1',
 unit:'package',unit_price_rub:'1800000',price_source_ref:'SYNTHETIC-COST-PACKAGE-2027',predecessors:[]}]};
el('programme-capital').value=JSON.stringify(syntheticCapital,null,2);
async function refreshProgrammes(){
 if(!org)return;
 const requested=org;
 const records=await api(programmeBase()+'/programmes');
 if(org!==requested)return;
 researchProgrammes=records;
 multiChoices('programme-study-ids',studyRuns,x=>x.module+' · '+x.scenario_group+' · '+x.id.slice(0,8));
 multiChoices('programme-finance-ids',radialDossiers,x=>x.benefit_key+' · '+x.id.slice(0,8));
 choices('programme-list',researchProgrammes,x=>x.reference_code+' · '+x.id.slice(0,8));
}
el('programme-links-generate').addEventListener('click',()=>{
 const selected=new Set(multiSelected('programme-study-ids'));
 const rows=studyRuns.filter(x=>selected.has(x.id));
 const relations=[['hydroforecast','cascade','forecast_context_for_cascade'],
   ['cascade','hydrocapex','cascade_context_for_capex'],
   ['turbine','hydrocapex','diagnostics_context_for_capex'],
   ['gridloss','hydrocapex','grid_context_for_capex'],
   ['heatnet','hydrocapex','heat_context_for_capex']];
 const edges=[];for(const [a,b,relationship] of relations){
  const left=rows.find(x=>x.module===a);const right=rows.find(x=>x.module===b && x.scenario_group===left?.scenario_group);
  if(left&&right)edges.push({from_study_id:left.id,to_study_id:right.id,relationship});
 }
 el('programme-links').value=JSON.stringify(edges,null,2);
 info('Построено '+edges.length+' семантических связей. Значения между моделями автоматически не передаются.');
});
el('programme-budget-sample').addEventListener('click',()=>{
 el('programme-capital').value=JSON.stringify(syntheticCapital,null,2);
 info('Смета — искусственный пример, не стоимость строительных работ на реальных объектах.');
});
el('programme-budget-check').addEventListener('click',()=>perform(async()=>{
 const x=await api(programmeBase()+'/capital-screen','POST',JSON.parse(el('programme-capital').value));
 el('programme-budget-result').textContent=JSON.stringify(x,null,2);
 info('Сверка WBS завершена: '+x.status+'. Реальные цены и объёмы не подтверждены.');
}));
el('programme-heat-example').addEventListener('click',()=>{
 const selected=new Set(multiSelected('programme-study-ids'));
 const options=studyRuns.filter(x=>x.module==='heatnet'&&selected.has(x.id));
 if(options.length<2){info('Выберите два сохранённых тепловых расчёта с одинаковым сценарием.',true);return;}
 el('programme-heat').value=JSON.stringify([{baseline_study_id:options[0].id,
   proposed_study_id:options[1].id,benefit_key:'synthetic_heat_'+options[0].id.slice(0,8),
   finance:{scope:'SYNTHETIC_HEAT_NOT_TARIFF',hours_per_year:'5000',
   value_rub_per_kwh:{low:'2',base:'3',high:'5'},capital_cost_rub:'1000000',
   annual_opex_delta_rub:'100000',discount_rate:'0.12',years:8,
   notes:'Synthetic placeholders; no real heat tariff or engineering validation.'}}],null,2);
 info('Пример теплосетевого сценария подготовлен. Проверьте идентичность базовых условий.');
});
el('programme-create').addEventListener('click',()=>perform(async()=>{
 const x=await api(programmeBase()+'/programmes','POST',{
  reference_code:el('programme-ref').value,title:el('programme-title').value,
  purpose:el('programme-purpose').value,study_ids:multiSelected('programme-study-ids'),
  financial_dossier_ids:multiSelected('programme-finance-ids'),
  links:JSON.parse(el('programme-links').value),heat_screenings:JSON.parse(el('programme-heat').value),
  capital:JSON.parse(el('programme-capital').value),
  scope:'SYNTHETIC_MAGADAN_RESEARCH_ONLY'
 });
 el('programme-output').textContent=JSON.stringify(x,null,2);
 info('Исследовательское досье создано: '+x.id+'. Промышленное утверждение запрещено.');
}));
el('programme-open').addEventListener('click',()=>perform(async()=>{
 const x=await api(programmeBase()+'/programmes/'+selected('programme-list'));
 el('programme-output').textContent=JSON.stringify(x,null,2);
}));
el('programme-reproduce').addEventListener('click',()=>perform(async()=>{
 const x=await api(programmeBase()+'/programmes/'+selected('programme-list')+'/reproduce','POST',{});
 el('programme-output').textContent=JSON.stringify(x,null,2);
 info(x.reproduced?'Связи, версии и расчёты воспроизведены. Полевой допуск отсутствует.':'Ошибка воспроизведения.',!x.reproduced);
}));

// V7.5 explicit research handoffs: never authorize operations or investment spending.
let researchHandoffs=[];
const handoffBase=()=>'/v75/orgs/'+encodeURIComponent(org);
const bridgeExamples={
 forecast_to_cascade:{scenario:'point',step_hours:24,travel_lag_steps:0,
   arrival_history_cms:[],hydrological_mapping_ref:'SYNTHETIC-HYDRO-MAPPING-V75'},
 turbine_to_maintenance:{planning_reference:'SYNTHETIC-MAGADAN-MAINTENANCE-V75',
  options:[{option_id:'inspection',action:'inspection',materials_rub:'10000',labor_rub:'25000',
     north_logistics_rub:'15000',outage_hours:'2',downtime_value_rub_per_hour:'3000',lead_time_days:7,
     basis_ref:'SYNTHETIC-INSPECTION-BASIS-V75'},
    {option_id:'repair',action:'repair',materials_rub:'130000',labor_rub:'40000',
     north_logistics_rub:'60000',outage_hours:'14',downtime_value_rub_per_hour:'3000',lead_time_days:45,
     basis_ref:'SYNTHETIC-REPAIR-BASIS-V75'}]}
};
function refreshBridgeSelectors(){
 const mode=selected('handoff-type');const leftModule=mode==='forecast_to_cascade'?'hydroforecast':'turbine';
 choices('handoff-left',studyRuns.filter(x=>x.module===leftModule),x=>x.scenario_group+' · '+x.id.slice(0,8));
 const right=el('handoff-right');right.disabled=mode!=='forecast_to_cascade';
 choices('handoff-right',studyRuns.filter(x=>x.module==='cascade'),x=>x.scenario_group+' · '+x.id.slice(0,8));
}
function handoffExample(){el('handoff-settings').value=JSON.stringify(bridgeExamples[selected('handoff-type')],null,2)}
async function refreshHandoffs(){
 if(!org)return;
 const requestOrg=org;
 const rows=await api(handoffBase()+'/handoffs');
 if(org!==requestOrg)return;
 researchHandoffs=rows;
 refreshBridgeSelectors();
 choices('handoff-list',rows,x=>x.kind+' · '+x.id.slice(0,8));
 const p=el('handoff-programme');const prior=p.value;p.replaceChildren();
 const none=document.createElement('option');none.value='';none.textContent='Без программы';p.append(none);
 for(const x of researchProgrammes){const op=document.createElement('option');op.value=x.id;op.textContent=x.reference_code;p.append(op)}
 if([...p.options].some(x=>x.value===prior))p.value=prior;
}
el('handoff-type').addEventListener('change',()=>{refreshBridgeSelectors();handoffExample()});
el('handoff-example').addEventListener('click',()=>{handoffExample();info('Подставлены только синтетические предпосылки.');});
el('handoff-create').addEventListener('click',()=>perform(async()=>{
 const kind=selected('handoff-type'),settings=JSON.parse(el('handoff-settings').value);
 const body={kind,left_study_id:selected('handoff-left'),scope:'SYNTHETIC_LAB_ONLY'};
 if(selected('handoff-programme'))body.programme_id=selected('handoff-programme');
 if(kind==='forecast_to_cascade'){
  body.right_study_id=selected('handoff-right');body.forecast_bridge=settings;
 }else{body.maintenance_bridge=settings;}
 const result=await api(handoffBase()+'/handoffs','POST',body);
 el('handoff-result').textContent=JSON.stringify(result,null,2);
 info('Исследовательская связь создана: '+result.id+'; промышленное утверждение запрещено.');
}));
el('handoff-open').addEventListener('click',()=>perform(async()=>{
 const result=await api(handoffBase()+'/handoffs/'+selected('handoff-list'));
 el('handoff-result').textContent=JSON.stringify(result,null,2);
}));
el('handoff-reproduce').addEventListener('click',()=>perform(async()=>{
 const result=await api(handoffBase()+'/handoffs/'+selected('handoff-list')+'/reproduce','POST',{});
 el('handoff-result').textContent=JSON.stringify(result,null,2);
 info('Лабораторная модель воспроизведена: '+result.reproduced+'. Независимой экспертизы нет.');
}));
el('handoff-programme-open').addEventListener('click',()=>perform(async()=>{
 const pid=selected('handoff-programme');if(!pid)throw Error('Выберите программу');
 const result=await api(handoffBase()+'/programmes/'+pid+'/handoffs');
 el('handoff-assurance').textContent=JSON.stringify(result,null,2);
}));
el('handoff-programme-reproduce').addEventListener('click',()=>perform(async()=>{
 const pid=selected('handoff-programme');if(!pid)throw Error('Выберите программу');
 const result=await api(handoffBase()+'/programmes/'+pid+'/reproduce-handoffs','POST',{});
 el('handoff-assurance').textContent=JSON.stringify(result,null,2);
 info('Исследовательские связи воспроизведены: '+result.attached_handoffs_recomputed+'. Проверка родительских моделей выполняется отдельно в разделе 08.');
}));
handoffExample();


// V7.6: one immutable research assurance dossier per benefit key; NEVER an investment authorization.
let assurancePacks=[];
const assuranceBase=()=>'/v76/orgs/'+encodeURIComponent(org);
const assuranceRoutingExample={time_constant_hours:12,initial_routed_outflow_cms:30,
  mapping_ref:'SYNTHETIC-MAGADAN-UNVALIDATED-ROUTING-V76'};
const assuranceFinanceExample={scope:'SYNTHETIC_INCREMENTAL_CASHFLOWS_ONLY',
  benefit_key:'synthetic_research_value_v76',source_assumption_ref:'SYNTHETIC-NOT-A-REAL-ENERGY-TARIFF-V76',
  discounted_from_year:2027,discount_rate:'0.12',benefit_scenarios:{low:'0.5',base:'1',high:'1.5'},
  annual_gross_value_rub:{'2028':'200000','2029':'350000','2030':'500000','2031':'500000'},
  annual_incremental_opex_rub:{'2028':'20000','2029':'30000','2030':'30000','2031':'30000'},
  rationale:'This is a synthetic example for financial model QA, not real Magadan tariff, avoided cost, or investment economics.'};
function sampleAssurance(){
 el('assurance-routing').value=JSON.stringify(assuranceRoutingExample,null,2);
 el('assurance-finance').value=JSON.stringify(assuranceFinanceExample,null,2);
}
function updateAssuranceSelectors(){
 choices('assurance-programme',researchProgrammes,x=>x.reference_code+' · '+x.id.slice(0,8));
 const pid=selected('assurance-programme');
 const rows=researchHandoffs.filter(x=>x.programme_id===pid);
 multiChoices('assurance-handoffs',rows,x=>x.kind+' · '+x.id.slice(0,8));
 const choose=el('assurance-routing-handoff'),before=choose.value;choose.replaceChildren();
 const blank=document.createElement('option');blank.value='';blank.textContent='Без дополнительной модели';choose.append(blank);
 for(const item of rows.filter(x=>x.kind==='forecast_to_cascade')){
   const option=document.createElement('option');option.value=item.id;option.textContent=item.id.slice(0,12);choose.append(option);
 }
 if([...choose.options].some(x=>x.value===before))choose.value=before;
}
async function refreshAssurancePacks(){
 if(!org)return;
 const requestOrg=org;
 const rows=await api(assuranceBase()+'/assurance-packs');
 if(org!==requestOrg)return;
 assurancePacks=rows;
 updateAssuranceSelectors();
 choices('assurance-list',rows,x=>x.reference_code+' · '+x.id.slice(0,8));
}
el('assurance-programme').addEventListener('change',updateAssuranceSelectors);
el('assurance-sample').addEventListener('click',()=>{
 sampleAssurance();info('Подставлены только синтетические финансовые и гидрологические предпосылки.');
});
el('assurance-create').addEventListener('click',()=>perform(async()=>{
 const handoffIds=multiSelected('assurance-handoffs'),routed=selected('assurance-routing-handoff');
 if(!selected('assurance-programme'))throw Error('Выберите программу с сохранённым WBS');
 if(!handoffIds.length)throw Error('Выберите хотя бы одну исследовательскую связь');
 const payload={reference_code:el('assurance-ref').value,
  programme_id:selected('assurance-programme'),handoff_ids:handoffIds,
  routing_handoff_id:routed||null,routing:routed?JSON.parse(el('assurance-routing').value):null,
  finance:JSON.parse(el('assurance-finance').value),
  scope:'SYNTHETIC_DECISION_EVIDENCE_NOT_APPROVAL'};
 const result=await api(assuranceBase()+'/assurance-packs','POST',payload);
 el('assurance-output').textContent=JSON.stringify(result,null,2);
 info('Создано синтетическое досье '+result.id+'. Ни один инвестиционный допуск не выдан.');
}));
el('assurance-open').addEventListener('click',()=>perform(async()=>{
 const result=await api(assuranceBase()+'/assurance-packs/'+selected('assurance-list'));
 el('assurance-output').textContent=JSON.stringify(result,null,2);
}));
el('assurance-reproduce').addEventListener('click',()=>perform(async()=>{
 const result=await api(assuranceBase()+'/assurance-packs/'+selected('assurance-list')+'/reproduce','POST',{});
 el('assurance-output').textContent=JSON.stringify(result,null,2);
 info('Воспроизведено: '+result.reproduced+'. Не является независимой полевой экспертизой.',!result.reproduced);
}));
sampleAssurance();

// V7.7: external reference values are UNTRUSTED until independent expert attestation.
function refreshV77Selectors(){
  choices('reference-study',radialRuns,x=>x.scenario_group+' · '+x.id.slice(0,8));
  choices('reference-assurance',assurancePacks,x=>x.reference_code+' · '+x.id.slice(0,8));
}
const referenceBase=()=>'/v77/orgs/'+encodeURIComponent(org);
el('reference-export').addEventListener('click',()=>perform(async()=>{
 const id=selected('reference-study');if(!id)throw Error('Сначала сохраните сетевой расчёт в разделе 07');
 const out=await api(referenceBase()+'/grid-reference/request/'+encodeURIComponent(id));
 el('reference-request').value=JSON.stringify(out,null,2);
 info('Экспортирован синтетический запрос. Расчёт независимым инструментом ещё не выполнен.');
}));
el('reference-import').addEventListener('click',()=>perform(async()=>{
 const id=selected('reference-study');if(!id)throw Error('Выберите сетевой расчёт');
 const payload={study_id:id,submission:JSON.parse(el('reference-submission').value)};
 const out=await api(referenceBase()+'/grid-reference/comparisons','POST',payload);
 el('reference-comparison-id').value=out.comparison_id;
 el('reference-result').textContent=JSON.stringify(out,null,2);
 info('Сравнение сохранено. Совпадение показателей не является подтверждением внешнего источника.');
}));
el('reference-reproduce').addEventListener('click',()=>perform(async()=>{
 const id=el('reference-comparison-id').value;if(!id)throw Error('Сначала сохраните сравнение');
 const out=await api(referenceBase()+'/grid-reference/comparisons/'+encodeURIComponent(id)+'/reproduce','POST',{});
 el('reference-result').textContent=JSON.stringify(out,null,2);
 info('Результаты воспроизведены. Подлинность стороннего расчёта по-прежнему не подтверждена.');
}));
el('reference-sensitivity').addEventListener('click',()=>perform(async()=>{
 const id=selected('reference-assurance');if(!id)throw Error('Создайте WBS-досье в разделе 10');
 const out=await api(referenceBase()+'/assurance-packs/'+encodeURIComponent(id)+'/sensitivity');
 el('reference-finance-output').textContent=JSON.stringify(out,null,2);
 info('Выполнен расчёт чувствительности; вероятности сценария не оцениваются.');
}));


// V7.8: annual research economics are derived from PINNED physical feeder windows
// and an exclusive programme WBS. This UI provides NO approvals or real-tariff claims.
const annualBase78=()=>'/v78/orgs/'+encodeURIComponent(org);
let annualDossiers78=[];
async function refreshV78(){
  if(!org)return;
  const current=org;
  const items=await api(annualBase78()+'/grid-annual-dossiers');
  if(org!==current)return;
  annualDossiers78=items;
  choices('v78-programme',researchProgrammes,x=>x.reference_code+' · '+x.id.slice(0,8));
  choices('v78-baseline',radialRuns,x=>x.scenario_group+' · '+x.id.slice(0,8));
  choices('v78-proposed',radialRuns,x=>x.scenario_group+' · '+x.id.slice(0,8));
  choices('v78-history',annualDossiers78,x=>x.benefit_key+' · '+x.id.slice(0,8));
}
const exampleCash78={
 scope:'SYNTHETIC_SINGLE_INTERVENTION_NO_TARIFF',
 benefit_key:'SYNTHETIC_MAGADAN_GRID_ANNUAL_V78',discount_anchor_year:2026,
 nominal_discount_rate:'0.12',discount_source_ref:'SYNTHETIC-NOMINAL-DISCOUNT-V78',
 first_full_service_year:2030,
 price_scenario_factors:{low:'0.7',base:'1.0',high:'1.3'},
 annual_assumptions:[
  {year:2030,cycles:50,avoided_supply_cost_rub_per_kwh:{normal:'3',winter_peak:'8'},
   retained_physical_savings_fraction:'1',additional_opex_rub:'100000',
   cost_assumption_ref:'SYNTHETIC-AVOIDED-COST-2030'},
  {year:2031,cycles:50,avoided_supply_cost_rub_per_kwh:{normal:'4',winter_peak:'9'},
   retained_physical_savings_fraction:'0.95',additional_opex_rub:'120000',
   cost_assumption_ref:'SYNTHETIC-AVOIDED-COST-2031'}],
 economic_rationale:'Synthetic radial feeder with the same loads and topology across both variants. Assumed window-specific avoided cost by year is not a tariff, approved price or actual reduction in corporate expense.',
 basis:'NOMINAL_RUB_WITH_NOMINAL_DISCOUNT_NO_VAT_OR_TAX'
};
el('v78-finance').value=JSON.stringify(exampleCash78,null,2);
el('v78-sample').addEventListener('click',()=>{
 el('v78-finance').value=JSON.stringify(exampleCash78,null,2);
 info('Загружены условные стоимости, а не тарифы. Для запуска создайте отдельную программу WBS с survey/equipment/commissioning за 2027–2029 гг.');
});
function showV78(x){
 const r=x.report;
 if(!r){el('v78-output').textContent=JSON.stringify(x,null,2);return;}
 const npv=Object.entries(r.scenario_results).map(([name,v])=>`${name}: ${v.npv_rub} ₽`).join(' | ');
 el('v78-output').textContent='NPV: '+npv+'\nПокрытие неполных лет: '+r.partial_coverage_years.join(', ')+
 '\nWBS: '+r.wbs_total_capex_rub+' ₽ | '+r.wbs_status+'\nНИКАКОГО РАЗРЕШЕНИЯ НА ИНВЕСТИЦИИ\n\n'+JSON.stringify(r,null,2);
}
el('v78-create').addEventListener('click',()=>perform(async()=>{
 const programme_id=selected('v78-programme'),baseline_run_id=selected('v78-baseline'),proposed_run_id=selected('v78-proposed');
 if(!programme_id||!baseline_run_id||!proposed_run_id)throw Error('Нужны программа WBS и два сетевых расчёта');
 const result=await api(annualBase78()+'/grid-annual-dossiers','POST',
  {programme_id,baseline_run_id,proposed_run_id,parameters:JSON.parse(el('v78-finance').value)});
 showV78(result);info('Исследовательский годовой расчёт записан: '+result.id+'. Промышленное применение запрещено.');
}));
el('v78-open').addEventListener('click',()=>perform(async()=>{
 const id=selected('v78-history');if(!id)throw Error('Выберите досье');
 showV78(await api(annualBase78()+'/grid-annual-dossiers/'+encodeURIComponent(id)));
}));
el('v78-reproduce').addEventListener('click',()=>perform(async()=>{
 const id=selected('v78-history');if(!id)throw Error('Выберите досье');
 const out=await api(annualBase78()+'/grid-annual-dossiers/'+encodeURIComponent(id)+'/reproduce','POST',{});
 el('v78-output').textContent=JSON.stringify(out,null,2);
 info('Пересчёт лаборатории: '+out.reproduced+'. Независимая инженерная экспертиза не проводилась.');
}));


// V7.9: two strictly LAB-only views. No actual savings can be recognized.
const v79Root=()=>'/v79/orgs/'+encodeURIComponent(org);
let benefitReservations79=[],measurementScreens79=[];
function updateBenefitSources79(){
  const kind=selected('v79-source-kind');
  const possible=kind==='GRID_ANNUAL_V78'?annualDossiers78:
    kind==='MAINTENANCE_HANDOFF_V75'?researchHandoffs.filter(x=>x.kind==='turbine_to_maintenance'):
    kind==='PROGRAMME_V74'?researchProgrammes:assurancePacks;
  choices('v79-source',possible,x=>(x.benefit_key||x.reference_code||x.kind||x.id)+' / '+x.id.slice(0,8));
  const families={GRID_ANNUAL_V78:'ELECTRIC_ENERGY_COST',MAINTENANCE_HANDOFF_V75:'MAINTENANCE_COST',PROGRAMME_V74:'HEAT_ENERGY_COST',ASSURANCE_V76:'DECISION_PROCESS'};
  el('v79-family').value=families[kind];
}
async function refreshV79(){
  if(!org)return;
  choices('v79-boundary',assets,x=>x.name+' / '+x.id);
  updateBenefitSources79();
  const [ledger,screens]=await Promise.all([api(v79Root()+'/benefit-reservations'),api(v79Root()+'/measurement-screens')]);
  benefitReservations79=ledger.reservations;
  measurementScreens79=screens;
  choices('v79-history',benefitReservations79,x=>x.source.family+' / '+x.id.slice(0,8));
  choices('v79-mv-list',measurementScreens79,x=>x.id.slice(0,8)+' / '+x.asset_id);
}
el('v79-source-kind').addEventListener('change',updateBenefitSources79);
el('v79-reserve').addEventListener('click',()=>perform(async()=>{
 const data={asset_id:selected('v79-boundary'),family:selected('v79-family'),
   start_year:Number(selected('v79-from')),end_year:Number(selected('v79-to')),
   source_kind:selected('v79-source-kind'),source_id:selected('v79-source'),
   measurement_plan_ref:el('v79-plan-ref').value,
   measurement_boundary_description:el('v79-boundary-note').value,
   comparison_normalization:el('v79-normalization').value};
 const item=await api(v79Root()+'/benefit-reservations','POST',data);
 el('v79-output').textContent=JSON.stringify(item,null,2);
 info('LAB ownership recorded without recognition of actual savings');
}));
el('v79-open').addEventListener('click',()=>perform(async()=>{
 const id=selected('v79-history');if(!id)throw Error('Choose a reservation');
 el('v79-output').textContent=JSON.stringify(await api(v79Root()+'/benefit-reservations/'+encodeURIComponent(id)),null,2);
}));
el('v79-reproduce').addEventListener('click',()=>perform(async()=>{
 const id=selected('v79-history');if(!id)throw Error('Choose a reservation');
 el('v79-output').textContent=JSON.stringify(await api(v79Root()+'/benefit-reservations/'+encodeURIComponent(id)+'/reproduce','POST',{}),null,2);
}));
function syntheticMvExample79(){
 const base=new Date('2027-01-01T00:00:00.000Z');
 const commission=new Date('2027-03-07T00:00:00.000Z');
 const obs=(after,i)=>{
   const time=new Date((after?commission:base).getTime()+(after?24+i*24:i*24)*3600000);
   const p=after?3.1+(i%6)*0.39:3+(i%7)*0.37;
   const temp=after?-16+(i*7%20):-17+(i*9%22);
   const rate=2.6+0.55*p*p+0.09*temp+(after?-1.1:((i%5)-2)*0.005);
   return {started_at:time.toISOString(),available_at:new Date(time.getTime()+7200000).toISOString(),duration_hours:1,
      mean_delivered_load_mw:p,mean_ambient_temperature_c:temp,metered_loss_kwh:rate,
      source_ref:'SYNTHETIC-OBS-'+(after?'AFTER':'BEFORE')+'-'+i};
 };
 return {asset_id:selected('v79-boundary'),commissioned_at:commission.toISOString(),
   report_as_of:'2027-04-03T00:00:00.000Z',
   baseline:Array.from({length:48},(_,i)=>obs(false,i)),post:Array.from({length:12},(_,i)=>obs(true,i)),
   measurement_boundary_ref:'SYNTHETIC-MV-MAGADAN-V79-BOUNDARY',
   adjustment_description:'Synthetic OLS counterfactual fitted exclusively on pre-commissioning load, load squared and temperature. No field metering or independent causal review.'};
}
el('v79-mv-example').addEventListener('click',()=>{
 el('v79-mv-case').value=JSON.stringify(syntheticMvExample79(),null,2);
 info('Synthetic post-project example. No actual field effect.');
});
el('v79-mv-create').addEventListener('click',()=>perform(async()=>{
 const data=JSON.parse(el('v79-mv-case').value);
 const r=await api(v79Root()+'/measurement-screens','POST',data);
 el('v79-mv-output').textContent=JSON.stringify(r.report,null,2);
 info('Synthetic counterfactual saved, not eligible for cash recognition');
}));
el('v79-mv-open').addEventListener('click',()=>perform(async()=>{
 const id=selected('v79-mv-list');if(!id)throw Error('Choose an M&V screen');
 el('v79-mv-output').textContent=JSON.stringify(await api(v79Root()+'/measurement-screens/'+encodeURIComponent(id)),null,2);
}));
el('v79-mv-reproduce').addEventListener('click',()=>perform(async()=>{
 const id=selected('v79-mv-list');if(!id)throw Error('Choose an M&V screen');
 el('v79-mv-output').textContent=JSON.stringify(await api(v79Root()+'/measurement-screens/'+encodeURIComponent(id)+'/reproduce','POST',{}),null,2);
}));


// V8 laboratory metering scope audit and M&V quality; server authority only.
const v8Root=()=>'/v8/orgs/'+encodeURIComponent(org);
async function refreshV8(){
  if(!org)return;
  const data=await api(v8Root()+'/boundary-audit');
  const boundaries=data.boundaries;
  choices('v8-boundary-asset',assets,x=>x.name+' / '+x.id);
  for(const id of ['v8-boundary-map','v8-overlap-a','v8-overlap-b']){
    choices(id,boundaries,x=>x.id+' / '+x.quantity_class);
  }
  const parent=el('v8-parent'),prior=parent.value;
  parent.replaceChildren();const blank=document.createElement('option');blank.value='';blank.textContent='Нет родительской границы';parent.append(blank);
  for(const b of boundaries){const op=document.createElement('option');op.value=b.id;op.textContent=b.id;parent.append(op)}
  parent.value=boundaries.some(b=>b.id===prior)?prior:'';
  const isAdmin=who?.organizations?.some(m=>m.org_id===org&&m.role==='admin');
  for(const id of ['v8-boundary-create','v8-boundary-assign','v8-overlap-create']){
    el(id).disabled=!isAdmin || data.claim_graph_frozen;
  }
  el('v8-boundary-output').textContent=JSON.stringify(data,null,2);
}
for(const id of ['v8-boundary-create','v8-boundary-assign','v8-overlap-create']){
  el(id).addEventListener('click',()=>perform(async()=>{
    const ev=el('v8-evidence').value;
    const request=id==='v8-boundary-create'
      ?{route:'/meter-boundaries',data:{id:el('v8-boundary-id').value,parent_id:selected('v8-parent')||null,
        quantity_class:selected('v8-quantity'),source_ref:ev}}
      :id==='v8-boundary-assign'
        ?{route:'/boundary-asset-assignments',data:{asset_id:selected('v8-boundary-asset'),
          boundary_id:selected('v8-boundary-map'),evidence_ref:ev}}
        :{route:'/boundary-overlaps',data:{boundary_a:selected('v8-overlap-a'),
          boundary_b:selected('v8-overlap-b'),evidence_ref:ev}};
    const result=await api(v8Root()+request.route,'POST',request.data);
    el('v8-boundary-output').textContent=JSON.stringify(result,null,2);
    info('Лабораторная граница сохранена; полевой статус не присваивается');
  }));
}
el('v8-boundary-refresh').addEventListener('click',()=>perform(async()=>{await refreshV8();
  info('Реестр физических границ и старых досье сверён без признания экономии')}));
el('v8-mv-quality').addEventListener('click',()=>perform(async()=>{
  const id=selected('v79-mv-list');if(!id)throw Error('Выберите сохранённое исследование до/после');
  const res=await api(v8Root()+'/measurement-screens/'+encodeURIComponent(id)+'/quality');
  el('v79-mv-output').textContent=JSON.stringify(res,null,2);
  info('Качество и совместная область условий рассчитаны; это не подтверждение экономии');
}));


// V8.2 synthetic hydrological research. A plotting aid only; no SCADA.
function refreshV82(){
  choices('v82-asset',assets.filter(x=>x.classification==='LAB_REFERENCE'),x=>x.name+' / '+x.id);
}
function syntheticDailyFlowV82(){
  const n=168, horizon=Number(selected('v82-horizon'));
  const shift=Number(selected('v82-regime'));
  const origin=Date.UTC(2026,0,1);
  const daily=86400000;
  const observations=Array.from({length:n},(_,i)=>{
     const t=origin+i*daily;
     const q=160+0.16*i+15*Math.sin(2*Math.PI*i/32)+5*Math.sin(2*Math.PI*i/8)+4*Math.cos(2.1*i)+(i>=n-28?shift:0);
     return {observed_at:new Date(t).toISOString(),
       available_at:new Date(t+6*3600000).toISOString(),mean_flow_cms:Number(Math.max(0,q).toFixed(7)),
       source_ref:'SYNTHETIC-MAGADAN-LAB-DAILY-Q-'+String(i).padStart(4,'0')};
  });
  return {asset_id:selected('v82-asset'),as_of:new Date(origin+(n-1)*daily+10*3600000).toISOString(),
    horizon_days:horizon,miscoverage_alpha:0.1,
    monitor_threshold_cms:Number(el('v82-threshold').value),observations};
}
const v82NS='http://www.w3.org/2000/svg';
function plotForecastV82(rows){
  const host=el('v82-plot');host.replaceChildren();
  if(!rows?.length)return;
  const svg=document.createElementNS(v82NS,'svg');svg.setAttribute('viewBox','0 0 820 260');
  svg.setAttribute('role','img');svg.setAttribute('aria-label','28 прогнозов: факт, точечная оценка и эмпирическая полоса, м³/с');
  const values=rows.flatMap(r=>[r.actual_cms,r.lower_cms,r.upper_cms]);
  const min=Math.max(0,Math.min(...values)-5),max=Math.max(...values)+5;
  const X=i=>48+i*(754/(rows.length-1));
  const Y=v=>218-(v-min)*172/(max-min||1);
  function path(points,color,width,fill='none'){
    const node=document.createElementNS(v82NS,'path');node.setAttribute('d',points);node.setAttribute('stroke',color);
    node.setAttribute('stroke-width',width);node.setAttribute('fill',fill);svg.append(node);
  }
  function title(t,x,y,color){const node=document.createElementNS(v82NS,'text');node.setAttribute('x',x);node.setAttribute('y',y);node.setAttribute('font-size','12');node.setAttribute('fill',color);node.textContent=t;svg.append(node)}
  for(let i=0;i<4;i++){
    const v=min+i*(max-min)/3, y=Y(v);
    path(`M48 ${y} H802`,'#e2eaee',1);title(v.toFixed(1),5,y+4,'#587481');
  }
  const poly=rows.map((r,i)=>`${X(i)},${Y(r.upper_cms)}`).concat(rows.slice().reverse().map((r,i)=>`${X(rows.length-1-i)},${Y(r.lower_cms)}`)).join(' L');
  path('M'+poly+' Z','none',0,'#d5e9e1');
  path('M'+rows.map((r,i)=>`${X(i)},${Y(r.point_cms)}`).join(' L'),'#c47d44',2.4);
  path('M'+rows.map((r,i)=>`${X(i)},${Y(r.actual_cms)}`).join(' L'),'#0e4659',2.4);
  title('Факт',520,22,'#0e4659');title('Прогноз',578,22,'#c47d44');title('Полоса ошибок',660,22,'#41846b');
  title('Дни независимой проверки →',576,249,'#617986');
  host.append(svg);
}
el('v82-sample').addEventListener('click',()=>{
  if(!selected('v82-asset')){info('Сначала войдите и выберите синтетический объект',true);return}
  el('v82-case').value=JSON.stringify(syntheticDailyFlowV82(),null,2);
  info('Учебные 168 суток созданы; это не архив гидропостов Магаданской области.');
});
el('v82-run').addEventListener('click',()=>perform(async()=>{
  const input=JSON.parse(el('v82-case').value);
  const resp=await api('/v82/orgs/'+encodeURIComponent(org)+'/hydroforecast/evaluate','POST',input);
  const r=resp.report,stats=r.holdout,output=el('v82-output');
  el('v82-mae').textContent=stats.mae_cms.toFixed(2);
  el('v82-rmse').textContent=stats.rmse_cms.toFixed(2);
  el('v82-coverage').textContent=(100*stats.interval_empirical_coverage_fraction).toFixed(1)+' %';
  el('v82-point').textContent=r.forecast.point_cms.toFixed(2);
  plotForecastV82(r.holdout_rows);
  el('v82-assessment').textContent='Модель: '+r.selected_model+' · Исторический период: '+stats.count+' суток · Эмпирический радиус: '+r.calibration.absolute_error_radius_cms.toFixed(2)+' м³/с · Ограничения: '+r.risk_flags.join(', ');
  output.textContent=JSON.stringify({split:r.split,model_selection_mae_cms:r.model_selection_mae_cms,
    calibration:r.calibration,holdout:r.holdout,persistence_holdout:r.persistence_holdout,
    forecast:r.forecast,proof:resp.proof},null,2);
  info('Исследовательский прогноз рассчитан и проверен на независимом историческом периоде; промышленное применение запрещено.');
}));


// V8.3: strict lab-only coupling: one predicted UTC day, two distinct assets.
function refreshV83(){
  const lab=assets.filter(a=>a.classification==='LAB_REFERENCE');
  const preferredUpper=lab.find(a=>a.id==='synthetic-cascade-upper')?.id;
  choices('v83-upper',lab,x=>x.name+' / '+x.id,preferredUpper);
  const lowerPool=lab.filter(a=>a.id!==selected('v83-upper'));
  const preferredLower=lowerPool.find(a=>a.id==='synthetic-cascade-lower')?.id
    ||lowerPool.find(a=>a.id==='synthetic-cascade-upper')?.id
    ||lowerPool[0]?.id;
  choices('v83-lower',lab.filter(a=>a.id!==selected('v83-upper')),x=>x.name+' / '+x.id,preferredLower);
}
el('v83-upper').addEventListener('change',refreshV83);
function syntheticCascadeV83(){
  const upperAsset=selected('v83-upper'),lowerAsset=selected('v83-lower');
  if(!upperAsset||!lowerAsset||upperAsset===lowerAsset)
    throw Error('Нужны два разных LAB_REFERENCE объекта в одной организации');
  let forecast;
  if(el('v82-case').value.trim()) forecast=JSON.parse(el('v82-case').value);
  else forecast=syntheticDailyFlowV82();
  forecast.asset_id=upperAsset;
  forecast.horizon_days=2; // one FULL day begins after the 10:00 UTC issue.
  const common=(asset_id,name,start,min,max,elevationLow,elevationHigh,tailLow,tailHigh,limitQ,turbineQ,spillQ,ratedMW)=>({
    asset_id,name,source_ref:'SYNTHETIC-CASCADE-V83-CURVES-EXAMPLE-2026',
    start_volume_m3:start,min_volume_m3:min,max_volume_m3:max,
    storage_curve:[{volume_m3:min,upstream_elevation_m:elevationLow},
                   {volume_m3:start,upstream_elevation_m:(elevationLow+elevationHigh)/2},
                   {volume_m3:max,upstream_elevation_m:elevationHigh}],
    tailwater_curve:[{discharge_cms:0,elevation_m:tailLow},
                     {discharge_cms:250,elevation_m:(tailLow+tailHigh)/2},
                     {discharge_cms:500,elevation_m:tailHigh}],
    efficiency_curve:[{turbine_flow_fraction:0,efficiency:0},
                      {turbine_flow_fraction:.5,efficiency:.9},
                      {turbine_flow_fraction:1,efficiency:.93}],
    turbine_capacity_cms:limitQ,turbine_release_cms:turbineQ,spill_release_cms:spillQ,
    other_losses_cms:0,minimum_release_cms:20,
    previous_release_cms:turbineQ+spillQ,max_daily_ramp_cms:80,
    hydraulic_head_loss_m:1,rated_capacity_mw:ratedMW});
  const delay=Number(selected('v83-delay'));
  return {forecast,daily_observation_semantics:'UTC_DAILY_MEAN_PERIOD_END_AT_OBSERVED_AT',
    target_start_state_and_prior_release_basis:'SYNTHETIC_CONDITIONAL_FUTURE_ASSUMPTIONS_NOT_KNOWN_AT_FORECAST_ISSUE',
    initial_storage_state_ref:'SYNTHETIC-CASCADE-TARGET-DAY-START-STORAGE-2026',
    upper:common(upperAsset,'SYNTHETIC-UPPER-STATION',1e9,9e8,1.1e9,380,410,300,310,250,125,25,120),
    lower:common(lowerAsset,'SYNTHETIC-LOWER-STATION',5e8,4e8,6e8,300,330,220,232,200,145,30,150),
    route:{delay_hours:delay,previous_daily_releases_cms:Array(Math.ceil(delay/24)).fill(150),
      source_ref:'SYNTHETIC-DAILY-RELEASE-ROUTING-2026'},
    hydrological_mapping_ref:'SYNTHETIC-UPSTREAM-FLOW-TO-RESERVOIR-2026',
    lower_local_inflow_cms:45,lower_local_inflow_ref:'SYNTHETIC-DOWNSTREAM-LOCAL-INFLOW-2026',
    water_density_kg_m3:1000};
}
el('v83-sample').addEventListener('click',()=>{
  try{
    el('v83-case').value=JSON.stringify(syntheticCascadeV83(),null,2);
    info('Создан учебный связанный сценарий: расход, две кривые объёма, задержка, КПД, три варианта');
  }catch(e){info(e.message,true)}
});
el('v83-run').addEventListener('click',()=>perform(async()=>{
  const body=JSON.parse(el('v83-case').value);
  const response=await api('/v83/orgs/'+encodeURIComponent(org)+'/cascade/forecast-screen','POST',body);
  const r=response.report;
  for(const [id,name] of [['v83-dry','dry'],['v83-central','central'],['v83-wet','wet']]){
    const item=r.scenarios.find(x=>x.name===name);
    el(id).textContent=item.upper_forecast_inflow_cms.toFixed(2);
  }
  el('v83-balance').textContent=r.scenarios.every(x=>Math.abs(x.global_mass_balance_residual_m3)<1e-3)?'Баланс сведён':'Проверить';
  const peakWarning=r.scenarios.some(s=>s.violations.some(v=>v.includes('ELECTRICAL_RATED_CAPACITY_EXCEEDED')));
  el('v83-assessment').textContent='Класс: '+r.qualification+
    (peakWarning?' · ПРЕВЫШЕН синтетический предел мгновенной мощности: энергия не признаётся':' · Пиковая мощность проверена на обеих границах суток')+
    ' · Сценарии с нарушениями: '+r.scenarios.filter(s=>!s.feasible_under_synthetic_constraints).length+
    ' · Важные статистические замечания: '+r.calibration_and_stationarity_risk_flags.join(', ')+
    ' · Финансовый эффект: НЕ ПРИЗНАН';
  el('v83-output').textContent=JSON.stringify({target_start:r.target_day_start_utc,
      target_end:r.target_day_end_utc,lead_to_start_hours:r.forecast_actual_lead_to_target_day_start_hours,
      scenario_energy_span_mwh:r.scenario_energy_span_mwh,
      risk:r.hydrology_report,scenarios:r.scenarios,limitations:r.limitations,proof:response.proof},null,2);
  info('Проверен лабораторный баланс по двум водохранилищам; никакого решения о режиме или экономии не принято.');
}));
