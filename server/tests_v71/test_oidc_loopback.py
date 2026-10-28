"""Full HTTP redirect+code exchange against a local synthetic IdP.
Not a corporate login, real employee identity, MFA ceremony or PostgreSQL test.
"""
import hashlib,json,secrets,socket,threading,time
from urllib.parse import parse_qs,urlencode
import httpx,jwt,uvicorn
from fastapi import FastAPI,Request
from fastapi.responses import RedirectResponse,JSONResponse
from cryptography.hazmat.primitives.asymmetric import rsa
from hydro_api.identity import AuthStore,IdentityMapping,OidcConfig,OidcService,b64url
from hydro_api.storage import setup_engine,Organization,User,Membership
from hydro_api.main import create_app


def test_full_oidc_flow_over_actual_local_http(tmp_path):
    sockets=[];servers=[];threads=[]
    def reserve():
        s=socket.socket();s.bind(('127.0.0.1',0));sockets.append(s);return s,s.getsockname()[1]
    idp_sock,idp_port=reserve();api_sock,api_port=reserve()
    issuer=f'http://127.0.0.1:{idp_port}';origin=f'http://127.0.0.1:{api_port}'
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk.update(kid='loopback',alg='RS256',use='sig')
    codes={};provider=FastAPI();observed=[]
    @provider.get('/.well-known/openid-configuration')
    def metadata():return {'issuer':issuer,'authorization_endpoint':issuer+'/authorize',
        'token_endpoint':issuer+'/token','jwks_uri':issuer+'/keys','code_challenge_methods_supported':['S256']}
    @provider.get('/keys')
    def keys():return {'keys':[jwk]}
    @provider.get('/authorize')
    def authorize(request:Request):
        q=dict(request.query_params)
        assert q['response_type']=='code' and q['code_challenge_method']=='S256'
        assert q['redirect_uri']==origin+'/v71/auth/callback'
        code=secrets.token_urlsafe(32);codes[code]=q
        observed.append('authorization')
        return RedirectResponse(q['redirect_uri']+'?'+urlencode({'state':q['state'],'code':code}),status_code=303)
    @provider.post('/token')
    async def token(request:Request):
        form={k:v[0] for k,v in parse_qs((await request.body()).decode()).items()}
        q=codes.pop(form.get('code',''),None)
        if not q:return JSONResponse({'error':'invalid_grant'},status_code=400)
        assert b64url(hashlib.sha256(form['code_verifier'].encode()).digest())==q['code_challenge']
        assert form['redirect_uri']==q['redirect_uri']
        now=int(time.time());observed.append('pkce_code_exchange')
        claims={'iss':issuer,'sub':'synthetic-engineer','aud':'loopback-client','iat':now,'exp':now+900,
                'auth_time':now,'acr':'urn:loopback:simulated-assurance','nonce':q['nonce']}
        return {'id_token':jwt.encode(claims,key,algorithm='RS256',headers={'kid':'loopback'}),'access_token':'synthetic','token_type':'Bearer'}
    url='sqlite:///'+str(tmp_path/'loopback-auth.db');engine,factory=setup_engine(url)
    with factory.begin() as db:
        db.add(Organization(id='magadan-loopback-lab',name='Synthetic Magadan software acceptance'))
        db.add(User(id='loopback-u1',email='loopback@lab.invalid',password_hash='!OIDC_ONLY',active=True,token_version=0));db.flush()
        db.add(Membership(org_id='magadan-loopback-lab',user_id='loopback-u1',role='engineer',active=True))
    store=AuthStore(url,create_test_schema=True)
    with store.factory.begin() as db:db.add(IdentityMapping(id='mapping',issuer=issuer,subject='synthetic-engineer',user_id='loopback-u1'))
    config=OidcConfig(issuer=issuer,client_id='loopback-client',redirect_uri=origin+'/v71/auth/callback',app_origin=origin,
        required_acr=('urn:loopback:simulated-assurance',),allow_loopback_http=True)
    identity=OidcService(config,store)
    application=create_app(url,jwt_secret=secrets.token_urlsafe(40),audit_secret=secrets.token_urlsafe(40),oidc_service=identity)
    def launch(app,sock):
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,loop='asyncio',ws='none'));servers.append(server)
        t=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);threads.append(t);t.start()
        for _ in range(100):
            if server.started:return
            time.sleep(.02)
        raise AssertionError('Local HTTP service did not start')
    try:
        launch(provider,idp_sock);launch(application,api_sock)
        with httpx.Client(base_url=origin,follow_redirects=True,trust_env=False,timeout=8) as client:
            login=client.get('/v71/auth/start')
            assert login.status_code==200 and login.url.path=='/lab'
            assert observed==['authorization','pkce_code_exchange']
            me=client.get('/v7/me');assert me.status_code==200 and me.json()['user_id']=='loopback-u1'
            csrf=client.cookies.get(config.cookie('csrf'))
            assert client.post('/v7/orgs/magadan-loopback-lab/assets',json={'name':'test feeder'}).status_code==403
            out=client.post('/v7/auth/logout',headers={'Origin':origin,'X-CSRF-Token':csrf})
            assert out.status_code==200
            assert client.get('/v7/me').status_code==401
    finally:
        for server in servers:server.should_exit=True
        for t in threads:t.join(timeout=5)
        for s in sockets:s.close()
        identity.http.close();store.engine.dispose();engine.dispose()
