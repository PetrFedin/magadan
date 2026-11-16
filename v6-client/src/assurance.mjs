/**
 * Hydrokontur 360 V6 lab assurance algorithms.
 * Domain guardrails only: no control of real energy infrastructure, no
 * authenticated users, no production certificate, no authoritative data.
 */
const EPS = 1e-9;
function need(p, reason) { if (!p) throw new Error(reason); }
function finite(n, name, min = -Infinity) {
  need(typeof n === 'number' && Number.isFinite(n) && n >= min, `Invalid ${name}`);
  return n;
}
function id(v, label) { need(typeof v === 'string' && v.trim().length > 0, `Missing ${label}`); return v.trim(); }
function instant(v, label) {
  need(typeof v === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(v), `Invalid ISO timestamp ${label}`);
  const x = Date.parse(v);
  need(Number.isFinite(x), `Invalid date ${label}`);
  return x;
}
const average = arr => arr.reduce((s,x)=>s+x,0)/arr.length;
const fixed = (v, digits=6) => Number(v.toFixed(digits));

/** Rows have strict temporal provenance. Actual observations may become available only after targetAt. */
export function verifyForecastBacktest(rows, {asOf, expectedUnit='m3/s'} = {}) {
  need(Array.isArray(rows) && rows.length >= 2, 'At least two forecast records required');
  const cutoff = instant(asOf, 'asOf');
  const errors = [], absolute = [], actuals = [], issues = new Set();
  for (let i=0;i<rows.length;i++) {
    const r = rows[i];
    need(r && typeof r === 'object', `Invalid row ${i}`);
    id(r.forecastId, `forecastId ${i}`);
    need(!issues.has(r.forecastId), `Duplicate forecastId ${r.forecastId}`); issues.add(r.forecastId);
    need(r.unit === expectedUnit, `Wrong unit in row ${i}`);
    const issue = instant(r.issuedAt,'issuedAt');
    const target = instant(r.targetAt,'targetAt');
    const features = instant(r.featuresAvailableAt,'featuresAvailableAt');
    const observed = instant(r.observedAvailableAt,'observedAvailableAt');
    need(features <= issue, `FORECAST_LEAKAGE: future features in ${r.forecastId}`);
    need(issue < target, `Forecast must precede target in ${r.forecastId}`);
    need(observed >= target, `Observation timestamp precedes target in ${r.forecastId}`);
    need(observed <= cutoff, `Observation not yet available in ${r.forecastId}`);
    const y = finite(r.actual,`actual ${i}`,0);
    const p = finite(r.predicted,`predicted ${i}`,0);
    errors.push(p-y); absolute.push(Math.abs(p-y)); actuals.push(y);
  }
  const sq=errors.map(e=>e*e);const denom=actuals.reduce((a,b)=>a+b,0);
  return {
    count: rows.length, unit:expectedUnit, asOf,
    mae:fixed(average(absolute)), rmse:fixed(Math.sqrt(average(sq))),
    bias:fixed(average(errors)), wapePct: denom>EPS?fixed(100*absolute.reduce((a,b)=>a+b,0)/denom):null,
    wapeStatus:denom>EPS?'valid':'undefined_zero_actual',
    leakageCheck:'PASS', industrialValidation:false
  };
}

