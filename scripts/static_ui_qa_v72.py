"""Browser layout verification without localhost network access.
No JS API behavior is tested; screenshots are marked static-layout-only.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v72';OUT.mkdir(exist_ok=True)
html=(ROOT/'server/ui/index.html').read_text()
css=(ROOT/'server/ui/ui.css').read_text()
html=html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">','<style>'+css+'</style>')
html=html.replace('<script type="module" src="/lab-assets/ui.js"></script>','')
html=html.replace('<main>', '<div style="background:#ffecc9;color:#6a3d06;font:700 12px Arial;padding:9px 22px">STATIC LAYOUT QA ONLY - NOT CONNECTED - SYNTHETIC LAB</div><main>')
report={'scope':'STATIC_LAYOUT_ONLY','app_http_e2e_pass':False,'widths':{}}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 try:
  for width,height,name in [(1440,900,'desktop'),(768,1024,'tablet'),(375,812,'mobile')]:
   page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.set_content(html,wait_until='load')
   page.evaluate("""() => {
     document.getElementById('auth-card').hidden = true;
     document.getElementById('session').hidden = false;
     document.getElementById('lab').hidden = false;
     document.getElementById('identity').textContent = 'Static mock - no authentication';
     document.getElementById('role-info').textContent = 'Mock only / no server';
     document.getElementById('study-case').value = '{"synthetic":true, "field_data":false}';
     document.getElementById('study-result').textContent = 'NOT EXECUTED. See automated server tests.';
   }""")
   overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
   study=page.locator('#study-workspace').is_visible()
   page.screenshot(path=str(OUT/f'v72-layout-{name}.png'),full_page=True)
   report['widths'][str(width)]={'overflow':overflow,'six_domain_panel_visible':study,'page_errors':errors}
   page.close()
   assert study and not overflow and not errors,report
  report['status']='STATIC_LAYOUT_PASS'
 finally:browser.close()
OUT.joinpath('layout_qa_v72.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
