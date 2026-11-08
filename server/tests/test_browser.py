"""Live Chromium smoke test over an actual uvicorn server. Synthetic users and data."""
import json,time,socket,threading,os
from pathlib import Path
import pytest,uvicorn
from playwright.sync_api import sync_playwright, expect
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
        savedir=Path(os.environ.get('HYDRO_BROWSER_EVIDENCE_DIR', str(Path(__file__).resolve().parents[2]/'artifacts')))
        savedir.mkdir(parents=True,exist_ok=True)
        browser=None
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get('HYDRO_BROWSER_EXECUTABLE'),args=['--no-proxy-server'])
                page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{port}/lab',wait_until='load')
                assert page.locator('h1').inner_text().startswith('ГИДРОКОНТУР')
                assert page.locator('#lab').is_hidden()
                def login(name):
                    page.locator('input[name="email"]').fill(name+'@lab.invalid')
                    page.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                    page.locator('#login-form button').click()
                    page.locator('#lab').wait_for(state='visible')
                    page.locator('#asset option').first.wait_for(state='attached')
                def logout():
                    page.locator('#logout').click()
                    page.locator('#auth-card').wait_for(state='visible')
                login('lead')
                expect(page.locator('#create-initiative')).to_be_disabled()
                assert page.locator('#asset').input_value()=='feeder-a'
                # First synthetic evidence; audit role must review it.
                page.locator('#create-evidence').click()
                page.locator('#evidence-list option').first.wait_for(state='attached')
                assert 'pending' in page.locator('#evidence-list').inner_text()
                logout();login('audit')
                page.locator('#accept-evidence').click()
                expect(page.locator('#evidence-list')).to_contain_text('accepted')
                logout();login('lead')
                page.locator('#create-model').click()
                page.locator('#model-list option').first.wait_for(state='attached')
                logout();login('audit')
                page.locator('#accept-model').click()
                expect(page.locator('#model-list')).to_contain_text('accepted')
                page.locator('#verify-audit').click()
                expect(page.locator('#audit-result')).to_contain_text('"valid": true')
                logout();login('lead')
                page.locator('#calculate').click()
                expect(page.locator('#calc-result')).to_contain_text('line_loss_p_mw')
                assert '0.022004055' in page.locator('#calc-result').inner_text()
                # The result JSON can arrive before refresh publishes the new run
                # to the tenant-scoped selector. Never click early.
                page.locator('#run-list option').first.wait_for(state='attached')
                expect(page.locator('#create-initiative')).to_be_enabled()
                page.locator('#create-initiative').click()
                page.locator('#initiative-list option').first.wait_for(state='attached')
                page.locator('#transition').click()
                expect(page.locator('#initiative-list')).to_contain_text('engineering_review')
                page.screenshot(path=str(savedir/'v7-desktop.png'),full_page=True)
                assert not errors,errors
                ctx=browser.new_context(viewport={'width':375,'height':812},device_scale_factor=1,is_mobile=True,has_touch=True)
                mobile=ctx.new_page()
                mobile.on('pageerror',lambda err:errors.append(str(err)))
                mobile.goto(f'http://127.0.0.1:{port}/lab',wait_until='load')
                mobile.locator('input[name="email"]').fill('viewer@lab.invalid')
                mobile.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                mobile.locator('#login-form button').click()
                mobile.locator('#lab').wait_for(state='visible')
                mobile.wait_for_timeout(100)
                assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                mobile.screenshot(path=str(savedir/'v7-mobile.png'),full_page=True)
                # Each role receives a separate real Chromium browser context.
                for username, role, tenant in (
                    ('finance', 'economist', 'magadan-lab'),
                    ('manager', 'manager', 'magadan-lab'),
                    ('audit', 'auditor', 'magadan-lab'),
                    ('other', 'engineer', 'separate-org'),
                ):
                    isolated = browser.new_context(viewport={'width': 1440, 'height': 920})
                    role_page = isolated.new_page()
                    role_page.on('pageerror', lambda err: errors.append(str(err)))
                    role_page.goto(f'http://127.0.0.1:{port}/lab', wait_until='load')
                    role_page.locator('input[name="email"]').fill(username + '@lab.invalid')
                    role_page.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                    role_page.locator('#login-form button').click()
                    role_page.locator('#lab').wait_for(state='visible')
                    role_page.locator('#asset option').first.wait_for(state='attached')
                    expect(role_page.locator('#notice')).to_contain_text('Подключено к серверу')
                    expect(role_page.locator('#org')).to_have_value(tenant)
                    expect(role_page.locator('#role-info')).to_contain_text(role)
                    if username == 'other':
                        assert role_page.locator('#org option').count() == 1
                        assert role_page.locator('#org option').first.input_value() == 'separate-org'
                    else:
                        role_page.locator('#fill-sample').click()
                        role_page.locator('#create-evidence').click()
                        expect(role_page.locator('#notice')).to_contain_text('403')
                    role_page.screenshot(path=str(savedir/f'v85-role-{username}.png'), full_page=True)
                    isolated.close()

                # Representative tablet and mobile widths, in independent sessions.
                for width, height in ((390, 844), (768, 1024)):
                    responsive = browser.new_context(
                        viewport={'width': width, 'height': height},
                        device_scale_factor=1,
                        is_mobile=width < 400,
                        has_touch=width < 400)
                    responsive_page = responsive.new_page()
                    responsive_page.on('pageerror', lambda err: errors.append(str(err)))
                    responsive_page.goto(f'http://127.0.0.1:{port}/lab', wait_until='load')
                    responsive_page.locator('input[name="email"]').fill('viewer@lab.invalid')
                    responsive_page.locator('input[name="password"]').fill('Testing-password-Long-2026!')
                    responsive_page.locator('#login-form button').click()
                    responsive_page.locator('#lab').wait_for(state='visible')
                    expect(responsive_page.locator('#org')).to_have_value('magadan-lab')
                    assert responsive_page.evaluate(
                        'document.documentElement.scrollWidth <= window.innerWidth'
                    ), f'horizontal overflow at width={width}'
                    responsive_page.screenshot(path=str(savedir/f'v85-responsive-{width}.png'), full_page=True)
                    responsive.close()
                assert not errors,errors
                browser.close()
                (savedir/'browser_result.json').write_text(json.dumps({'browser':'Chromium','desktop':'1440','mobile':'375','login':True,
                    'evidence_review':True,'model_review':True,'physical_solver':True,'initiative_state':True,
                    'audit_verified':True,'horizontal_overflow':False,'console_pageerrors':errors},ensure_ascii=False,indent=2))
        finally:
            server.should_exit=True;t.join(timeout=10)
            assert not t.is_alive(), 'HTTP server did not shut down'
