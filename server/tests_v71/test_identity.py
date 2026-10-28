import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from hydro_api.identity import (AuthStore, IdentityMapping, LoginSession, IdentityError, OidcConfig,
    OidcService, b64url, token_hash)
from hydro_api.main import create_app, HASHER
from hydro_api.storage import setup_engine, Organization, User, Membership

@pytest.fixture
def oidc(tmp_path):
    url='sqlite:///'+str(tmp_path/'identity.db')
    engine,factory=setup_engine(url)
    with factory.begin() as db:
        db.add(Organization(id='magadan-lab',name='Synthetic Magadan study; not a corporate tenant'))
        db.add(User(id='u1',email='engineer@lab.invalid',password_hash=HASHER.hash('not-used-with-oidc'),active=True,token_version=0))
        db.flush()
        db.add(Membership(org_id='magadan-lab',user_id='u1',role='engineer',active=True))
    store=AuthStore(url,create_test_schema=True)
    cfg=OidcConfig(issuer='http://localhost:8999',client_id='hydro-lab',
        redirect_uri='http://testserver/v71/auth/callback',app_origin='http://testserver',
        required_acr=('urn:lab:mfa',),allow_loopback_http=True)
    with store.factory.begin() as db:
        db.add(IdentityMapping(id='map1',issuer=cfg.issuer,subject='subject-engineer',user_id='u1'))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid='key1',alg='RS256',use='sig')
    codes={}; requests=[]
    def claims(expected_nonce,**overrides):
        now=int(time.time())
        return {'iss':cfg.issuer,'sub':'subject-engineer','aud':cfg.client_id,'iat':now,'exp':now+900,
                'nonce':expected_nonce,'auth_time':now,'acr':'urn:lab:mfa',**overrides}
    def encoded(body,**headers):return jwt.encode(body,key,algorithm='RS256',headers={'kid':'key1',**headers})
    def provider(req):
        requests.append((req.method,req.url.path))
        if req.url.path.endswith('openid-configuration'):
            return httpx.Response(200,json={'issuer':cfg.issuer,'authorization_endpoint':cfg.issuer+'/authorize',
                'token_endpoint':cfg.issuer+'/token','jwks_uri':cfg.issuer+'/keys','code_challenge_methods_supported':['S256']})
        if req.url.path=='/keys':return httpx.Response(200,json={'keys':[jwk]})
        if req.url.path=='/token':
            form=parse_qs(req.content.decode());data=codes.pop(form['code'][0],None)
            if not data:return httpx.Response(400,json={'error':'invalid_grant'})
            verifier=form['code_verifier'][0]
            if b64url(hashlib.sha256(verifier.encode()).digest())!=data['challenge']:
                return httpx.Response(400,json={'error':'invalid_grant'})
            assert form['redirect_uri'][0]==cfg.redirect_uri
            return httpx.Response(200,json={'id_token':encoded(claims(data['nonce'],**data.get('overrides',{}))),
                                            'access_token':'opaque-provider-token','token_type':'Bearer'})
        return httpx.Response(404)
    service=OidcService(cfg,store,client=httpx.Client(transport=httpx.MockTransport(provider)))
    app=create_app(url,jwt_secret='v71-unused-local-jwt-secret-0123456789',
                   audit_secret='v71-separate-lab-audit-key-01234567890',oidc_service=service)
    client=TestClient(app)
    def begin(overrides=None):
        r=client.get('/v71/auth/start',follow_redirects=False)
        assert r.status_code==303
        params={k:v[0] for k,v in parse_qs(urlsplit(r.headers['location']).query).items()}
        code='test-code-'+str(len(codes))
        codes[code]={'nonce':params['nonce'],'challenge':params['code_challenge'],'overrides':overrides or {}}
        return code,params
    def login(overrides=None):
        code,p=begin(overrides)
        return client.get('/v71/auth/callback',params={'code':code,'state':p['state']},follow_redirects=False)
    yield locals()
    client.close();service.http.close();store.engine.dispose();engine.dispose();app.state.engine.dispose()


def test_complete_code_pkce_cookie_flow(oidc):
    o=oidc;c=o['client'];cfg=o['cfg']
    r=o['login']();assert r.status_code==303 and r.headers['location']=='/lab'
    assert cfg.cookie('session') in c.cookies
    assert 'HttpOnly' in r.headers['set-cookie']
    assert 'access_token' not in r.text
    session=o['store'].resolve(c.cookies[cfg.cookie('session')],int(time.time()))
    assert session.user_id=='u1'
    assert c.get('/v7/me').json()['organizations']==[{'org_id':'magadan-lab','role':'engineer'}]
    assert ('POST','/token') in o['requests']