/** Structural data quality with explicit missing-vs-zero distinction, source and tenancy. */
export function validateMeasurementBatch(batch, {orgId, assetId, metricUnits, asOf, minQuality='review'} = {}) {
  need(Array.isArray(batch) && batch.length > 0,'Empty measurement batch');
  need(['review','validated'].includes(minQuality),'Unknown minQuality policy');
  id(orgId,'orgId');id(assetId,'assetId');need(metricUnits && typeof metricUnits==='object','No metric unit dictionary');
  const cutoff=instant(asOf,'asOf'), keys=new Set(), errors=[];
  const seen=[];
  for(const r of batch){
    if(!r || typeof r !== 'object'){errors.push({key:'UNKNOWN',problems:['RECORD_INVALID']});continue;}
    const faults=[];
    if(r.orgId!==orgId || r.assetId!==assetId)faults.push('TENANT_ASSET_SCOPE');
    if(!r.sourceId || typeof r.sourceId!=='string')faults.push('SOURCE_MISSING');
    if(!Object.prototype.hasOwnProperty.call(metricUnits,r.metricId))faults.push('METRIC_UNKNOWN');
    else if(metricUnits[r.metricId]!==r.unit)faults.push('UNIT_MISMATCH');
    const stamp = typeof r.observedAt==='string'?Date.parse(r.observedAt):NaN;
    if(!Number.isFinite(stamp))faults.push('TIME_INVALID');
    else if(stamp>cutoff)faults.push('FUTURE_OBSERVATION');
    if(!Object.prototype.hasOwnProperty.call(r,'value') || r.value===null)faults.push('MISSING_NOT_ZERO');
    else if(typeof r.value!=='number'||!Number.isFinite(r.value))faults.push('NOT_FINITE');
    if(!['validated','review','rejected'].includes(r.quality))faults.push('QUALITY_UNKNOWN');
    if(r.quality==='rejected')faults.push('QUALITY_REJECTED');
    if(r.quality==='review' && minQuality==='validated')faults.push('QUALITY_BELOW_POLICY');
    const key=[r.orgId,r.assetId,r.sourceId,r.metricId,r.observedAt].join('|');
    if(keys.has(key))faults.push('DUPLICATE');keys.add(key);
    seen.push(key);
    if(faults.length)errors.push({key,problems:faults});
  }
  return {total:batch.length,accepted:batch.length-errors.length,rejected:errors.length,errors,valid:errors.length===0,unitDictionary:metricUnits,qualityPolicy:minQuality};
}

const CONTEXT_FIELDS=['orgId','assetId','baselineSnapshotId','constraintSetId','modelVersion','valuationDate','currency','discountRate'];
function compareBase(a,b){
  const differences=[];
  for(const k of CONTEXT_FIELDS)if(a.context?.[k]!==b.context?.[k])differences.push(k);
  return differences;
}
function scenarioNpv(s){
  finite(s.capexMln,'capexMln',0);need(Array.isArray(s.cashflowsMln)&&s.cashflowsMln.length>=1 && s.cashflowsMln.length<=50,'Invalid cash flow period');
  const rate=finite(s.context.discountRate,'discountRate',0);need(rate<=1,'Discount rate exceeds laboratory limit');
  return -s.capexMln+s.cashflowsMln.reduce((a,c,i)=>a+finite(c,`cash flow period ${i}`)/Math.pow(1+rate,i+1),0);
}
function constraints(s){
  need(Array.isArray(s.constraints)&&s.constraints.length,'No verified constraint list');
  const failed=[];
  for(const c of s.constraints){
    id(c.id,'constraint.id');
    need(c.kind==='hard'||c.kind==='informational','Unknown constraint type');
    need(typeof c.passed==='boolean','Constraint missing verification');
    id(c.evidenceRef,'constraint.evidenceRef');
    if(c.kind==='hard'&&!c.passed)failed.push(c.id);
  }
  return failed;
}
/** Rejects unverified hard constraints and incomparable baselines before monetization. */
export function compareDecisionScenarios(base,alternative){
  need(base&&alternative,'Two scenarios required');
  id(base.scenarioId,'baseline scenario id');id(alternative.scenarioId,'alternative scenario id');
  need(base.scenarioId!==alternative.scenarioId,'Same scenario id');
  for(const scenario of [base,alternative]){
    need(scenario.context && typeof scenario.context==='object','Scenario context missing');
    for(const key of CONTEXT_FIELDS){
      need(scenario.context[key] !== undefined && scenario.context[key] !== null && scenario.context[key] !== '',`Scenario context missing ${key}`);
    }
  }
  const difference=compareBase(base,alternative);
  need(!difference.length,`INCOMPARABLE_BASELINES: ${difference.join(',')}`);
  need(base.cashflowsMln?.length===alternative.cashflowsMln?.length,'Different cash flow horizons');
  const baseFails=constraints(base),altFails=constraints(alternative);
  if(baseFails.length||altFails.length)return {comparable:true,admissible:false,failedConstraints:{baseline:baseFails,alternative:altFails},deltaNpvMln:null};
  const npvBase=scenarioNpv(base),npvAlternative=scenarioNpv(alternative);
  return {comparable:true,admissible:true,npvBaseMln:fixed(npvBase),npvAlternativeMln:fixed(npvAlternative),deltaNpvMln:fixed(npvAlternative-npvBase),result:'SYNTHETIC_SCENARIO_NOT_IMPLEMENTATION_RECOMMENDATION'};
}

