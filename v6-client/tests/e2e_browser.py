from playwright.sync_api import sync_playwright
from pathlib import Path
import time,json,sys
root=Path(__file__).resolve().parents[1]
standalone=(root/'dist'/'standalone.html').read_text('utf-8')
results={'navigation':[], 'workflow':[], 'console_errors':[], 'page_errors':[], 'screenshots':[]}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
  page.on('console',lambda msg: results['console_errors'].append(msg.text) if msg.type=='error' else None)
  page.on('pageerror',lambda err: results['page_errors'].append(str(err)))
  page.set_content(standalone,wait_until='domcontentloaded')
  page.wait_for_selector('.module-card')
  assert page.locator('.module-card').count()==6,'not six modules'
  page.screenshot(path=str(root/'artifacts/overview-desktop.png'),full_page=True)
  results['screenshots'].append('overview-desktop.png')
  for m in ['hydro','cascade','turbine','grid','heat','capex']:
   page.locator(f'[data-nav="{m}"]').click()
   page.wait_for_selector('#calculator')
   page.locator('#calculator button[type="submit"]').click()
   page.wait_for_selector('.result-grid')
   results['navigation'].append(m)
   if m=='grid':
    page.screenshot(path=str(root/'artifacts/grid-desktop.png'),full_page=True)
    results['screenshots'].append('grid-desktop.png')
  page.locator('[data-nav="decisions"]').click()
  page.wait_for_selector('#new-decision')
  page.locator('#new-decision button[type="submit"]').click()
  page.wait_for_selector('.decision-card')
  assert page.locator('.decision-card').count()==1
  seq=[('analyst','submit',None),('engineer','engineering_pass','engineering-review-001'),('finance','financial_pass','finance-proof-001'),('approver','approve','committee-minutes-001'),('operator','start_execution',None),('operator','submit_execution','execution-act-001'),('auditor','verify','independent-post-audit-001')]
  for role,act,note in seq:
   page.locator('#role').select_option(role)
   page.wait_for_selector('.decision-card')
   if note:page.locator('[data-note="DEC-001"]').fill(note)
   page.locator(f'[data-act="{act}"]').click()
   page.wait_for_selector('.decision-card')
   results['workflow'].append(f'{role}:{act}')
  assert page.locator('.status.good').count()==1, 'final not verified'
  page.screenshot(path=str(root/'artifacts/decisions-verified-desktop.png'),full_page=True)
  results['screenshots'].append('decisions-verified-desktop.png')
  page.locator('[data-nav="audit"]').click()
  page.wait_for_selector('.audit-banner.valid')
  assert page.locator('table.data-table tbody tr').count()==8,'expected create + 7 transitions'
  results['audit']='8 append-only hashed events verified'
  page.screenshot(path=str(root/'artifacts/audit-desktop.png'),full_page=True)
  results['screenshots'].append('audit-desktop.png')
  # Invalid input must not produce a valid result
  page.locator('[data-nav="grid"]').click()
  page.locator('input[name="input"]').fill('100')
  page.locator('input[name="output"]').fill('200')
  page.locator('#calculator button[type="submit"]').click()
  assert 'Баланс отрицательный' in page.locator('#calc-result').inner_text()
  results['negative_balance_blocked']=True
  # Mobile 375px overview: no horizontal overflow
  mobile=browser.new_page(viewport={'width':375,'height':812},device_scale_factor=1,is_mobile=True,has_touch=True)
  mobile.on('pageerror',lambda err: results['page_errors'].append('mobile:'+str(err)))
  mobile.set_content(standalone,wait_until='domcontentloaded')
  mobile.wait_for_selector('.module-card')
  mobile.screenshot(path=str(root/'artifacts/overview-mobile.png'),full_page=True)
  results['screenshots'].append('overview-mobile.png')
  dims=mobile.evaluate('({scroll: document.documentElement.scrollWidth, view: document.documentElement.clientWidth})')
  results['mobile_widths']=dims
  assert dims['scroll'] <= dims['view']+2,'horizontal overflow mobile'
  assert not results['console_errors'] and not results['page_errors'],results
  browser.close()
 finally_result=True
except Exception as e:
 results['exception']=str(e)
finally:
 pass # Playwright allowed only local HTML content injection; URL navigation blocked by policy
 (root/'artifacts/browser_qa.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(results,ensure_ascii=False,indent=2))
 if 'exception' in results:sys.exit(1)
