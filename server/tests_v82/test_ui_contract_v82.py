"""V8.2 UI contract checks: static only, not browser E2E acceptance."""
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'server/ui/index.html').read_text(encoding='utf-8')
JS=(ROOT/'server/ui/ui.js').read_text(encoding='utf-8')
CSS=(ROOT/'server/ui/ui.css').read_text(encoding='utf-8')


def test_forecast_workspace_wired_to_authenticated_server_endpoint():
    expected={'v82-asset','v82-horizon','v82-regime','v82-threshold',
              'v82-sample','v82-run','v82-case','v82-output','v82-assessment',
              'v82-plot','v82-mae','v82-rmse','v82-coverage','v82-point'}
    ids=re.findall(r'id="([a-zA-Z0-9_-]+)"',HTML)
    assert len(ids)==len(set(ids))
    assert expected.issubset(set(ids))
    assert "api('/v82/orgs/'+encodeURIComponent(org)+'/hydroforecast/evaluate','POST',input)" in JS
    assert "refreshV82();" in JS
    assert "choices('v82-asset',assets.filter(x=>x.classification==='LAB_REFERENCE')" in JS


def test_safe_chart_has_no_remote_dependencies_or_operational_action():
    assert 'createElementNS' in JS
    assert 'textContent' in JS
    assert 'innerHTML=' not in JS
    assert 'SYNTHETIC-' in JS
    assert 'SCADA' in HTML
    assert 'Не' in HTML or 'НЕ' in HTML
    assert 'forecast-v82-kpis' in CSS
    assert "data-src='" not in HTML


def test_javascript_compiles_without_browser():
    r=subprocess.run(['node','--check',str(ROOT/'server/ui/ui.js')],
                     capture_output=True,text=True)
    assert r.returncode==0,r.stderr