/** Portfolio gate: hard obligations, dependencies, resource caps, alternatives. */
export function checkPortfolio({projects, selectedIds, annualCapsMln}) {
  need(Array.isArray(projects)&&Array.isArray(selectedIds),'Projects and selection required');
  need(annualCapsMln&&typeof annualCapsMln==='object','Annual budget caps missing');
  const byId=new Map();for(const p of projects){id(p.id,'project.id');need(!byId.has(p.id),'Duplicate project');byId.set(p.id,p);}
  const sel=new Set(selectedIds);need(sel.size===selectedIds.length,'Duplicate selection');
  const errors=[];const spends={};
  for(const p of projects){if(p.mandatory&&!sel.has(p.id))errors.push({code:'MANDATORY_MISSING',project:p.id});}
  for(const idv of sel){
    const p=byId.get(idv);if(!p){errors.push({code:'PROJECT_UNKNOWN',project:idv});continue;}
    for(const d of p.dependencies||[]){
      if(!byId.has(d))errors.push({code:'DEPENDENCY_UNKNOWN',project:p.id,dependency:d});
      if(!sel.has(d))errors.push({code:'DEPENDENCY_MISSING',project:p.id,dependency:d});
    }
    for(const x of p.exclusions||[])if(sel.has(x))errors.push({code:'MUTUAL_EXCLUSION',project:p.id,with:x});
    for(const [year,cost] of Object.entries(p.cashOutByYearMln||{})){finite(cost,`cost ${p.id} ${year}`,0);spends[year]=(spends[year]||0)+cost;}
  }
  const colors=new Map();
  function visit(pid,path=[]){
    if(colors.get(pid)===2)return;
    if(colors.get(pid)===1){errors.push({code:'DEPENDENCY_CYCLE',path:[...path,pid]});return;}
    const node=byId.get(pid);if(!node)return;colors.set(pid,1);
    for(const child of node.dependencies||[])if(sel.has(child))visit(child,[...path,pid]);
    colors.set(pid,2);
  }
  for(const pid of sel)visit(pid);
  for(const [year,amount] of Object.entries(spends)){
    if(!Object.prototype.hasOwnProperty.call(annualCapsMln,year))errors.push({code:'BUDGET_YEAR_UNDEFINED',year});
    else {finite(annualCapsMln[year],`budget ${year}`,0);if(amount>annualCapsMln[year]+EPS)errors.push({code:'BUDGET_LIMIT',year,amountMln:fixed(amount),limitMln:annualCapsMln[year]});}
  }
  return {valid:errors.length===0,errors,annualSpendMln:Object.fromEntries(Object.entries(spends).map(([k,v])=>[k,fixed(v)])),countSelected:sel.size,industrialValidation:false};
}

/** Reconcile financial benefit by real owner and impact key. No cross-organization merger. */
export function reconcileBenefitsScoped(rows){
  need(Array.isArray(rows),'Array of benefits required');
  const groups=new Map(),flags=[];let sum=0;
  for(const r of rows){
    id(r.orgId,'organization');id(r.benefitKey,'benefitKey');id(r.evidenceRef,'evidenceRef');
    const amount=finite(r.annualBenefitMln,'annualBenefitMln',0);
    if(!['approved','in_execution','verification_pending','verified'].includes(r.status))continue;
    const k=r.orgId+'|'+r.benefitKey;
    if(!groups.has(k))groups.set(k,[]);groups.get(k).push({...r,amount});
  }
  for(const [key,g] of groups){
    const vals=g.map(x=>x.annualBenefitMln);
    if(Math.max(...vals)-Math.min(...vals)>EPS){flags.push({key,type:'AMOUNT_CONFLICT',excludedMln:null});continue;}
    if(g.length>1)flags.push({key,type:'SHARED_EFFECT_COUNTED_ONCE',duplicates:g.length});
    sum+=vals[0];
  }
  return {uniqueAnnualBenefitMln:fixed(sum),groups:groups.size,flags,canApproveAggregate:!flags.some(x=>x.type==='AMOUNT_CONFLICT')};
}
