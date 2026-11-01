"""Static Chromium viewport/render check only, NOT authenticated browser E2E."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts_v83'
html=(ROOT/'server/ui/index.html').read_text(encoding='utf-8')
css=(ROOT/'server/ui/ui.css').read_text(encoding='utf-8')
# Do NOT load the production JS or make network requests in static mode.
html=html.replace('<script type="module" src="/lab-assets/ui.js"></script>','')
html=html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">','')
info={'mode':'CHROMIUM_STATIC_SET_CONTENT_NO_AUTH_NO_SERVER','status':'NOT_EXECUTED',
      'browser_e2e_verified':False,'viewports':{}}
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                   args=['--no-sandbox','--disable-dev-shm-usage'])
        for w,h in ((375,820),(768,960),(1440,960)):
            page=browser.new_page(viewport={'width':w,'height':h})
            page.set_content(html,wait_until='domcontentloaded')
            page.add_style_tag(content=css)
            card=page.locator('#cascade-v83-workspace')
            card.scroll_into_view_if_needed()
            card.screenshot(path=str(OUT/f'cascade-static-v83-{w}.png'))
            scroll=page.evaluate('document.documentElement.scrollWidth')
            info['viewports'][str(w)]={
                'viewport_width':w,'document_scroll_width':scroll,
                'horizontal_overflow':scroll>w+1,
                'cascade_section_visible':card.is_visible(),
                'synthetic_disclosure_present':'SYNTHETIC' in card.inner_text(),
                'interactions_tested':False}
            page.close()
        browser.close()
        info['status']='STATIC_LAYOUT_PASS' if all(not r['horizontal_overflow'] and
              r['cascade_section_visible'] for r in info['viewports'].values()) else 'STATIC_LAYOUT_FAILURE'
except Exception as exc:
    info['status']='STATIC_LAYOUT_BLOCKED';info['error']=str(exc)[:650]
(OUT/'static_viewport_v83.json').write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(info,indent=2,ensure_ascii=False))
if info['status']!='STATIC_LAYOUT_PASS':raise SystemExit(2)
