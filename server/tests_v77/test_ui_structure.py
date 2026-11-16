"""Static UI checks only. They do not establish browser E2E acceptance."""
import re
from pathlib import Path

ROOT=Path(__file__).parents[1]/'ui'

def test_v77_ui_references_and_no_duplicate_ids():
    html=(ROOT/'index.html').read_text()
    js=(ROOT/'ui.js').read_text()
    ids=re.findall(r'\bid="([^"]+)"',html)
    refs=re.findall(r"\bel\(['\"]([^'\"]+)['\"]\)",js)
    assert len(ids)==len(set(ids))
    assert not (set(refs)-set(ids))
    assert all(term in html for term in ('reference-workspace','reference-study','reference-submission',
        'reference-assurance','reference-sensitivity','НЕ ЯВЛЯЕТСЯ НЕЗАВИСИМОЙ ЭКСПЕРТИЗОЙ'))
    assert 'industrial_approval_eligible' not in js or 'industrial_approval_eligible' in html
