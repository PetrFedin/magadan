/** ГИДРОКОНТУР 360 • Laboratory reference engine v0.1 (synthetic data ONLY).
 * Not an operational control system, a hydraulic/electrical solver, or a certified engineering model.
 */
export const MODULES = Object.freeze([
  {id:'hydro',name:'HydroForecast',kind:'Гидрологические прогнозы',icon:'≈',color:'#48b2ce'},
  {id:'cascade',name:'CascadeEconomics',kind:'Водно-энергетические сценарии',icon:'⇆',color:'#64a9f5'},
  {id:'turbine',name:'TurbineReliability',kind:'Диагностика оборудования',icon:'◈',color:'#e4b46e'},
  {id:'grid',name:'GridLoss Planner',kind:'Электросети и потери',icon:'⌁',color:'#77bc9e'},
  {id:'heat',name:'HeatNet Economics',kind:'Тепловые сети',icon:'♨',color:'#e8908a'},
  {id:'capex',name:'HydroCAPEX',kind:'Инвестиционные решения',icon:'▧',color:'#aa98d6'}
]);
export const ASSETS=Object.freeze([
  {id:'kolyma',label:'Колымская ГЭС',orgId:'kolymaenergo',modules:['hydro','cascade','turbine','capex'],isRealName:true},
  {id:'ust',label:'Усть-Среднеканская ГЭС',orgId:'kolymaenergo',modules:['hydro','cascade','turbine','capex'],isRealName:true},
  {id:'grid-demo',label:'Учебный сетевой участок М-01',orgId:'magadanenergo',modules:['grid','capex'],isRealName:false},
  {id:'heat-demo',label:'Учебный тепловой участок Т-01',orgId:'magadanenergo',modules:['heat','capex'],isRealName:false}
]);
export const PROPOSED_ROLES=['analyst','engineer','finance','approver','operator','auditor'];
export const FLOW=Object.freeze({
  draft:{submit:{next:'engineering_review',role:'analyst'}},
  engineering_review:{engineering_pass:{next:'financial_review',role:'engineer'},reject:{next:'rejected',role:'engineer'}},
  financial_review:{financial_pass:{next:'approval_pending',role:'finance'},reject:{next:'rejected',role:'finance'}},
  approval_pending:{approve:{next:'approved',role:'approver'},reject:{next:'rejected',role:'approver'}},
  approved:{start_execution:{next:'in_execution',role:'operator'}},
  in_execution:{submit_execution:{next:'verification_pending',role:'operator'}},
  verification_pending:{verify:{next:'verified',role:'auditor'},request_correction:{next:'in_execution',role:'auditor'}},
  verified:{},rejected:{}
});
export const STATUS_LABEL={draft:'Черновик',engineering_review:'Инженерная проверка',financial_review:'Финансовая проверка',approval_pending:'Утверждение',approved:'Утверждено',in_execution:'Исполнение',verification_pending:'Проверка результата',verified:'Результат подтверждён',rejected:'Отклонено'};
export const ACTION_LABEL={submit:'Передать инженеру',engineering_pass:'Подтвердить инженерно',financial_pass:'Подтвердить финансово',approve:'Утвердить',start_execution:'Начать исполнение',submit_execution:'Предъявить результат',verify:'Подтвердить результат',reject:'Отклонить',request_correction:'Вернуть на исправление'};
function number(v,name,{min=-Infinity,max=Infinity}={}){if(typeof v !=='number'||!Number.isFinite(v)||v<min||v>max)throw new Error(`Некорректный параметр «${name}»`);return v;}
function nonempty(v,name){if(typeof v!=='string'||!v.trim())throw new Error(`Поле «${name}» обязательно`);return v.trim();}
const round=(v,n=3)=>Number(v.toFixed(n));
export function npv({capexMln,annualBenefitMln,annualOpexMln=0,discountRate,years}){
  number(capexMln,'CAPEX, млн ₽',{min:0});number(annualBenefitMln,'эффект, млн ₽',{min:0});number(annualOpexMln,'OPEX, млн ₽',{min:0});number(discountRate,'ставка',{min:0,max:1});number(years,'горизонт',{min:1,max:50});if(!Number.isInteger(years))throw new Error('Горизонт должен быть целым числом лет');
  const net=annualBenefitMln-annualOpexMln;
  const factor=discountRate===0?years:(1-Math.pow(1+discountRate,-years))/discountRate;
  return {valueMln:round(-capexMln+net*factor,5),annualNetMln:round(net,5),factor:round(factor,6),classification:net>0?'сценарий с положительным потоком':'сценарий без положительного потока'};
}
export function gridEnergyBalance({inputMwh,outputMwh,ownUseMwh=0,calculatedTechnicalLossMwh}){
  number(inputMwh,'вход, МВт·ч',{min:0});number(outputMwh,'выход, МВт·ч',{min:0});number(ownUseMwh,'собственные нужды, МВт·ч',{min:0});number(calculatedTechnicalLossMwh,'технические потери, МВт·ч',{min:0});
  if(inputMwh===0)throw new Error('Для баланса требуется ненулевой вход');
  const measured=inputMwh-outputMwh-ownUseMwh;
  if(measured < -1e-8)throw new Error('Баланс отрицательный: нужна проверка данных и границ учёта');
  const diff=measured-calculatedTechnicalLossMwh;
  return {measuredLossMwh:round(measured),lossPct:round(measured/inputMwh*100),unexplainedMwh:round(diff),status:diff<0?'Несогласованность измерений и модели':'Обязательна проверка причин необъяснённого остатка',noFraudInference:true};
}
export function hydroBalance({storageM3,inflowM3s,outflowM3s,seconds,minStorageM3,maxStorageM3}){
  number(storageM3,'запас воды',{min:0});number(inflowM3s,'приток',{min:0});number(outflowM3s,'расход',{min:0});number(seconds,'шаг времени',{min:1,max:366*86400});number(minStorageM3,'минимальный запас',{min:0});number(maxStorageM3,'максимальный запас',{min:0});
  if(minStorageM3>maxStorageM3)throw new Error('Несогласованные границы хранения');
  const predicted=storageM3+(inflowM3s-outflowM3s)*seconds;
  return {storageEndM3:round(predicted),valid:predicted>=minStorageM3&&predicted<=maxStorageM3,reason:predicted<minStorageM3?'Ниже нижней учебной границы':predicted>maxStorageM3?'Выше верхней учебной границы':'Внутри учебных ограничений'};
}
export function hydropower({flowM3s,headM,efficiency,ratedMw}){
  number(flowM3s,'расход',{min:0});number(headM,'напор',{min:0});number(efficiency,'КПД',{min:0,max:1});number(ratedMw,'мощность',{min:0});
  const theoretical=1000*9.81*flowM3s*headM*efficiency/1_000_000;
  return {calculatedMw:round(theoretical),overRated:theoretical>ratedMw,warning:theoretical>ratedMw?'Требуется проверка ограничений агрегатов':'Упрощённая формула — не режимный расчёт'};
}
export function heatDuty({massKgSec,temperatureSupplyC,temperatureReturnC,heatCapacityKjKgK=4.186}){
  number(massKgSec,'массовый расход',{min:0});number(temperatureSupplyC,'температура подачи',{min:-50,max:250});number(temperatureReturnC,'температура обратки',{min:-50,max:250});number(heatCapacityKjKgK,'удельная теплоёмкость',{min:0.01,max:10});
  if(temperatureSupplyC<=temperatureReturnC)throw new Error('Температура подачи должна превышать температуру обратки для выбранного режима');
  return {dutyMw:round(massKgSec*heatCapacityKjKgK*(temperatureSupplyC-temperatureReturnC)/1000),warning:'Тепловой баланс, не гидравлическая модель и не модель потерь'};
}
export function conditionAnomaly({value,referenceMean,referenceSd,comparableRegime}){
  number(value,'показание');number(referenceMean,'среднее');number(referenceSd,'стандартное отклонение',{min:0});
  if(!comparableRegime)return {status:'unavailable',message:'Режимы несопоставимы',failureProbability:null};
  if(referenceSd===0)return {status:'unavailable',message:'Недостаточная вариативность эталона',failureProbability:null};
  const z=Math.abs(value-referenceMean)/referenceSd;
  return {status:z>=3?'review':'observation',zScore:round(z),message:z>=3?'Отклонение требует проверки':'В пределах учебного порога',failureProbability:null};
}
export function forecastMAE(forecast,observed){
  if(!Array.isArray(forecast)||!Array.isArray(observed)||forecast.length<2||forecast.length!==observed.length)throw new Error('Нужны одинаковые ряды длиной не менее 2');
  let total=0;for(let i=0;i<forecast.length;i++){number(forecast[i],`прогноз ${i}`);number(observed[i],`факт ${i}`);total+=Math.abs(forecast[i]-observed[i]);}
  return {mae:round(total/forecast.length),samples:forecast.length,warning:'Нет оценки временной утечки: требуется реальная backtesting-процедура'};
}
export function portfolioBenefits(initiatives){
  const grouped=new Map();for(const i of initiatives){if(!['approved','in_execution','verification_pending','verified'].includes(i.status))continue;const key=nonempty(i.benefitKey,'benefitKey');if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(i);}
  let uniqueMln=0;const duplicates=[],conflicts=[];
  for(const [key,items] of grouped){if(items.length===1){uniqueMln+=items[0].annualBenefitMln;continue;} duplicates.push(key);if(items.some(x=>Math.abs(x.annualBenefitMln-items[0].annualBenefitMln)>1e-8)){conflicts.push(key);continue;}uniqueMln+=items[0].annualBenefitMln;}
  return {uniqueAnnualBenefitMln:round(uniqueMln),duplicateKeys:duplicates,conflictingKeys:conflicts,excludedUntilReview:conflicts.length};
}
export const emptyState=()=>({version:1,initiatives:[],events:[]});
export function createInitiative(state,request,actor){
  if(actor.role!=='analyst')throw new Error('Создавать инициативы может аналитик');
  const asset=ASSETS.find(x=>x.id===request.assetId);if(!asset)throw new Error('Объект не найден');
  if(actor.orgId!==asset.orgId)throw new Error('Доступ к другой организации запрещён');
  if(!asset.modules.includes(request.moduleId))throw new Error('Модуль не разрешён для данного объекта');
  nonempty(request.title,'наименование');nonempty(request.evidenceRef,'источник данных');nonempty(request.benefitKey,'код эффекта');
  const financial=npv(request);const id=`DEC-${String(state.initiatives.length+1).padStart(3,'0')}`;
  const entry={id,title:request.title.trim(),assetId:asset.id,orgId:asset.orgId,moduleId:request.moduleId,benefitKey:request.benefitKey,authorId:actor.userId,status:'draft',capexMln:request.capexMln,annualBenefitMln:request.annualBenefitMln,annualOpexMln:request.annualOpexMln,discountRate:request.discountRate,years:request.years,npvMln:financial.valueMln,evidenceRef:request.evidenceRef,approvals:{},executionEvidence:null,outcomeEvidence:null};
  return {...state,initiatives:[...state.initiatives,entry]};
}
export function availableActions(initiative,actor){const transitions=FLOW[initiative.status]||{};return Object.entries(transitions).filter(([action,config])=>config.role===actor.role&&actor.orgId===initiative.orgId&&!( ['engineering_pass','financial_pass','approve','verify'].includes(action)&&initiative.authorId===actor.userId)).map(([action])=>action);}
export function transitionDecision(state,id,action,actor,evidence=''){
  const i=state.initiatives.find(v=>v.id===id);if(!i)throw new Error('Решение не найдено');
  const rule=FLOW[i.status]?.[action];if(!rule)throw new Error(`Переход ${action} запрещён из состояния ${i.status}`);
  if(rule.role!==actor.role||actor.orgId!==i.orgId)throw new Error('Недостаточно прав для перехода');
  if(['engineering_pass','financial_pass','approve','verify'].includes(action)&&actor.userId===i.authorId)throw new Error('Разделение полномочий: автор не подтверждает своё решение');
  if(['engineering_pass','financial_pass','approve','submit_execution','verify','reject','request_correction'].includes(action))nonempty(evidence,'доказательство или обоснование');
  if(action==='verify'&&!i.executionEvidence)throw new Error('Нет подтверждения исполнения');
  const next={...i,status:rule.next,approvals:{...i.approvals}};
  if(['engineering_pass','financial_pass','approve'].includes(action))next.approvals[action]={actor:actor.userId,evidence:evidence.trim()};
  if(action==='submit_execution')next.executionEvidence=evidence.trim();
  if(action==='verify')next.outcomeEvidence={methodAndFacts:evidence.trim(),confirmedBy:actor.userId};
  return {...state,initiatives:state.initiatives.map(v=>v.id===id?next:v)};
}
const enc=new TextEncoder();const bytesToHex=arr=>[...new Uint8Array(arr)].map(x=>x.toString(16).padStart(2,'0')).join('');
// Only for opaque-origin browser previews; NOT cryptographic, NEVER a production authentication substitute.
function weakChecksum(s){let h=2166136261;for(const c of s){h^=c.charCodeAt(0);h=Math.imul(h,16777619);}return 'PREVIEW-NONCRYPTO-'+(h>>>0).toString(16).padStart(8,'0');}
async function hashRecord(base){const payload=JSON.stringify(base);return globalThis.crypto?.subtle?bytesToHex(await globalThis.crypto.subtle.digest('SHA-256',enc.encode(payload))):weakChecksum(payload);}
export async function appendAudit(state,event){
  const prevHash=state.events.length?state.events.at(-1).hash:'GENESIS';
  const base={seq:state.events.length+1,at:event.at||new Date().toISOString(),action:nonempty(event.action,'действие'),actor:nonempty(event.actor,'участник'),objectId:event.objectId||'',note:event.note||'',prevHash};
  const hash=await hashRecord(base);
  return {...state,events:[...state.events,{...base,hash}]};
}
export async function verifyAudit(events){
  let prev='GENESIS';for(let j=0;j<events.length;j++){
    const {hash,...base}=events[j];if(base.prevHash!==prev||base.seq!==j+1)return false;
    const expected=await hashRecord(base);if(hash!==expected)return false;prev=hash;
  }
  return true;
}
