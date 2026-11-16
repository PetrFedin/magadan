"""Optional real browser smoke test: local synthetic account, no external network."""
import json, os, socket, tempfile, threading, time
from pathlib import Path
import httpx, uvicorn
from playwright.sync_api import sync_playwright
from hydro_api.main import create_app, HASHER
from hydro_api.storage import Organization, User, Membership, Asset

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v72';OUT.mkdir(exist_ok=True)
secret1='v72-browser-local-jwt-testing-only-key-very-long'
secret2='v72-browser-local-audit-testing-only-secret-long'
status={'status':'NOT_EXECUTED','field_data':'NONE','environment':'localhost synthetic'}
with tempfile.TemporaryDirectory(prefix='hk72-smoke-') as tmp:
    app=create_app(database_url='sqlite:///'+str(Path(tmp)/'lab.db'),jwt_secret=secret1,audit_secret=secret2)
    with app.state.SessionLocal() as db:
        db.add(Organization(id='synthetic-magadan',name='Synthetic Magadan training organization'));db.flush()
        u=User(email='engineer@test.invalid',password_hash=HASHER.hash('SyntheticLabPassword2026!'))
        db.add(u);db.flush();db.add(Membership(org_id='synthetic-magadan',user_id=u.id,role='engineer'))
        db.add(Asset(id='demo-grid',org_id='synthetic-magadan',name='Synthetic two-bus research feeder',classification='LAB_REFERENCE'))
        db.commit()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    t=threading.Thread(target=server.run,daemon=True);t.start()
    try:
        for _ in range(100):
            try:
                with httpx.Client(timeout=1) as client:
                    if client.get(f'http://127.0.0.1:{port}/health').status_code==200:break
            except Exception:pass
            time.sleep(.05)
        else:raise RuntimeError('Server did not start')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                errors=[]
                desktop=browser.new_page(viewport={'width':1440,'height':1000})
                desktop.on('pageerror',lambda error:errors.append(str(error)))
                desktop.goto(f'http://127.0.0.1:{port}/lab',wait_until='networkidle',timeout=18000)
                desktop.locator('input[name=email]').fill('engineer@test.invalid')
                desktop.locator('input[name=password]').fill('SyntheticLabPassword2026!')
                desktop.get_by_role('button',name='Войти').click()
                desktop.locator('#study-workspace').wait_for(state='visible',timeout=16000)
                desktop.locator('#study-module').select_option('heatnet')
                desktop.locator('#study-load').click()
                desktop.locator('#study-execute').click()
                desktop.wait_for_function("() => document.querySelector('#study-result').textContent.includes('SYNTHETIC_UNVERIFIED')",timeout=16000)
                desktop.locator('#study-reproduce').click()
                desktop.wait_for_function("() => document.querySelector('#study-result').textContent.includes('reproduced')",timeout=16000)
                desktop.screenshot(path=str(OUT/'v72-desktop.png'),full_page=True)
                desktop_overflow=desktop.evaluate('document.documentElement.scrollWidth > innerWidth')
                status['desktop']={'login':True,'study_run':True,'reproduced':True,'horizontal_overflow':desktop_overflow,'page_errors':errors}
                assert not desktop_overflow and not errors
                mobile=browser.new_page(viewport={'width':375,'height':812},device_scale_factor=1)
                mobile.on('pageerror',lambda error:errors.append(str(error)))
                mobile.goto(f'http://127.0.0.1:{port}/lab',wait_until='networkidle',timeout=18000)
                mobile.locator('input[name=email]').fill('engineer@test.invalid')
                mobile.locator('input[name=password]').fill('SyntheticLabPassword2026!')
                mobile.get_by_role('button',name='Войти').click()
                mobile.locator('#study-workspace').wait_for(state='visible',timeout=16000)
                mobile.locator('#study-workspace').scroll_into_view_if_needed()
                mobile.screenshot(path=str(OUT/'v72-mobile.png'),full_page=True)
                mobile_overflow=mobile.evaluate('document.documentElement.scrollWidth > innerWidth')
                status['mobile']={'login':True,'horizontal_overflow':mobile_overflow,'page_errors':errors}
                assert not mobile_overflow and not errors
                status['status']='BROWSER_SMOKE_PASS'
            finally:browser.close()
    except Exception as e:
        status['status']='BROWSER_SMOKE_FAIL';status['error']=type(e).__name__+': '+str(e)[:600]
    finally:
        server.should_exit=True;t.join(timeout=10)
OUT.joinpath('browser_smoke_v72.json').write_text(json.dumps(status,indent=2,ensure_ascii=False))
print(json.dumps(status,indent=2,ensure_ascii=False))
if status['status']!='BROWSER_SMOKE_PASS':raise SystemExit(1)
