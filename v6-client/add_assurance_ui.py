from pathlib import Path
p=Path('/mnt/data/hydro_v6/src/app.mjs')
s=p.read_text()
s="import {verifyForecastBacktest,validateMeasurementBatch,compareDecisionScenarios,checkPortfolio,reconcileBenefitsScoped} from './assurance.mjs';\n"+s
s=s.replace("{id:'audit',name:'Журнал доказательств',symbol:'▤'},{id:'quality'", "{id:'audit',name:'Журнал доказательств',symbol:'▤'},{id:'assurance',name:'V6 Assurance Lab',symbol:'◇'},{id:'quality'")
ui='''
function assurancePanel(){
  return `<div class="intro"><h2>V6 Assurance Lab</h2><p>Executable quality and scenario proof checks on synthetic data only. No operational commands or live engineering models.</p></div>
  <div class="surface"><div class="surface-head"><h3>Evidence-based gates</h3><span>28 added automated tests</span></div>
  <div class="content-grid"><div class="surface" style="padding:18px"><h3>Forecast time-leakage gate</h3><p>Requires all model features to exist by forecast issue time and observed truth by evaluation time.</p><button class="smallbtn" data-assure="forecast-good">Valid history</button> <button class="smallbtn" data-assure="forecast-bad">Deliberate leakage</button></div>
  <div class="surface" style="padding:18px"><h3>Scenario comparability</h3><p>Same asset, evidence snapshot, model, constraint set and valuation date; hard constraints cannot be overridden by benefit.</p><button class="smallbtn" data-assure="scenario-good">Comparable scenarios</button> <button class="smallbtn" data-assure="scenario-bad">Incomparable baselines</button></div>
  <div class="surface" style="padding:18px"><h3>Capital portfolio gates</h3><p>Mandatory investment, dependencies, mutually exclusive alternatives and annual cash budgets.</p><button class="smallbtn" data-assure="portfolio-good">Valid portfolio</button> <button class="smallbtn" data-assure="portfolio-bad">Missing mandatory project</button></div>
  <div class="surface" style="padding:18px"><h3>Measurement quality</h3><p>Separates absent value from valid zero, rejects wrong units, tenant scope and future observations.</p><button class="smallbtn" data-assure="quality-good">Valid measurement</button> <button class="smallbtn" data-assure="quality-bad">Unit mismatch</button></div></div>
  <div class="surface" style="padding:18px;margin-top:16px"><div class="surface-head"><h3>Gate output</h3><span>Validation response JSON</span></div><pre id="assurance-output" style="white-space:pre-wrap;word-break:break-word;max-height:350px;overflow:auto">Choose one proof test. No live plant data is loaded.</pre></div></div>`;
}
function runAssurance(which){
  const row=(forecastId,predicted,actual)=>({forecastId,issuedAt:'2026-10-01T12:00:00Z',featuresAvailableAt:'2026-10-01T11:00:00Z',targetAt:'2026-10-02T12:00:00Z',observedAvailableAt:'2026-10-03T12:00:00Z',unit:'m3/s',predicted,actual});
  const baseCtx={orgId:'kolymaenergo',assetId:'kolyma',baselineSnapshotId:'DATA-01',constraintSetId:'C-01',modelVersion:'study-v0',valuationDate:'2026-10-20',currency:'RUB',discountRate:0.12};
  const sc=(scenarioId,b)=>({scenarioId,context:{...baseCtx},capexMln:10,cashflowsMln:[b,b,b],constraints:[{id:'hard-rule-01',kind:'hard',passed:true,evidenceRef:'synthetic-protocol'}]});
  const project=(id,mandatory)=>({id,mandatory,dependencies:[],exclusions:[],cashOutByYearMln:{2027:3}});
  const measured={orgId:'magadanenergo',assetId:'grid-demo',metricId:'energy',unit:'MWh',sourceId:'synthetic-meter',observedAt:'2026-10-01T10:00:00Z',value:0,quality:'validated'};
  const data={
    'forecast-good':()=>verifyForecastBacktest([row('F1',11,10),row('F2',18,20)],{asOf:'2026-10-20T12:00:00Z'}),
    'forecast-bad':()=>verifyForecastBacktest([{...row('F1',11,10),featuresAvailableAt:'2026-10-02T12:01:00Z'},row('F2',18,20)],{asOf:'2026-10-20T12:00:00Z'}),
    'scenario-good':()=>compareDecisionScenarios(sc('BASE',7),sc('ALT',9)),
    'scenario-bad':()=>compareDecisionScenarios(sc('BASE',7),{...sc('ALT',9),context:{...baseCtx,baselineSnapshotId:'DATA-02'}}),
    'portfolio-good':()=>checkPortfolio({projects:[project('MAND',true),project('OPTION',false)],selectedIds:['MAND','OPTION'],annualCapsMln:{2027:8}}),
    'portfolio-bad':()=>checkPortfolio({projects:[project('MAND',true),project('OPTION',false)],selectedIds:['OPTION'],annualCapsMln:{2027:8}}),
    'quality-good':()=>validateMeasurementBatch([measured],{orgId:'magadanenergo',assetId:'grid-demo',metricUnits:{energy:'MWh'},asOf:'2026-10-20T12:00:00Z'}),
    'quality-bad':()=>validateMeasurementBatch([{...measured,unit:'kWh'}],{orgId:'magadanenergo',assetId:'grid-demo',metricUnits:{energy:'MWh'},asOf:'2026-10-20T12:00:00Z'})
  };
  return data[which]();
}
'''
anchor='async function render(){nav();'
assert anchor in s
s=s.replace(anchor,ui+'\n'+anchor)
s=s.replace("route==='audit'?await auditView():quality()", "route==='audit'?await auditView():route==='assurance'?assurancePanel():quality()")
s=s.replace("if($('#open-decisions'))$('#open-decisions').onclick=()=>go('decisions');", "if($('#open-decisions'))$('#open-decisions').onclick=()=>go('decisions');document.querySelectorAll('[data-assure]').forEach(b=>b.onclick=()=>{try{const value=runAssurance(b.dataset.assure);$('#assurance-output').textContent=JSON.stringify({gate:b.dataset.assure,result:value,scope:'SYNTHETIC_ONLY'},null,2);}catch(e){$('#assurance-output').textContent=JSON.stringify({gate:b.dataset.assure,blocked:true,reason:e.message},null,2);}});")
s=s.replace("['overview','decisions','audit','quality',...MODULES.map(m=>m.id)]", "['overview','decisions','audit','assurance','quality',...MODULES.map(m=>m.id)]")
p.write_text(s)
# bump labels and local storage prefix to ensure the earlier state is never silently treated as V6
s=p.read_text().replace("const key='hydrokontur-v5-lab-state';", "const key='hydrokontur-v6-lab-state';")
p.write_text(s)
p=Path('/mnt/data/hydro_v6/package.json');s=p.read_text().replace('"version":"0.1.0"','"version":"0.2.0"');p.write_text(s)
p=Path('/mnt/data/hydro_v6/README.md');s=p.read_text();s+='\n\n## V6 extension (2026-10-20)\n\n- `src/assurance.mjs`: five read-only validation domains; strict timestamp availability in hydrological forecast backtests; unit and tenancy validations; baseline comparability plus hard constraint gate; portfolio dependencies and annual budget caps; cross-company-safe benefit reconciliation.\n- `tests/assurance.test.mjs`: 29 additional tests on positive and negative cases.\n- `#assurance`: executable Assurance Lab screen, all input synthetic, including deliberately blocked cases.\n- Release remains **LOCAL DEMO / PRODUCTION HOLD**: no authentication, protected server store, solver, field telemetry or authorized corporate connection.\n';p.write_text(s)
