"""V8 metering scope graph: all writes require tenant admin; never industrial savings."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from .boundary_v8 import NewBoundary, AssignAsset, ExplicitOverlap, boundary_safety_statement
from .storage import (User, MeterBoundaryV8, BoundaryAssetV8, BoundaryConflictV8,
                      BenefitReservationV79, GridEconomicDossier, GridAnnualDossierV78,
                      AssurancePackV76, ResearchProgramme)

READ_ROLES={'engineer','economist','manager','auditor','admin','viewer'}


def install_boundary_routes(app,get_db,current_user,access,asset,record_audit,audit_secret):
    router=APIRouter()

    def existing(db,org):
        return db.scalar(select(func.count()).select_from(BenefitReservationV79)
                         .where(BenefitReservationV79.org_id==org)) or 0

    def add_conflict(db,org,a,b,why):
        for left,right in [(a,b)] if a==b else [(a,b),(b,a)]:
            if db.get(BoundaryConflictV8,{'org_id':org,'left_id':left,'right_id':right}) is None:
                db.add(BoundaryConflictV8(org_id=org,left_id=left,right_id=right,reason=why))
        db.flush()

    def conflict_neighborhood(db,org,boundary):
        return {boundary}|set(db.scalars(select(BoundaryConflictV8.right_id).where(
            BoundaryConflictV8.org_id==org,BoundaryConflictV8.left_id==boundary)).all())

    def checked_boundary(db,org,bid):
        row=db.scalar(select(MeterBoundaryV8).where(MeterBoundaryV8.org_id==org,
                                                       MeterBoundaryV8.id==bid))
        if row is None:raise HTTPException(404,'Synthetic metering boundary unavailable')
        return row

    @router.get('/v8/meta/boundary-readiness')
    def meta():return boundary_safety_statement()

    @router.post('/v8/orgs/{org_id}/meter-boundaries',status_code=201)
    def create_boundary(org_id:str, body:NewBoundary,
                        u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'admin'},u,db)
        if existing(db,org_id):raise HTTPException(409,'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM')
        if body.parent_id:
            parent=checked_boundary(db,org_id,body.parent_id)
            if parent.quantity_class!=body.quantity_class:
                raise HTTPException(409,'BOUNDARY_QUANTITY_MISMATCH')
        try:
            db.add(MeterBoundaryV8(id=body.id,org_id=org_id,parent_id=body.parent_id,
                quantity_class=body.quantity_class,source_ref=body.source_ref,created_by=u.id))
            db.flush()
            add_conflict(db,org_id,body.id,body.id,'IDENTICAL_SCOPE')
            if body.parent_id:
                for peer in conflict_neighborhood(db,org_id,body.parent_id):
                    add_conflict(db,org_id,body.id,peer,'CONTAINMENT_OR_PRIOR_OVERLAP')
            record_audit(db,org_id,u.id,'boundary.lab.created','meter_boundaries_v8',body.id,
                         {'parent':body.parent_id,'quantity':body.quantity_class},audit_secret)
            db.commit()
        except (IntegrityError,OperationalError):
            db.rollback();raise HTTPException(409,'BOUNDARY_CONFLICT_OR_GRAPH_FROZEN') from None
        return {'id':body.id,'quantity_class':body.quantity_class,'parent_id':body.parent_id,
                'approved_for_field':False}

    @router.post('/v8/orgs/{org_id}/boundary-asset-assignments',status_code=201)
    def assign(org_id:str,body:AssignAsset,
               u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'admin'},u,db)
        if existing(db,org_id):raise HTTPException(409,'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM')
        obj=asset(db,org_id,body.asset_id)
        if obj.classification!='LAB_REFERENCE':raise HTTPException(409,'REAL_ASSET_NOT_PERMITTED_IN_LAB_GRAPH')
        checked_boundary(db,org_id,body.boundary_id)
        try:
            db.add(BoundaryAssetV8(org_id=org_id,asset_id=body.asset_id,
                boundary_id=body.boundary_id,evidence_ref=body.evidence_ref,created_by=u.id))
            db.flush()
            record_audit(db,org_id,u.id,'boundary.asset_assigned.lab','boundary_assets_v8',body.asset_id,
                         {'boundary_id':body.boundary_id},audit_secret)
            db.commit()
        except (IntegrityError,OperationalError):
            db.rollback();raise HTTPException(409,'DUPLICATE_ASSET_OR_FROZEN_SCOPE') from None
        return {'asset_id':body.asset_id,'canonical_boundary_id':body.boundary_id,'field_verified':False}

    @router.post('/v8/orgs/{org_id}/boundary-overlaps',status_code=201)
    def overlap(org_id:str,body:ExplicitOverlap,
                u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,{'admin'},u,db)
        if existing(db,org_id):raise HTTPException(409,'BOUNDARY_GRAPH_FROZEN_AFTER_FIRST_CLAIM')
        a=checked_boundary(db,org_id,body.boundary_a)
        b=checked_boundary(db,org_id,body.boundary_b)
        if a.quantity_class!=b.quantity_class:raise HTTPException(409,'CANNOT_OVERLAP_DIFFERENT_PHYSICAL_QUANTITIES')
        try:
            # Conservative transitive propagation; may overblock ambiguous scopes.
            left=conflict_neighborhood(db,org_id,a.id)
            right=conflict_neighborhood(db,org_id,b.id)
            for l in left:
                for r in right:add_conflict(db,org_id,l,r,'EXPLICIT_POTENTIAL_OVERLAP')
            record_audit(db,org_id,u.id,'boundary.potential_overlap.lab','boundary_conflicts_v8',a.id,
                         {'other':b.id,'evidence_ref':body.evidence_ref},audit_secret)
            db.commit()
        except (IntegrityError,OperationalError):
            db.rollback();raise HTTPException(409,'GRAPH_FROZEN_OR_CONFLICT') from None
        return {'boundary_a':a.id,'boundary_b':b.id,'overlap_assumed':True,
                'field_certification':False}

    @router.get('/v8/orgs/{org_id}/boundary-audit')
    def overview(org_id:str,u:User=Depends(current_user),db:Session=Depends(get_db)):
        access(org_id,READ_ROLES,u,db)
        boundaries=db.scalars(select(MeterBoundaryV8).where(MeterBoundaryV8.org_id==org_id)).all()
        assignments=db.scalars(select(BoundaryAssetV8).where(BoundaryAssetV8.org_id==org_id)).all()
        graph_edges=db.scalars(select(BoundaryConflictV8).where(BoundaryConflictV8.org_id==org_id)).all()
        existing_claims=db.scalars(select(BenefitReservationV79).where(
            BenefitReservationV79.org_id==org_id)).all()
        legacy={
           'grid_economic_pre_v78':db.scalar(select(func.count()).select_from(GridEconomicDossier).where(GridEconomicDossier.org_id==org_id)) or 0,
           'annual_grid_v78':db.scalar(select(func.count()).select_from(GridAnnualDossierV78).where(GridAnnualDossierV78.org_id==org_id)) or 0,
           'assurance_v76':db.scalar(select(func.count()).select_from(AssurancePackV76).where(AssurancePackV76.org_id==org_id)) or 0,
        }
        unresolved=max(legacy['grid_economic_pre_v78'],0)+legacy['annual_grid_v78']+legacy['assurance_v76']
        # Legacy record count is intentionally conservative; no automatic deduplication or recognition.
        return {'scope_status':'SYNTHETIC_ONLY_NOT_ATTESTED',
            'boundaries':[{'id':x.id,'parent_id':x.parent_id,'quantity_class':x.quantity_class} for x in boundaries],
            'asset_mapping':[{'asset_id':x.asset_id,'boundary_id':x.boundary_id} for x in assignments],
            'materialized_symmetric_overlap_links':len(graph_edges),
            'lab_reserved_claims':len(existing_claims),'preexisting_dossier_inventory':legacy,
            'unreconciled_legacy_records_upper_bound':unresolved,
            'cannot_publish_consolidated_savings':True,
            'cross_org_boundary_links_unresolved':True,
            'claim_graph_frozen':bool(existing_claims),
            'independent_field_review':False}

    app.include_router(router)
