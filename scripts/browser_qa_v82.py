"""Real Chromium HTTP login → synthetic V8.2 forecast → visual QA. LAB only."""
import json,os,socket,tempfile,threading,time
from pathlib import Path
import httpx,uvicorn
from playwright.sync_api import sync_playwright
from hydro_api.main import create_app,HASHER
from hydro_api.storage import Organization,User,Membership,Asset

OUT=Path(__file__).resolve().parents[1]/'artifacts_v82'
OUT.mkdir(exist_ok=True)
summary={'status':'NOT_EXECUTED','client':'chromium','synthetic_only':True,
         'actual_rushydro_data_used':False,'industrial_approval_eligible':False,'viewports':{}}
with tempfile.TemporaryDirectory(prefix='hk82-browser-') as tmp:
    app=create_app(database_url='sqlite:///'+str(Path(tmp)/'study.db'),
            jwt_secret='synthetic-browser-jwt-secret-only-test-2026-MAGADAN-123456',
            audit_secret='synthetic-browser-audit-secret-only-test-2026-MAGADAN-123456')
    with app.state.SessionLocal() as db:
        db.add(Organization(id='magadan-lab-browser',name='Synthetic research organization'))
        db.flush()
        u=User(email='engineer-v82@test.invalid',password_hash=HASHER.hash('SyntheticForecastBrowserTest2026!'))
        db.add(u);db.flush()
        db.add(Membership(org_id='magadan-lab-browser',user_id=u.id,role='engineer'))
        db.add(Asset(id='lab-asset-v82',org_id='magadan-lab-browser',
                     name='Synthetic research boundary',classification='LAB_REFERENCE'))
        db.commit()
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    th=threading.Thread(target=server.run,daemon=True);th.start()
    try:
        for _ in range(70):
            try:
                if httpx.get(f'http://127.0.0.1:{port}/health',timeout=0.35).status_code==200:break
            except Exception:pass
            time.sleep(0.05)
        else:raise RuntimeError('LOCAL_TEST_SERVER_NOT_AVAILABLE')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                for width,height in [(1440,960),(768,980),(375,820)]:
                    page=browser.new_page(viewport={'width':width,'height':height})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{port}/lab',wait_until='domcontentloaded',timeout=13000)
                    page.locator('input[name=email]').fill('engineer-v82@test.invalid')
                    page.locator('input[name=password]').fill('SyntheticForecastBrowserTest2026!')
                    page.get_by_role('button',name='Войти').click()
                    page.locator('#forecast-v82-workspace').wait_for(state='visible',timeout=15000)
                    page.locator('#v82-sample').click()
                    page.wait_for_function("() => document.querySelector('#v82-case').value.includes('observations')",timeout=4000)
                    page.locator('#v82-run').click()
                    page.wait_for_function("() => document.querySelector('#v82-mae').textContent !== '—'",timeout=16000)
                    page.locator('#forecast-v82-workspace').scroll_into_view_if_needed()
                    page.locator('#forecast-v82-workspace').screenshot(path=str(OUT/f'forecast-browser-v82-{width}.png'))
                    scroll=page.evaluate('document.documentElement.scrollWidth')
                    score=page.locator('#v82-mae').text_content()
                    chart=page.locator('#v82-plot svg').count()
                    row={'login':True,'forecast_computed':True,'mae':score,
                         'chart_present':bool(chart),'page_errors':errors,
                         'viewport_width':width,'document_scroll_width':scroll,
                         'horizontal_overflow':scroll>width+1}
                    summary['viewports'][str(width)]=row
                    assert not errors,(width,errors)
                    assert row['chart_present'],width
                    assert not row['horizontal_overflow'],(width,scroll)
                    page.close()
                summary['status']='SYNTHETIC_BROWSER_E2E_PASS'
            finally:
                browser.close()
    except Exception as exc:
        summary['status']='BROWSER_E2E_BLOCKED_OR_FAILED'
        summary['error']=type(exc).__name__+': '+str(exc)[:600]
    finally:
        server.should_exit=True;th.join(timeout=7)
        app.state.engine.dispose()
OUT.joinpath('browser_e2e_v82.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
if summary['status']!='SYNTHETIC_BROWSER_E2E_PASS':raise SystemExit(2)
