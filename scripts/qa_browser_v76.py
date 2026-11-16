"""Bounded browser smoke. Writes honest outcomes; never bypasses policy blocks."""
import os,sys,json,subprocess,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts_v76';OUT.mkdir(exist_ok=True)
LAB=OUT/'browser_v76_synthetic.db'
if LAB.exists():LAB.unlink()
ENV=dict(os.environ,HYDRO_JWT_SECRET='synthetic-jwt-key-only-browser-smoke-2026-never-use-real',
 HYDRO_AUDIT_SECRET='synthetic-audit-key-only-browser-smoke-2026-never-use-real',
 HYDRO_DATABASE_URL='sqlite:///'+str(LAB),PYTHONPATH=str(ROOT/'server'))
proc=None
result={'scope':'SYNTHETIC_LOCAL_BROWSER_SMOKE','live_http':'NOT_RUN','network_e2e':'NOT_ACCEPTED','widths_tested':[]}
try:
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','hydro_api.asgi:app','--host','127.0.0.1','--port','8767'],env=ENV,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for i in range(80):
        if proc.poll() is not None:raise RuntimeError('SERVER_FAILED_STARTUP')
        try:
            res=urllib.request.urlopen('http://127.0.0.1:8767/health',timeout=0.5)
            if res.status==200:break
        except Exception:time.sleep(0.1)
    else:raise RuntimeError('HTTP_STARTUP_TIMEOUT')
    result['live_http']='SERVER_HEALTH_200'
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        try:
            page=b.new_page(viewport={'width':1440,'height':900})
            try:
                page.goto('http://127.0.0.1:8767/lab',wait_until='domcontentloaded',timeout=8000)
                page.wait_for_selector('#assurance-workspace',timeout=5000)
                result['network_e2e']='HTTP_PAGE_LOADED'
                for width in (1440,768,375):
                    page.set_viewport_size({'width':width,'height':900})
                    page.screenshot(path=str(OUT/f'v76-layout-{width}.png'),full_page=False)
                    overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
                    result['widths_tested'].append({'width':width,'overflow':overflow})
            except Exception as e:
                result['network_e2e']='BROWSER_BLOCKED_OR_FAILED'
                result['reason']=str(e)[:350]
                # Static layout verification does not assert network E2E.
                html=(ROOT/'server/ui/index.html').read_text()
                css=(ROOT/'server/ui/ui.css').read_text()
                html=html.replace('<link rel="stylesheet" href="/lab-assets/ui.css">','<style>'+css+'</style>')
                html=html.replace('<script type="module" src="/lab-assets/ui.js"></script>','')
                for width in (1440,768,375):
                    page.set_viewport_size({'width':width,'height':900})
                    page.set_content(html,wait_until='domcontentloaded',timeout=8000)
                    page.eval_on_selector('#lab','el => el.hidden=false')
                    page.screenshot(path=str(OUT/f'v76-layout-{width}.png'),full_page=False)
                    overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
                    result['widths_tested'].append({'width':width,'overflow':overflow,'mode':'STATIC_RENDER_ONLY'})
        finally:b.close()
except Exception as e:
    result['qa_error']=str(e)[:350]
finally:
    if proc:
        proc.terminate()
        try:proc.wait(timeout=4)
        except subprocess.TimeoutExpired:proc.kill()
    (OUT/'browser_smoke_v76.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
