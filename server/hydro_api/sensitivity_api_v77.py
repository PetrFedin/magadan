"""Read-only synthetic financial sensitivity, with source integrity gates."""
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .storage import AssurancePackV76,ResearchProgramme,User
from .assurance_api_v76 import AssuranceNewV76,engine_fingerprint
from .programme_v74 import CapitalScreen
from .sensitivity_v77 import evaluate_sensitivity


def install_sensitivity_routes(app,get_db,current_user,access,sha):
    r=APIRouter()
    @r.get('/v77/orgs/{org_id}/assurance-packs/{pack_id}/sensitivity')
    def sensitivity(org_id:str,pack_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'economist','auditor','manager'},u,db)
        row=db.scalar(select(AssurancePackV76).where(AssurancePackV76.org_id==org_id,AssurancePackV76.id==pack_id))
        if row is None:raise HTTPException(404,'Lab pack unavailable')
        if (sha(row.snapshot)!=row.snapshot_sha256 or sha(row.input_payload)!=row.input_sha256
            or engine_fingerprint()!=row.engine_sha256 or row.snapshot.get('industrial_approval_eligible') is not False):
            raise HTTPException(409,'INVALID_PINNED_ASSURANCE_PACK')
        programme=db.scalar(select(ResearchProgramme).where(ResearchProgramme.org_id==org_id,
            ResearchProgramme.id==row.programme_id))
        if not programme or sha(programme.snapshot)!=programme.snapshot_sha256 or not programme.capital_input:
            raise HTTPException(409,'INVALID_PINNED_WBS_PROGRAMME')
        if row.snapshot.get('programme_sha256')!=programme.snapshot_sha256:
            raise HTTPException(409,'PROGRAMME_VERSION_MISMATCH')
        try:
            body=AssuranceNewV76.model_validate(row.input_payload)
            if (body.programme_id!=programme.id or row.reference_code!=body.reference_code
                or body.finance.benefit_key!=row.benefit_key):
                raise ValueError('FINANCE_RELATIONAL_PIN_MISMATCH')
            values=evaluate_sensitivity(body.finance,CapitalScreen.model_validate(programme.capital_input))
            if values['scenario_npvs_rub']['baseline']!={k:v['npv_rub'] for k,v in row.snapshot['financial']['scenario_results'].items()}:
                raise ValueError('BASELINE_VALUE_MODEL_DIVERGED')
        except (ValueError,KeyError,TypeError) as exc:
            raise HTTPException(409,'SENSITIVITY_SOURCE_OR_MATH_INVALID') from exc
        return {'assurance_pack_id':row.id,'source_pack_sha256':row.snapshot_sha256,'report':values,
                'external_validation_accepted':False,'industrial_approval_eligible':False}
    app.include_router(r)
