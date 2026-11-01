#!/usr/bin/env python3
"""Chromium UI + real FastAPI TestClient, in-memory intercepted transport.

This verifies DOM/events/RBAC interaction in a browser. It is NOT independent
HTTP/TCP/browser E2E and is NOT production or native PostgreSQL acceptance.
"""
from pathlib import Path
import json,tempfile,sys
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'server'))
from hydro_api.main import create_app,HASHER
from hydro_api.storage import Organization,User,Membership,Asset

OUT=ROOT/'artifacts_v83';OUT.mkdir(exist_ok=True)
summary={'mode':'CHROMIUM_WITH_IN_PROCESS_ASGI_TESTCLIENT_NETWORK_INTERCEPTION',
  'status':'NOT_EXECUTED','standalone_network_http_e2e':False,
  'real_magadan_assets':False,'postgresql_rls_native':False,'viewports':{}}
with tempfile.TemporaryDirectory(prefix='hk-v83-browser-') as tmp:
    app=create_app(database_url='sqlite:///'+str(Path(tmp)/'synthetic.db'),
        jwt_secret='synthetic-browser-token-test-only-not-real-secret-2026-12345678',
        audit_secret='synthetic-browser-audit-test-only-not-real-secret-2026-12345678')
    with app.state.SessionLocal() as db:
        db.add(Organization(id='browser-lab',name='Synthetic cascade browser laboratory'))
        db.flush()
        user=User(email='engineer-v83@lab.invalid',password_hash=HASHER.hash('V83-Synthetic-Browser-Password!'))
        db.add(user);db.flush()
        db.add(Membership(org_id='browser-lab',user_id=user.id,role='engineer'))
        for aid in ('synthetic-upper','synthetic-lower'):
            db.add(Asset(id=aid,org_id='browser-lab',name=aid,classification='LAB_REFERENCE'))
        db.commit()
    client=TestClient(app,raise_server_exceptions=True)
    def intercept(route):
        request=route.request
        from urllib.parse import urlsplit
        parsed=urlsplit(request.url)
        uri=parsed.path+('?' + parsed.query if parsed.query else '')
        excluded={'host','content-length','accept-encoding','connection'}
        headers={k:v for k,v in request.headers.items() if k.lower() not in excluded}
        response=client.request(request.method,uri,headers=headers,
                content=request.post_data_buffer if request.post_data_buffer else None)
        hdr={k:v for k,v in response.headers.items() if k.lower() in {
            'content-type','content-security-policy','x-content-type-options','cache-control'}}
        route.fulfill(status=response.status_code,headers=hdr,body=response.content)
    try:
        with sync_playwright() as play:
            browser=play.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                args=['--no-sandbox','--disable-dev-shm-usage'])
            for width,height in ((375,810),(768,975),(1440,960)):
                page=browser.new_page(viewport={'width':width,'height':height})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/*',intercept)
                page.goto('http://hydrokontur.invalid/lab',wait_until='domcontentloaded',timeout=18000)
                page.locator('input[name=email]').fill('engineer-v83@lab.invalid')
                page.locator('input[name=password]').fill('V83-Synthetic-Browser-Password!')
                page.get_by_role('button',name='Войти').click()
                page.locator('#cascade-v83-workspace').wait_for(state='visible',timeout=15000)
                page.locator('#v83-sample').click()
                page.wait_for_function("() => document.querySelector('#v83-case').value.includes('storage_curve')",timeout=7000)
                page.locator('#v83-run').click()
                page.wait_for_function("() => document.querySelector('#v83-balance').textContent !== '—'",timeout=17000)
                element=page.locator('#cascade-v83-workspace');element.scroll_into_view_if_needed()
                element.screenshot(path=str(OUT/f'cascade-browser-v83-{width}.png'))
                row={'logged_in':True,'simulated_case_submitted':True,
                  'balance':page.locator('#v83-balance').text_content(),
                  'scope_mentions_synthetic':'SYNTHETIC' in element.inner_text(),
                  'report_has_proof':'input_sha256' in page.locator('#v83-output').text_content(),
                  'document_scroll_width':page.evaluate('document.documentElement.scrollWidth'),
                  'viewport_width':width,'page_errors':errors}
                row['horizontal_overflow']=row['document_scroll_width']>width+1
                summary['viewports'][str(width)]=row
                assert row['balance']=='Баланс сведён',row
                assert row['report_has_proof'],row
                assert not row['horizontal_overflow'],row
                assert not errors,row
                page.close()
            summary['status']='BROWSER_ASGI_INTERCEPTED_TRANSPORT_PASS'
            browser.close()
    except Exception as exc:
        summary['status']='BROWSER_ASGI_INTERCEPTED_TRANSPORT_BLOCKED_OR_FAILED'
        summary['error']=type(exc).__name__+': '+str(exc)[:750]
    finally:
        client.close()
        app.state.engine.dispose()
OUT.joinpath('browser_intercepted_v83.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
if summary['status']!='BROWSER_ASGI_INTERCEPTED_TRANSPORT_PASS':
    raise SystemExit(2)
