from hydro_api import main

def test_expert_can_reproduce_but_not_claim_field_validation(prepared):
    e=prepared['env'];c=e['client'];h=e['h']
    url='/v71/orgs/magadan-lab/runs/'+prepared['run']+'/reproduce'
    r=c.post(url,headers=h('audit'));assert r.status_code==200,r.text
    assert r.json()['exact_reproduction'] is True
    assert r.json()['independent_specialist_verified'] is False
    assert r.json()['magadan_field_validation'] is False
    assert r.json()['independent_implementation_difference_mw']<1e-8
    assert c.post(url,headers=h('viewer')).status_code==403
    assert c.post('/v71/orgs/separate-org/runs/'+prepared['run']+'/reproduce',headers=h('other')).status_code==404


def test_runtime_change_requires_a_new_review(prepared,monkeypatch):
    e=prepared['env'];changed={**main.execution_provenance(),'scipy':'DIFFERENT_RUNTIME'}
    monkeypatch.setattr(main,'execution_provenance',lambda:changed)
    c=e['client'];h=e['h']
    r=c.post('/v71/orgs/magadan-lab/runs/'+prepared['run']+'/reproduce',headers=h('audit'))
    assert r.status_code==409 and 'PINNED_RUNTIME' in r.text
    r=c.post(prepared['base']+'/runs',headers=h('lead'),json={'asset_id':'feeder-a','evidence_id':prepared['evidence'],'model_id':prepared['model']})
    assert r.status_code==409 and 'REVIEW_NEW_MODEL' in r.text


def test_dossier_cannot_misrepresent_lab_as_field_acceptance(prepared):
    e=prepared['env'];c=e['client'];h=e['h'];base=prepared['base']
    r=c.post(base+'/initiatives',headers=h('lead'),json={'asset_id':'feeder-a','run_id':prepared['run'],
           'title':'Synthetic report only','effect_key':'assurance-only'})
    assert r.status_code==201
    dossier=c.get(base+'/initiatives/'+r.json()['id']+'/dossier',headers=h('viewer')).json()
    assert dossier['assurance']['industrial_acceptance'] is False
    assert dossier['assurance']['external_audit']['externally_sealed'] is False
    assert dossier['assurance']['business_state_is_not_a_seal'] is True
