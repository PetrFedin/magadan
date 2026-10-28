"""V8 research diagnostic for synthetic M&V. Diagnostic envelope != confidence interval.

Physical units: metered losses in kWh, observations hours; regression target kW.
No causal attribution, covariance-certified intervals or field status.
"""
from __future__ import annotations
import numpy as np
from scipy.spatial import Delaunay, QhullError
from .measurement_v79 import MVScreenV79, _features, evaluate_mv_screen


def evaluate_quality(case: MVScreenV79) -> dict:
    base = case.baseline
    n = max(24, int(len(base)*0.75))
    # Re-evaluate the original result: temporal and physical guard must succeed first.
    original = evaluate_mv_screen(case)
    train = base[:n]
    held = base[n:]
    X = np.array([_features(r) for r in train], dtype=float)
    y = np.array([r.metered_loss_kwh/r.duration_hours for r in train], dtype=float)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    Xh=np.array([_features(r) for r in held],dtype=float)
    residual = np.array([r.metered_loss_kwh/r.duration_hours for r in held])-Xh@beta
    hp=np.array([r.duration_hours for r in case.post],dtype=float)
    covered=float(np.sum(hp))
    # Marginal support was checked in V7.9. Convex hull measures JOINT support.
    train_xy=np.array([[r.mean_delivered_load_mw,r.mean_ambient_temperature_c] for r in train])
    post_xy=np.array([[r.mean_delivered_load_mw,r.mean_ambient_temperature_c] for r in case.post])
    try:
        hull=Delaunay(train_xy)
        supported=hull.find_simplex(post_xy, tol=1e-9)>=0
        joint_support='MEASURABLE_2D_CONVEX_HULL'
    except QhullError:
        supported=np.zeros(len(post_xy),dtype=bool)
        joint_support='UNDETERMINED_DEGENERATE_COVARIATES'
    omitted=[i for i,yes in enumerate(supported) if not yes]
    bias_kw=float(np.mean(residual))
    p95_abs_kw=float(np.quantile(np.abs(residual),0.95))
    signed=float(original['signed_normalized_difference_kwh'])
    # Conservative deterministic error envelope based on held-out residual quantile.
    # NOT a CI: ignores serial correlation, concept drift, meter error and intervention bias.
    pessimistic_uncertainty=p95_abs_kw*covered
    bias_adjusted=signed-bias_kw*covered
    lag_corr=None
    if len(residual)>2 and np.std(residual[:-1])>1e-12 and np.std(residual[1:])>1e-12:
        lag_corr=float(np.corrcoef(residual[:-1],residual[1:])[0,1])
    reasons=['NO_CAUSAL_ATTRIBUTION','NO_REAL_METER_VERIFICATION','NO_APPROVED_MV_PROTOCOL']
    if omitted:reasons.append('POST_JOINT_COVARIATE_SUPPORT_NOT_DEMONSTRATED')
    if lag_corr is not None and abs(lag_corr)>0.3:
        reasons.append('POTENTIAL_AUTOCORRELATION_IN_HELD_OUT_ERRORS')
    if signed-pessimistic_uncertainty<=0:
        reasons.append('POINT_ESTIMATE_NOT_LARGER_THAN_HOLDOUT_ERROR_ENVELOPE')
    return {
       'status':'RESEARCH_DIAGNOSTIC_NOT_CONFIDENCE_INTERVAL',
       'source_scope':'SYNTHETIC_MV_RESEARCH_NO_REALIZED_SAVINGS',
       'joint_covariate_support':joint_support,
       'post_windows_outside_joint_support':omitted,
       'post_joint_support_fraction':round(float(np.mean(supported)),6),
       'held_out_bias_kw':round(bias_kw,9),
       'held_out_abs_error_p95_kw':round(p95_abs_kw,9),
       'held_out_lag1_residual_correlation':None if lag_corr is None else round(lag_corr,6),
       'observed_signed_difference_kwh':round(signed,6),
       'bias_adjusted_research_difference_kwh':round(bias_adjusted,6),
       'error_envelope_kwh':round(pessimistic_uncertainty,6),
       'indicative_lower_kwh':round(signed-pessimistic_uncertainty,6),
       'indicative_upper_kwh':round(signed+pessimistic_uncertainty,6),
       'envelope_kind':'DESCRIPTIVE_HOLDOUT_95TH_ABSOLUTE_ERROR_TIMES_POST_HOURS_NOT_PROBABILISTIC',
       'limitations':reasons,
       'certified_realized_savings':False,
       'industrial_approval_eligible':False,
       'requires_independent_engineering_signoff':True,
    }
