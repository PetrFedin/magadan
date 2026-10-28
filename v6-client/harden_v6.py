from pathlib import Path
p=Path('/mnt/data/hydro_v6/src/assurance.mjs')
s=p.read_text()
s=s.replace("  need(Array.isArray(batch) && batch.length > 0,'Empty measurement batch');", "  need(Array.isArray(batch) && batch.length > 0,'Empty measurement batch');\n  need(['review','validated'].includes(minQuality),'Unknown minQuality policy');")
s=s.replace("  for(const r of batch){\n    const faults=[];", "  for(const r of batch){\n    if(!r || typeof r !== 'object'){errors.push({key:'UNKNOWN',problems:['RECORD_INVALID']});continue;}\n    const faults=[];")
s=s.replace("    if(r.quality==='rejected')faults.push('QUALITY_REJECTED');", "    if(r.quality==='rejected')faults.push('QUALITY_REJECTED');\n    if(r.quality==='review' && minQuality==='validated')faults.push('QUALITY_BELOW_POLICY');")
s=s.replace("  const difference=compareBase(base,alternative);", "  for(const scenario of [base,alternative]){\n    need(scenario.context && typeof scenario.context==='object','Scenario context missing');\n    for(const key of CONTEXT_FIELDS){\n      need(scenario.context[key] !== undefined && scenario.context[key] !== null && scenario.context[key] !== '',`Scenario context missing ${key}`);\n    }\n  }\n  const difference=compareBase(base,alternative);")
s=s.replace("    for(const d of p.dependencies||[])if(!sel.has(d))errors.push({code:'DEPENDENCY_MISSING',project:p.id,dependency:d});", "    for(const d of p.dependencies||[]){\n      if(!byId.has(d))errors.push({code:'DEPENDENCY_UNKNOWN',project:p.id,dependency:d});\n      if(!sel.has(d))errors.push({code:'DEPENDENCY_MISSING',project:p.id,dependency:d});\n    }")
s=s.replace("  for(const [year,amount] of Object.entries(spends)){", "  const colors=new Map();\n  function visit(pid,path=[]){\n    if(colors.get(pid)===2)return;\n    if(colors.get(pid)===1){errors.push({code:'DEPENDENCY_CYCLE',path:[...path,pid]});return;}\n    const node=byId.get(pid);if(!node)return;colors.set(pid,1);\n    for(const child of node.dependencies||[])if(sel.has(child))visit(child,[...path,pid]);\n    colors.set(pid,2);\n  }\n  for(const pid of sel)visit(pid);\n  for(const [year,amount] of Object.entries(spends)){")
p.write_text(s)
q=Path('/mnt/data/hydro_v6/tests/assurance.test.mjs')
s=q.read_text()
s+='''
test('V6 quality policy validated rejects review-only records',()=>{const v=validateMeasurementBatch([{...obs(),quality:'review'}],{orgId:'magadanenergo',assetId:'grid-demo',metricUnits:{energy:'MWh'},asOf:stamp,minQuality:'validated'});assert.ok(v.errors[0].problems.includes('QUALITY_BELOW_POLICY'));});
test('V6 quality invalid object stays in rejected batch',()=>{const v=validateMeasurementBatch([null,obs()],{orgId:'magadanenergo',assetId:'grid-demo',metricUnits:{energy:'MWh'},asOf:stamp});assert.equal(v.rejected,1);});
test('V6 scenario missing baseline key rejected even if both missing',()=>{const a=scenario('BASE'),b=scenario('ALT');delete a.context.baselineSnapshotId;delete b.context.baselineSnapshotId;assert.throws(()=>compareDecisionScenarios(a,b),/context missing/);});
test('V6 portfolio cyclic dependencies are invalid',()=>{const v=checkPortfolio({projects:[project('A',true,['B']),project('B',false,['A'])],selectedIds:['A','B'],annualCapsMln:{2027:12}});assert.ok(v.errors.some(e=>e.code==='DEPENDENCY_CYCLE'));});
test('V6 portfolio unknown referenced dependency blocks',()=>{const v=checkPortfolio({projects:[project('A',true,['MISSING'])],selectedIds:['A'],annualCapsMln:{2027:10}});assert.ok(v.errors.some(e=>e.code==='DEPENDENCY_UNKNOWN'));});
'''
q.write_text(s)
