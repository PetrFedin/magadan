"""Live Chromium smoke test over an actual uvicorn server. Synthetic users and data."""
import json,time,socket,threading
from pathlib import Path
import pytest,uvicorn
from playwright.sync_api import sync_playwright
from playwright._impl._errors import Error as PlaywrightError

def test_real_browser_login_workflow_and_mobile(env):
    with socket.socket() as hold:
        hold.bind(('127.0.0.1',0)); port=hold.getsockname()[1]
        hold.listen(64)
        server=uvicorn.Server(uvicorn.Config(env['app'],host='127.0.0.1',port=port,log_level='error',access_log=False,loop='asyncio',ws='none'))
        t=threading.Thread(target=lambda: server.run(sockets=[hold]),daemon=True)
        t.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.03)
        assert server.started,'uvicorn not started'
        errors=[]
        savedir=Path(__file__).resolve().parents[2]/'artifacts';savedir.mkdir(parents=True,exist_ok=True)
        browser=None
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
                page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                page.on('pageerror',lambda err:errors.append(str(err)))
                try:
                    page.goto(f'http://127.0.0.1:{port}/lab',wait_until='networkidle')
                except PlaywrightError as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' in str(exc):
                        server.should_exit=True
                        pytest.skip('Browser network blocked by administrator in this container; real UI E2E not certified')
                    raise
                assert page.locator('h1').inner_text().startswith('ГИДРОКОНТУР')
                assert page.locator('#lab').is_hidden()
                def login(name):
                    page.locator('input[name="email"]').fill(name+'@lab.invalid')
                    page.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                    page.locator('#login-form button').click()
                    page.locator('#lab').wait_for(state='visible')
                    page.locator('#asset option').first.wait_for()
                def logout():
                    page.locator('#logout').click()
                    page.locator('#auth-card').wait_for(state='visible')
                login('lead')
                assert page.locator('#asset').input_value()=='feeder-a'
                # First synthetic evidence; audit role must review it.
                page.locator('#create-evidence').click()
                page.wait_for_function("document.querySelector('#evidence-list').options.length === 1")
                assert 'pending' in page.locator('#evidence-list').inner_text()
                logout();login('audit')
                page.locator('#accept-evidence').click()
                page.wait_for_function("document.querySelector('#evidence-list').innerText.includes('accepted')")
                logout();login('lead')
                page.locator('#create-model').click()
                page.wait_for_function("document.querySelector('#model-list').options.length === 1")
                logout();login('audit')
                page.locator('#accept-model').click()
                page.wait_for_function("document.querySelector('#model-list').innerText.includes('accepted')")
                page.locator('#verify-audit').click()
                page.wait_for_function("JSON.parse(document.querySelector('#audit-result').textContent).valid === true")
                logout();login('lead')
                page.locator('#calculate').click()
                page.wait_for_function("document.querySelector('#calc-result').textContent.includes('line_loss_p_mw')")
                assert '0.022004055' in page.locator('#calc-result').inner_text()
                page.locator('#create-initiative').click()
                page.wait_for_function("document.querySelector('#initiative-list').options.length === 1")
                page.locator('#transition').click()
                page.wait_for_function("document.querySelector('#initiative-list').innerText.includes('engineering_review')")
                page.screenshot(path=str(savedir/'v7-desktop.png'),full_page=True)
                assert not errors,errors
                ctx=browser.new_context(viewport={'width':375,'height':812},device_scale_factor=1,is_mobile=True,has_touch=True)
                mobile=ctx.new_page()
                mobile.on('pageerror',lambda err:errors.append(str(err)))
                mobile.goto(f'http://127.0.0.1:{port}/lab',wait_until='networkidle')
                mobile.locator('input[name="email"]').fill('viewer@lab.invalid')
                mobile.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                mobile.locator('#login-form button').click()
                mobile.locator('#lab').wait_for(state='visible')
                mobile.wait_for_timeout(100)
                assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                mobile.screenshot(path=str(savedir/'v7-mobile.png'),full_page=True)
                assert not errors,errors
                browser.close()
                (savedir/'browser_result.json').write_text(json.dumps({'browser':'Chromium','desktop':'1440','mobile':'375','login':True,
                    'evidence_review':True,'model_review':True,'physical_solver':True,'initiative_state':True,
                    'audit_verified':True,'horizontal_overflow':False,'console_pageerrors':errors},ensure_ascii=False,indent=2))
        finally:
            server.should_exit=True;t.join(timeout=10)
            assert not t.is_alive(), 'HTTP server did not shut down'
