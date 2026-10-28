"""Static layout QA only, no authenticated HTTP E2E."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
root=Path(__file__).parents[1]
markup=(root/'server/ui/index.html').read_text()
markup=markup.replace('<script type="module" src="/lab-assets/ui.js"></script>','')
css=(root/'server/ui/ui.css').read_text()
metrics=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for width in (1440,768,375):
        page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
        page.set_content(markup,wait_until='domcontentloaded')
        page.add_style_tag(content=css)
        page.evaluate("""() => {document.querySelector('#lab').hidden=false; document.querySelector('#auth-card').hidden=true; document.querySelector('#session').hidden=false;}""")
        block=page.locator('#reference-workspace')
        block.scroll_into_view_if_needed()
        info=page.evaluate("""() => ({viewport:innerWidth,body:document.body.scrollWidth,
          section:document.getElementById('reference-workspace').scrollWidth,
          sectionClient:document.getElementById('reference-workspace').clientWidth})""")
        block.screenshot(path=str(root/f'artifacts_v77/reference-layout-{width}.png'))
        metrics.append(info)
        page.close()
    browser.close()
(root/'artifacts_v77/ui_static_metrics.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics))
if any(r['body']>r['viewport']+1 for r in metrics):raise SystemExit('STATIC_HORIZONTAL_OVERFLOW')
