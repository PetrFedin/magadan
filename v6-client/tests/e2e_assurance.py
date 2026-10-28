from playwright.sync_api import sync_playwright
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
html=(root/'dist/standalone.html').read_text(encoding='utf-8')
report={'checks':[], 'console_errors':[], 'page_errors':[], 'mobile':{}}
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    desktop=b.new_page(viewport={'width':1440,'height':1000})
    desktop.on('console',lambda m: report['console_errors'].append(m.text) if m.type=='error' else None)
    desktop.on('pageerror',lambda e: report['page_errors'].append(str(e)))
    desktop.set_content(html)
    desktop.wait_for_selector('[data-nav="assurance"]')
    desktop.locator('[data-nav="assurance"]').click()
    desktop.wait_for_selector('[data-assure="forecast-good"]')
    examples=['forecast-good','forecast-bad','scenario-good','scenario-bad','portfolio-good','portfolio-bad','quality-good','quality-bad']
    for name in examples:
        desktop.locator(f'[data-assure="{name}"]').click()
        result=json.loads(desktop.locator('#assurance-output').inner_text())
        if name.endswith('bad'):
            assert result.get('blocked') or (result.get('result') and result['result'].get('valid') is False),result
        else:
            assert not result.get('blocked'),result
        report['checks'].append({'name':name,'passed':True,'blocked':bool(result.get('blocked'))})
    desktop.screenshot(path=str(root/'artifacts/v6-assurance-desktop.png'),full_page=True)
    mobile=b.new_page(viewport={'width':375,'height':812},is_mobile=True,has_touch=True)
    mobile.set_content(html)
    mobile.wait_for_selector('[data-nav="assurance"]')
    mobile.locator('[data-nav="assurance"]').click()
    mobile.wait_for_selector('[data-assure="forecast-good"]')
    mobile.locator('[data-assure="forecast-good"]').click()
    assert 'mae' in mobile.locator('#assurance-output').inner_text()
    w=mobile.evaluate('({view:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})')
    report['mobile']=w
    assert w['scroll']<=w['view']+2, w
    mobile.screenshot(path=str(root/'artifacts/v6-assurance-mobile.png'),full_page=True)
    assert not report['console_errors'] and not report['page_errors'], report
    b.close()
(root/'artifacts/v6_assurance_qa.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