def test_cookie_write_requires_origin_and_csrf(oidc):
    o=oidc;o['login']();c=o['client'];cfg=o['cfg'];url='/v7/orgs/magadan-lab/assets'
    body={'name':'Synthetic second feeder'}
    assert c.post(url,json=body).status_code==403
    csrf=c.cookies[cfg.cookie('csrf')]
    assert c.post(url,json=body,headers={'Origin':'https://evil.invalid','X-CSRF-Token':csrf}).status_code==403
    assert c.post(url,json=body,headers={'Origin':cfg.app_origin,'X-CSRF-Token':csrf}).status_code==201


def test_local_password_cannot_bypass_oidc(oidc):
    r=oidc['client'].post('/v7/auth/login',json={'email':'engineer@lab.invalid','password':'not-used-with-oidc'})
    assert r.status_code==404


def test_login_state_is_one_use_and_browser_bound(oidc):
    code,p=oidc['begin']()
    other=TestClient(oidc['app'])
    assert other.get('/v71/auth/callback',params={'code':code,'state':p['state']}).status_code==401
    c=oidc['client']
    assert c.get('/v71/auth/callback',params={'code':code,'state':p['state']},follow_redirects=False).status_code==303
    assert c.get('/v71/auth/callback',params={'code':code,'state':p['state']}).status_code==401


@pytest.mark.parametrize('overrides',[
 {'iss':'https://attacker.invalid'}, {'aud':'another-client'}, {'sub':''}, {'sub':'unprovisioned-user'},
 {'nonce':'wrong-nonce'}, {'exp':1}, {'iat':int(time.time())+9999}, {'auth_time':int(time.time())-9999},
 {'acr':'urn:lab:password-only'}, {'azp':'wrong-client'}, {'aud':['hydro-lab','another-client']},
 {'at_hash':'invalid-binding'}
])
def test_id_token_rejections(oidc,overrides):
    assert oidc['login'](overrides).status_code==401


def test_email_and_role_claim_do_not_grant_authority(oidc):
    o=oidc
    assert o['login']({'email':'manager@corporate.invalid','roles':['admin'],'org_id':'other-org'}).status_code==303
    assert o['client'].get('/v7/me').json()['organizations'][0]['role']=='engineer'


def test_signature_and_jku_rejected(oidc):
    o=oidc;service=o['service'];claims=o['claims']('expected')
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    bad=jwt.encode(claims,other,algorithm='RS256',headers={'kid':'key1'})
    with pytest.raises(IdentityError):service.validate_id_token(bad,'expected')
    bad=o['encoded'](claims,jku='https://attacker.invalid/keys')
    with pytest.raises(IdentityError):service.validate_id_token(bad,'expected')


def test_session_revoke_and_user_disable(oidc):
    o=oidc;o['login']();c=o['client'];cfg=o['cfg']
    raw=c.cookies[cfg.cookie('session')];csrf=c.cookies[cfg.cookie('csrf')]
    r=c.post('/v7/auth/logout',headers={'Origin':cfg.app_origin,'X-CSRF-Token':csrf})
    assert r.status_code==200 and r.json()['idp_global_logout'] is False
    with pytest.raises(IdentityError):o['store'].resolve(raw,int(time.time()))
    assert o['login']().status_code==303
    with o['factory'].begin() as db:
        db.get(User,'u1').active=False
    assert c.get('/v7/me').status_code==401


def test_state_survives_service_restart(oidc):
    o=oidc
    state,nonce,verifier=o['store'].begin('a-valid-browser-binding-0123456789',int(time.time()))
    new=AuthStore(o['url'],create_test_schema=True)
    assert new.consume(state,'a-valid-browser-binding-0123456789',int(time.time()))==(nonce,verifier)
    with pytest.raises(IdentityError):new.consume(state,'a-valid-browser-binding-0123456789',int(time.time()))


def test_insecure_or_unassured_production_config_rejected():
    with pytest.raises(IdentityError):OidcConfig(issuer='http://idp.example',client_id='x',redirect_uri='https://x/cb',app_origin='https://x')
    with pytest.raises(IdentityError):OidcConfig(issuer='https://idp.example',client_id='x',redirect_uri='https://x/cb',app_origin='https://x')
    with pytest.raises(IdentityError):OidcConfig(issuer='https://idp.example',client_id='x',redirect_uri='https://other/cb',app_origin='https://x',required_acr=('mfa',))
