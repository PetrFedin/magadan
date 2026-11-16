"""V7.9 auditable, tenant-scoped SYNTHETIC benefit reservations.

An overlap is rejected by the storage engine, not by a racy pre-insert SELECT.
No field savings or investment authorization may be inferred.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from .benefit_ledger_v79 import ReserveBenefitV79, base_value_from_v78, readiness_statement
from .storage import (Asset, User, BenefitReservationV79, GridAnnualDossierV78,
                      AssurancePackV76, ResearchHandoff, ResearchProgramme,
                      ResearchProgrammeStudy, StudyRun, GridEconomicDossier)

ALL_ROLES = {'engineer', 'economist', 'manager', 'auditor', 'admin', 'viewer'}


def install_benefit_routes(app, get_db, current_user, access, asset, record_audit,
                           audit_secret, sha, canonical):
    router = APIRouter()

    def verify_source(db: Session, org_id: str, body: ReserveBenefitV79):
        """Explicit lab evidence. No polymorphic source accepted without rules."""
        kind, ident = body.source_kind, body.source_id
        value = None
        if kind == 'GRID_ANNUAL_V78':
            source = db.scalar(select(GridAnnualDossierV78).where(
                GridAnnualDossierV78.id == ident, GridAnnualDossierV78.org_id == org_id))
            if not source:
                raise HTTPException(404, 'Source dossier unavailable')
            if (source.asset_id != body.asset_id or body.family != 'ELECTRIC_ENERGY_COST'
                    or source.report.get('industrial_approval_eligible') is not False
                    or sha(source.report) != source.report_sha256
                    or sha(source.finance_input) != source.input_sha256):
                raise HTTPException(409, 'SOURCE_TYPE_OR_CONTENT_INTEGRITY_REJECTED')
            # The financial report is a model estimate, never measured savings.
            value = base_value_from_v78(source.report, body.start_year, body.end_year)
            if value is None:
                raise HTTPException(409, 'CLAIM_YEARS_NOT_REPRESENTED_BY_SOURCE')
            source_digest = source.report_sha256
        elif kind == 'MAINTENANCE_HANDOFF_V75':
            source = db.scalar(select(ResearchHandoff).where(
                ResearchHandoff.id == ident, ResearchHandoff.org_id == org_id))
            if not source:
                raise HTTPException(404, 'Source handoff unavailable')
            if (source.asset_id != body.asset_id or body.family != 'MAINTENANCE_COST'
                    or source.kind != 'turbine_to_maintenance'
                    or sha(source.snapshot) != source.snapshot_sha256
                    or sha(source.input_payload) != source.input_sha256):
                raise HTTPException(409, 'HANDOFF_NOT_SUITABLE_FOR_BENEFIT_CLAIM')
            # Cross-check the complete research source and its executable engine,
            # not merely the child's self-reported hash.
            from .handoff_api_v75 import HandoffNew, handoff_engine_hash
            from .studies_api import algorithm_hash
            from .studies import compute_study
            from .coupling_v75 import build_maintenance_decision
            try:
                args = HandoffNew.model_validate(source.input_payload['inputs'])
                study = db.scalar(select(StudyRun).where(
                    StudyRun.org_id == org_id, StudyRun.id == source.left_study_id))
                if (study is None or study.asset_id != body.asset_id or study.module != 'turbine'
                    or not study.source_ref.startswith('SYNTHETIC-')
                    or sha({'org_id':study.org_id,'asset_id':study.asset_id,
                            'module':study.module,'source_ref':study.source_ref,
                            'scenario_group':study.scenario_group,'case':study.case_payload}) != study.input_sha256
                    or sha(study.result) != study.result_sha256
                    or study.engine_sha256 != algorithm_hash()
                    or source.engine_sha256 != handoff_engine_hash()
                    or args.left_study_id != study.id or args.programme_id != source.programme_id
                    or source.snapshot.get('pinned_engine_sha256') != source.engine_sha256
                    or source.snapshot.get('industrial_approval_eligible') is not False
                    or sha(compute_study('turbine',study.case_payload)) != study.result_sha256):
                    raise ValueError('SOURCE_PIN_DRIFT')
                recalculated=build_maintenance_decision(study.result['result'],args.maintenance_bridge)
                if (source.snapshot.get('result') != recalculated
                    or source.snapshot.get('result_sha256') != sha(recalculated)):
                    raise ValueError('REPLAY_MISMATCH')
            except (ValueError,KeyError,TypeError) as exc:
                raise HTTPException(409,'HANDOFF_PARENT_OR_MATH_INTEGRITY_FAILURE') from None
            source_digest = source.snapshot_sha256
        elif kind == 'PROGRAMME_V74':
            source = db.scalar(select(ResearchProgramme).where(
                ResearchProgramme.id == ident, ResearchProgramme.org_id == org_id))
            if not source:
                raise HTTPException(404, 'Programme unavailable')
            if (body.family != 'HEAT_ENERGY_COST' or sha(source.snapshot) != source.snapshot_sha256
                    or not source.snapshot.get('heat_screenings')
                    or source.snapshot.get('cannot_be_used_for_field_approval') is not True):
                raise HTTPException(409, 'PROGRAMME_NOT_SUITABLE_FOR_HEAT_CLAIM')
            linked = db.execute(select(StudyRun).join(
                ResearchProgrammeStudy,
                (ResearchProgrammeStudy.study_id == StudyRun.id) &
                (ResearchProgrammeStudy.org_id == StudyRun.org_id))
                .where(ResearchProgrammeStudy.org_id == org_id,
                       ResearchProgrammeStudy.programme_id == source.id,
                       StudyRun.asset_id == body.asset_id,
                       StudyRun.module == 'heatnet')).scalars().all()
            if not linked or any(not r.source_ref.startswith('SYNTHETIC-') for r in linked):
                raise HTTPException(409, 'HEAT_ASSET_NOT_PINNED_TO_PROGRAMME')
            source_digest = source.snapshot_sha256
        elif kind == 'ASSURANCE_V76':
            source = db.scalar(select(AssurancePackV76).where(
                AssurancePackV76.id == ident, AssurancePackV76.org_id == org_id))
            if not source:
                raise HTTPException(404, 'Assurance dossier unavailable')
            if (body.family != 'DECISION_PROCESS' or sha(source.snapshot) != source.snapshot_sha256
                    or source.snapshot.get('industrial_approval_eligible') is not False):
                raise HTTPException(409, 'ASSURANCE_SCOPE_NOT_SUITABLE')
            programme = db.scalar(select(ResearchProgramme).where(
                ResearchProgramme.id == source.programme_id,
                ResearchProgramme.org_id == org_id))
            if not programme or sha(programme.snapshot) != programme.snapshot_sha256:
                raise HTTPException(409, 'PROGRAMME_NOT_PINNED')
            studies = db.execute(select(StudyRun).join(ResearchProgrammeStudy,
                (ResearchProgrammeStudy.study_id == StudyRun.id) &
                (ResearchProgrammeStudy.org_id == StudyRun.org_id))
                .where(ResearchProgrammeStudy.org_id == org_id,
                       ResearchProgrammeStudy.programme_id == programme.id,
                       StudyRun.asset_id == body.asset_id)).scalars().all()
            if not studies:
                raise HTTPException(409, 'ASSURANCE_BOUNDARY_ASSET_NOT_IN_PROGRAMME')
            source_digest = source.snapshot_sha256
        else:
            raise HTTPException(422, 'UNSUPPORTED_SOURCE')
        return source_digest, value

    def view(db, org_id, row):
        if row.org_id != org_id:
            raise HTTPException(404, 'Benefit not found')
        body = ReserveBenefitV79.model_validate({name: getattr(row, name) for name in (
            'asset_id', 'family', 'start_year', 'end_year', 'source_kind', 'source_id',
            'measurement_plan_ref', 'measurement_boundary_description', 'comparison_normalization')})
        digest, value = verify_source(db, org_id, body)
        reservation = {**body.model_dump(mode='json'),
                       'org_id': org_id, 'source_sha256': digest,
                       'lab_estimated_gross_rub': value}
        if (digest != row.source_sha256 or value != row.lab_estimated_gross_rub
                or sha(reservation) != row.reservation_sha256):
            raise HTTPException(409, 'BENEFIT_SOURCE_OR_RESERVATION_INTEGRITY_FAILURE')
        return {'id': row.id, 'source': body.model_dump(mode='json'),
                'lab_estimated_gross_rub': value, 'source_integrity_checked': True,
                'source_independently_attested': False, 'actual_savings_confirmed': False,
                'state': 'LAB_RESERVED_NON_AUTHORITATIVE',
                'industrial_approval_eligible': False, 'reservation_sha256': row.reservation_sha256}

    @router.get('/v79/meta/readiness')
    def meta():
        return readiness_statement()

    @router.post('/v79/orgs/{org_id}/benefit-reservations', status_code=201)
    def reserve(org_id: str, body: ReserveBenefitV79,
                u: User = Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, {'economist'}, u, db)
        a = asset(db, org_id, body.asset_id)
        if a.classification != 'LAB_REFERENCE':
            raise HTTPException(409, 'REAL_ASSETS_NOT_ACCEPTED_FOR_LAB_CLAIMS')
        digest, value = verify_source(db, org_id, body)
        payload = {**body.model_dump(mode='json'), 'org_id': org_id,
                   'source_sha256': digest, 'lab_estimated_gross_rub': value}
        row = BenefitReservationV79(org_id=org_id, asset_id=body.asset_id,
            family=body.family, start_year=body.start_year, end_year=body.end_year,
            source_kind=body.source_kind, source_id=body.source_id,
            source_sha256=digest,
            source_fingerprint=sha({'org_id': org_id, 'kind': body.source_kind,
                                    'source_id': body.source_id, 'source_sha256': digest}),
            measurement_plan_ref=body.measurement_plan_ref,
            measurement_boundary_description=body.measurement_boundary_description,
            comparison_normalization=body.comparison_normalization,
            lab_estimated_gross_rub=value, reservation_sha256=sha(payload), created_by=u.id)
        try:
            db.add(row)
            db.flush()  # SQLite BEFORE INSERT guards overlapping boundary-year claims atomically.
            if db.bind.dialect.name != 'postgresql':
                record_audit(db, org_id, u.id, 'benefit.reserved.lab',
                             'benefit_reservations_v79', row.id,
                             {'source_sha256': digest, 'reservation_sha256': row.reservation_sha256,
                              'source_kind': body.source_kind, 'boundary_asset_id': body.asset_id,
                              'family': body.family, 'period': [body.start_year, body.end_year]}, audit_secret)
            db.commit()
        except (IntegrityError, OperationalError) as exc:
            db.rollback()
            raise HTTPException(409, 'DUPLICATE_OR_OVERLAPPING_BENEFIT_RESERVATION') from None
        return view(db, org_id, row)

    @router.get('/v79/orgs/{org_id}/benefit-reservations')
    def listing(org_id: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, ALL_ROLES, u, db)
        rows = db.scalars(select(BenefitReservationV79).where(
            BenefitReservationV79.org_id == org_id).order_by(
            BenefitReservationV79.created_at, BenefitReservationV79.id).limit(200)).all()
        result = [view(db, org_id, r) for r in rows]
        legacy_count = db.query(GridEconomicDossier).filter(GridEconomicDossier.org_id == org_id).count()
        raw_dcf = db.query(GridAnnualDossierV78).filter(GridAnnualDossierV78.org_id == org_id).count()
        return {'reservations': result, 'count': len(result), 'unregistered_legacy_warning': True,
                'previous_grid_economic_dossiers': legacy_count,
                'total_grid_annual_dossiers': raw_dcf,
                'not_a_statement_of_realized_savings': True,
                'industrial_approval_eligible': False}

    @router.get('/v79/orgs/{org_id}/benefit-reservations/{reservation_id}')
    def get(org_id: str, reservation_id: str,
            u: User = Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, ALL_ROLES, u, db)
        row = db.scalar(select(BenefitReservationV79).where(
            BenefitReservationV79.org_id == org_id,
            BenefitReservationV79.id == reservation_id))
        if row is None:
            raise HTTPException(404, 'Benefit not found')
        return view(db, org_id, row)

    @router.post('/v79/orgs/{org_id}/benefit-reservations/{reservation_id}/reproduce')
    def reproduce(org_id: str, reservation_id: str,
                  u: User = Depends(current_user), db: Session = Depends(get_db)):
        access(org_id, {'auditor'}, u, db)
        row = db.scalar(select(BenefitReservationV79).where(
            BenefitReservationV79.org_id == org_id,
            BenefitReservationV79.id == reservation_id))
        if row is None:
            raise HTTPException(404, 'Benefit not found')
        item = view(db, org_id, row)
        return {**item, 'reproduced': True,
                'independent_expert_assessment': False,
                'source_mathematical_replay': False}

    app.include_router(router)
