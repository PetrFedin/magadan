"""Static layout QA only, no server auth or HTTP E2E."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v73';OUT.mkdir(exist_ok=True)
html=(ROOT/'server/ui/index.html').read_text()
css=(ROOT/'server/ui/ui.css').read_text()
html=html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">','<style>'+css+'</style>')
html=html.replace('<script type="module" src="/lab-assets/ui.js"></script>','')
html=html.replace('<main>', '<div style="background:#ffecc9;color:#693b09;font:700 12px Arial;padding:9px 22px">STATIC LAYOUT QA ONLY — NO AUTHENTICATED SERVER — SYNTHETIC DATA</div><main>')
report={'scope':'STATIC_LAYOUT_ONLY','server_http_e2e_accepted':False,'widths':{}}
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    try:
        for width,height,name in [(1440,900,'desktop'),(768,1024,'tablet'),(375,812,'mobile')]:
            page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html,wait_until='load')
            page.evaluate('''() => {
                document.getElementById('auth-card').hidden=true;
                document.getElementById('session').hidden=false;
                document.getElementById('lab').hidden=false;
                document.getElementById('identity').textContent='Static view (no real login)';
                document.getElementById('role-info').textContent='Engineering research demo only';
                document.getElementById('radial-case').value='{"model_kind":"radial_ac_v73","reference_name":"SYNTHETIC"}';
                document.getElementById('radial-finance').value='{"scope":"SYNTHETIC_NOT_A_TARIFF"}';
                document.getElementById('radial-output').textContent='STATIC PREVIEW — no calculation executed';
             }''')
            radial=page.locator('#radial-workspace').is_visible()
            overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
            cards=page.locator('#radial-workspace .v73-metrics > div').count()
            page.screenshot(path=str(OUT/f'v73-layout-{name}.png'),full_page=True)
            report['widths'][str(width)]={'horizontal_overflow':overflow,'radial_panel_visible':radial,'metric_cards':cards,'page_errors':errors}
            page.close()
            assert radial and cards==3 and not overflow and not errors,report
        report['status']='STATIC_LAYOUT_PASS'
    finally:
        browser.close()
(OUT/'layout_qa_v73.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
