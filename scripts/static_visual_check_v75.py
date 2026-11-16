#!/usr/bin/env python3
"""Offline static CSS check only. Does NOT validate browser <-> API authentication/E2E."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / 'server/ui/index.html').read_text()
css = (ROOT / 'server/ui/ui.css').read_text()
html = html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">', '<style>' + css + '</style>')
html = html.replace('<script type="module" src="/lab-assets/ui.js"></script>', '')
html = html.replace('<div id="lab" hidden>', '<div id="lab">')
html = html.replace('<section class="card" id="auth-card">', '<section class="card" id="auth-card" hidden>')
html = html.replace('<section class="session card" id="session" hidden>', '<section class="session card" id="session" hidden>')
html = html.replace('Для запуска сначала сохраните исходные исследования в разделе 06.', 'SYNTHETIC / LAB ONLY — нет выполненного серверного запроса в данном снимке.')
html = html.replace('Для действительного инженерного подтверждения необходимы независимые специалисты и исходные данные владельца.', 'NATIVE PG: NOT ACCEPTED. FIELD DATA: NOT RECEIVED. NO INDUSTRIAL APPROVAL.')
output = ROOT/'artifacts_v75'
output.mkdir(exist_ok=True)
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    for width in (1440,768,375):
        page = browser.new_page(viewport={'width':width, 'height':900}, device_scale_factor=1)
        page.set_content(html, wait_until='domcontentloaded')
        page.locator('#handoff-workspace').scroll_into_view_if_needed()
        page.wait_for_timeout(120)
        result = page.evaluate('''() => ({document_width:document.documentElement.scrollWidth,viewport_width:window.innerWidth,section_width:document.getElementById('handoff-workspace').getBoundingClientRect().width,labels:[...document.querySelectorAll('#handoff-workspace label')].length})''')
        result.update({'width':width,'horizontal_overflow':max(0,result['document_width']-width),'browser_e2e':False})
        file = output/f'v75-handoff-static-{width}.png'
        page.locator('#handoff-workspace').screenshot(path=str(file), animations='disabled')
        results.append(result)
        page.close()
    browser.close()
(output/'visual_check_v75.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
print(json.dumps(results, ensure_ascii=False))
if any(r['horizontal_overflow'] for r in results):
    raise SystemExit('STATIC_UI_OVERFLOW')
