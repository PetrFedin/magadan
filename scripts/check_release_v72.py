"""Fail-closed certification gates; no user-provided status overrides."""
import argparse,json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
a=json.loads((root/'artifacts_v72/acceptance_summary.json').read_text())
py=(root/'artifacts_v72/python_tests.log').read_text()
node=(root/'artifacts_v72/node_legacy_tests.log').read_text()
conditions={
 'python_test_report':re.search(r'\b' + str(a['server_python_tests']) + r' passed\b',py) is not None and a['server_python_tests']>=119,
 'node_test_report':'# pass 63' in node and a['legacy_node_tests']==63,
 'static_layout':a['static_layout']['status']=='STATIC_LAYOUT_PASS',
 'synthetic_classification':not a['magadan_field_data_present'],
 'postgres_rls_native':a['native_postgres_executed'],
 'corporate_idp':a['corporate_oidc_connected'],
 'external_worm':a['external_compliance_worm_verified'],
 'field_engineering':a['field_engineering_accepted'],
 'browser_network_e2e':a['browser_live_http_e2e']=='PASS',
 'industrial_readiness':a['industrial_production_ready'],
}
p=argparse.ArgumentParser();p.add_argument('--gate',choices=['lab','industrial'],required=True)
args=p.parse_args()
required=['python_test_report','node_test_report','static_layout','synthetic_classification']
if args.gate=='industrial':
 required+=['postgres_rls_native','corporate_idp','external_worm','field_engineering','browser_network_e2e','industrial_readiness']
failed=[name for name in required if not conditions[name]]
print(json.dumps({'gate':args.gate,'passed':not failed,'requirements':{k:conditions[k] for k in required},'missing':failed},indent=2))
if failed:raise SystemExit(2)
