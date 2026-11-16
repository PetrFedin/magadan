"""Static layout only. Does NOT prove logged-in browser-to-API E2E."""
from pathlib import Path
import json,re
from playwright.sync_api import sync_playwright
root=Path(__file__).parents[1]
markup=(root/'server/ui/index.html').read_text().replace('<script type="module" src="/lab-assets/ui.js"></script>','')
css=(root/'server/ui/ui.css').read_text()
client=(root/'server/ui/ui.js').read_text()
ids=set(re.findall(r'\bid=["\']([^"\']+)',markup))
js_refs=set(re.findall(r'el\(["\']([^"\']+)',client))
missing=sorted(js_refs-ids)
if missing:raise SystemExit('UNKNOWN_DOM_IDS: '+str(missing))
metrics=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
    for width in (1440,768,375):
        page=browser.new_page(viewport={'width':width,'height':1000},device_scale_factor=1)
        page.set_content(markup,wait_until='domcontentloaded')
        page.add_style_tag(content=css)
        page.evaluate("""() => {document.querySelector('#lab').hidden=false;document.querySelector('#auth-card').hidden=true;document.querySelector('#session').hidden=false;}""")
        page.locator('#annual-grid-workspace').scroll_into_view_if_needed()
        result=page.evaluate("""() => ({viewport:innerWidth,body:document.body.scrollWidth,
             block:document.getElementById('annual-grid-workspace').scrollWidth,
             blockClient:document.getElementById('annual-grid-workspace').clientWidth,
             fields:document.querySelectorAll('#annual-grid-workspace input,#annual-grid-workspace select,#annual-grid-workspace textarea').length})""")
        path=root/'artifacts_v78'/f'v78-grid-economics-{width}.png'
        page.locator('#annual-grid-workspace').screenshot(path=str(path))
        metrics.append(result)
        page.close()
    browser.close()
(root/'artifacts_v78'/'layout_metrics.json').write_text(json.dumps({'metrics':metrics,'dom_ids':len(ids),'unknown_js_ids':missing,'authenticated_e2e':False},indent=2))
print(json.dumps(metrics))
if any(x['body']>x['viewport']+1 for x in metrics):raise SystemExit('STATIC_HORIZONTAL_OVERFLOW')
