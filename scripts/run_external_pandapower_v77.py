#!/usr/bin/env python3
"""OFFLINE OPTIONAL separate pandapower solver for SYNTHETIC exported V7.7 case.

Require pandapower in a distinct engineering environment. Do not substitute
hydrokontur's own solver as purported external verification. Output remains
unattested; engineer sign-off and field calibration are separate requirements.
"""
from __future__ import annotations
import argparse,json,sys,hashlib
from pathlib import Path


def canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--request',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise SystemExit('REFUSE_TO_OVERWRITE_EXISTING_REFERENCE')
    data=json.loads(args.request.read_text())
    if data.get('format')!='hydrokontur-reference-request-v77' or not data.get('not_field_approved'):
        raise SystemExit('INVALID_V77_SYNTHETIC_REQUEST')
    case=data['reference_case']
    if case.get('model_kind')!='radial_ac_v73':raise SystemExit('NO_NONLAB_TOPOLOGY_ALLOWED')
    sha=hashlib.sha256(canonical(case).encode()).hexdigest()
    if sha!=data['case_sha256']:raise SystemExit('CASE_HASH_MISMATCH')
    try:
        import pandapower as pp
    except ImportError:
        raise SystemExit('PANDAPOWER_NOT_INSTALLED: use a separate approved engineering environment; no external result created')
    # Interpret each edge as a balanced three-phase 1 km line. No shunts,
    # transformers, neutral, asymmetry or switching; only matches this narrow lab model.
    lines=[]
    for window in case['windows']:
        net=pp.create_empty_network(sn_mva=100,f_hz=50)
        buses={'SOURCE':pp.create_bus(net,vn_kv=case['source_voltage_kv_ll'],name='SOURCE')}
        pp.create_ext_grid(net,bus=buses['SOURCE'],vm_pu=1.0)
        for node in case['nodes']:
            buses[node['node_id']]=pp.create_bus(net,vn_kv=case['source_voltage_kv_ll'],name=node['node_id'])
        indexes={}
        for node in case['nodes']:
            key=node['node_id']
            indexes[key]=pp.create_line_from_parameters(net,from_bus=buses[node['parent_id']],to_bus=buses[key],
                  length_km=1,r_ohm_per_km=node['r_ohm_per_phase'],x_ohm_per_km=node['x_ohm_per_phase'],
                  c_nf_per_km=0,max_i_ka=node['ampacity_a']/1000,name=key)
            pp.create_load(net,bus=buses[key],p_mw=node['load_p_mw']*window['scale'],
                           q_mvar=node['load_q_mvar']*window['scale'])
        pp.runpp(net,algorithm='nr',init='flat',max_iteration=40,tolerance_mva=1e-10,
                 enforce_q_lims=False,calculate_voltage_angles=True)
        if not net.converged:raise SystemExit('EXTERNAL_SOLVER_DID_NOT_CONVERGE')
        nodes=[]
        for node in case['nodes']:
            key=node['node_id'];li=indexes[key];bi=buses[key]
            nodes.append({'node_id':key,'voltage_pu':float(net.res_bus.at[bi,'vm_pu']),
                          'current_a':float(net.res_line.at[li,'i_ka'])*1000,
                          'line_loss_p_mw':float(net.res_line.at[li,'pl_mw'])})
        lines.append({'window':window['name'],'line_loss_p_mw':sum(n['line_loss_p_mw'] for n in nodes),
                      'nodes':nodes})
    result={'scope':'SYNTHETIC_UNATTESTED_REFERENCE_ONLY','claimed_tool':'pandapower',
       'claimed_tool_version':pp.__version__,
       'calculation_method':'External pandapower NR powerflow: balanced three-phase PQ loads, 1km unshunted lines, one slack',
       'source_reference':'SYNTHETIC-PANDAPOWER-REFERENCE-'+data['study_id'][:20],
       'case_sha256':sha,'windows':lines}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print('External numerical results exported, but engineering authenticity/signoff NOT verified:',args.output)


if __name__=='__main__':main()
