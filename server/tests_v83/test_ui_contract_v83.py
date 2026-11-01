"""Structural UI checks. These are NOT independent browser E2E results."""
from pathlib import Path
import re, subprocess

ROOT=Path(__file__).resolve().parents[2]
HTML=(ROOT/'server/ui/index.html').read_text(encoding='utf-8')
JS=(ROOT/'server/ui/ui.js').read_text(encoding='utf-8')


def test_connected_cascade_evidence_widget_present_and_ids_unique():
    expected={'v83-upper','v83-lower','v83-delay','v83-sample','v83-run',
              'v83-case','v83-output','v83-assessment','v83-balance',
              'v83-dry','v83-central','v83-wet'}
    ids=re.findall(r'id="([\w-]+)"',HTML)
    assert len(ids)==len(set(ids))
    assert expected.issubset(set(ids))
    assert 'НЕ ДИСПЕТЧЕРИЗАЦИЯ' in HTML
    assert 'SYNTHETIC' in HTML
    assert 'Финансовый эффект' in JS


def test_ui_uses_authenticated_server_and_two_distinct_assets():
    assert "api('/v83/orgs/'+encodeURIComponent(org)+'/cascade/forecast-screen','POST',body)" in JS
    assert "choices('v83-lower',lab.filter(a=>a.id!==selected('v83-upper'))" in JS
    assert 'refreshV83();' in JS
    assert 'forecast.horizon_days=2' in JS
    assert 'daily_observation_semantics:' in JS
    assert "el('v83-output').textContent" in JS
    assert 'innerHTML=' not in JS


def test_js_syntax_and_no_remote_dependencies():
    result=subprocess.run(['node','--check',str(ROOT/'server/ui/ui.js')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'https://cdn' not in HTML
