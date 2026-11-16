"""STATIC UI layout only. No API calls; does not assert actual browser E2E."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];html=(ROOT/'server/ui/index.html').read_text()
style=(ROOT/'server/ui/ui.css').read_text()
html=html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">','').replace('<script type="module" src="/lab-assets/ui.js"></script>','')
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height,name in [(1440,900,'v7-layout-desktop.png'),(375,812,'v7-layout-mobile.png')]:
  page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
  page.set_content(html)
  page.add_style_tag(content=style)
  page.evaluate('''() => {
   document.querySelector('#auth-card').hidden=true;
   document.querySelector('#session').hidden=false;
   document.querySelector('#lab').hidden=false;
   document.querySelector('#identity').textContent='engineer1@hydrokontur-lab.invalid';
   document.querySelector('#role-info').textContent='magadan-synthetic-lab · engineer (illustrative)';
   const fill=(selector,arr)=>{const s=document.querySelector(selector);s.replaceChildren();arr.forEach(t=>{let op=document.createElement('option');op.textContent=t;s.appendChild(op)})};
   fill('#org',['magadan-synthetic-lab (engineer)']);
   fill('#asset',['Synthetic reference two-bus feeder — 20 kV']);
   fill('#evidence-list',['grid_input — accepted — synthetic']);
   fill('#attached-evidence',['engineering_report — accepted — synthetic']);
   fill('#model-list',['balanced_two_bus_AC_PQ_lab_v1 — accepted']);
   fill('#run-list',['Synthetic reference — 0.022004055 MW loss']);
   fill('#initiative-list',['Feeder study — engineering_review']);
   fill('#next-state',['financial_review']);
   document.querySelector('#payload').value=JSON.stringify({reference_name:'synthetic case',source_voltage_kv_ll:20,load_p_mw:5,load_q_mvar:2,line_r_ohm_per_phase:0.3,line_x_ohm_per_phase:0.4,period_hours:100},null,2);
   document.querySelector('#calc-result').textContent=JSON.stringify({line_loss_p_mw:0.022004055,active_power_balance_residual_mw:0,validation:'internal analytic cross-check',data_classification:'SYNTHETIC_LAB_ONLY'},null,2);
   document.querySelector('#dossier-result').textContent=JSON.stringify({initiative:{title:'Synthetic feasibility',state:'engineering_review',revision:1},source:'lab only; no actual investment approved'},null,2);
   document.querySelector('#audit-result').textContent=JSON.stringify({valid:true,checked:7,property:'HMAC tamper-evident; NOT WORM'},null,2);
  }''')
  page.screenshot(path=str(ROOT/'artifacts'/name),full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),f'Overflow on {width}'
  assert page.locator('#lab').is_visible()
  print(f'{name}: static layout PASS, no overflow width={width}, height={page.evaluate("document.documentElement.scrollHeight")}')
  page.close()
 browser.close()
