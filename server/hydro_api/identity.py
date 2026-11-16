"""OIDC authorization-code + S256 PKCE adapter. No email-based auto-provisioning.

Production identity must be pre-provisioned by (issuer, subject). The local
protocol tests exercise cryptography and HTTP contracts, not a corporate IdP.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
from typing import Callable
import httpx
from fastapi import Request
import jwt
from jwt import PyJWTError
from sqlalchemy import BigInteger, Boolean, String, Text, UniqueConstraint, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .storage import User, new_id


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


class IdentityError(ValueError):
    """Deliberately contains no token, code, nonce, subject or secret."""


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    redirect_uri: str
    app_origin: str
    client_secret: str | None = None
    required_acr: tuple[str, ...] = ()
    max_auth_age: int = 600
    session_ttl: int = 900
    allow_loopback_http: bool = False
    allowed_endpoint_origins: tuple[str, ...] = ()

    def __post_init__(self):
        for url in (self.issuer, self.redirect_uri, self.app_origin):
            p = urlsplit(url)
            local = p.hostname in ('127.0.0.1', 'localhost', 'testserver')
            if not p.hostname or p.username or p.password or p.fragment:
                raise IdentityError('INVALID_ENDPOINT')
            if p.scheme != 'https' and not (self.allow_loopback_http and local and p.scheme == 'http'):
                raise IdentityError('HTTPS_REQUIRED')
        r = urlsplit(self.redirect_uri)
        if self.app_origin != f'{r.scheme}://{r.netloc}' or r.query:
            raise IdentityError('FIXED_SAME_ORIGIN_CALLBACK_REQUIRED')
        if not self.client_id or not 60 <= self.session_ttl <= 3600 or not 60 <= self.max_auth_age <= 3600:
            raise IdentityError('INVALID_IDENTITY_CONFIGURATION')
        if not self.allow_loopback_http and not self.required_acr:
            raise IdentityError('PRODUCTION_ASSURANCE_POLICY_REQUIRED')

    @property
    def secure(self):
        return urlsplit(self.app_origin).scheme == 'https'

    def cookie(self, suffix):
        return ('__Host-hk_' if self.secure else 'hk_lab_') + suffix


class AuthBase(DeclarativeBase):
    pass


class IdentityMapping(AuthBase):
    __tablename__ = 'identities'
    __table_args__ = (UniqueConstraint('issuer', 'subject'), {'schema': 'hk_auth'})
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(String)


class LoginTransaction(AuthBase):
    __tablename__ = 'oidc_transactions'
    __table_args__ = {'schema': 'hk_auth'}
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(Text)
    verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class LoginSession(AuthBase):
    __tablename__ = 'sessions'
    __table_args__ = {'schema': 'hk_auth'}
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    token_version: Mapped[int] = mapped_column(BigInteger)
    issuer: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    auth_time: Mapped[int] = mapped_column(BigInteger)
    acr: Mapped[str] = mapped_column(Text)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(BigInteger)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthStore:
    """Separate credential: not the ordinary RLS application connection."""
    def __init__(self, url: str, *, create_test_schema=False):
        opts = {'connect_args': {'check_same_thread': False}} if url.startswith('sqlite') else {}
        self.engine = create_engine(url, **opts)
        if url.startswith('sqlite'):
            self.engine = self.engine.execution_options(schema_translate_map={'hk_auth': None})
            if not create_test_schema:
                raise IdentityError('SQLITE_AUTH_IS_TEST_ONLY')
            AuthBase.metadata.create_all(self.engine)
        elif create_test_schema:
            raise IdentityError('MIGRATE_POSTGRES_SEPARATELY')
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    def begin(self, binding: str, now: int):
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        with self.factory.begin() as db:
            db.add(LoginTransaction(state_hash=token_hash(state), binding_hash=token_hash(binding),
                nonce=nonce, verifier=verifier, expires_at=now+300, consumed=False))
        return state, nonce, verifier

    def consume(self, state: str, binding: str, now: int):
        if not 20 <= len(state) <= 200 or not 20 <= len(binding) <= 200:
            raise IdentityError('INVALID_OR_EXPIRED_LOGIN')
        with self.factory.begin() as db:
            stmt = update(LoginTransaction).where(
                LoginTransaction.state_hash == token_hash(state),
                LoginTransaction.binding_hash == token_hash(binding),
                LoginTransaction.expires_at > now, LoginTransaction.consumed == False
            ).values(consumed=True).returning(LoginTransaction.nonce, LoginTransaction.verifier)
            result = db.execute(stmt).first()
            if not result:
                raise IdentityError('INVALID_OR_EXPIRED_LOGIN')
            return result.nonce, result.verifier

    def issue(self, claims: dict, config: OidcConfig, now: int):
        raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.factory.begin() as db:
            principal = db.scalar(select(IdentityMapping).where(
                IdentityMapping.issuer == claims['iss'], IdentityMapping.subject == claims['sub']))
            if not principal:
                raise IdentityError('PRINCIPAL_NOT_PROVISIONED')
            user = db.execute(select(User.id, User.active, User.token_version).where(User.id == principal.user_id)).first()
            if not user or not user.active:
                raise IdentityError('PRINCIPAL_DISABLED')
            db.add(LoginSession(token_hash=token_hash(raw), user_id=user.id, token_version=user.token_version,
                issuer=claims['iss'], subject=claims['sub'], auth_time=claims['auth_time'],
                acr=claims.get('acr', ''), csrf_hash=token_hash(csrf),
                expires_at=min(now+config.session_ttl, claims['exp']), revoked=False))
        return raw, csrf

    def resolve(self, raw: str, now: int):
        if not isinstance(raw, str) or not 32 <= len(raw) <= 256:
            raise IdentityError('INVALID_SESSION')
        with self.factory() as db:
            s = db.get(LoginSession, token_hash(raw))
            if not s or s.revoked or s.expires_at <= now:
                raise IdentityError('INVALID_SESSION')
            u = db.execute(select(User.id, User.active, User.token_version).where(User.id == s.user_id)).first()
            if not u or not u.active or u.token_version != s.token_version:
                raise IdentityError('INVALID_SESSION')
            return s

    def revoke(self, raw: str):
        with self.factory.begin() as db:
            db.execute(update(LoginSession).where(LoginSession.token_hash == token_hash(raw)).values(revoked=True))


class OidcService:
    def __init__(self, config: OidcConfig, store: AuthStore, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.time):
        self.config, self.store, self.clock = config, store, clock
        self.http = client or httpx.Client(timeout=8, follow_redirects=False, trust_env=False)
        self._metadata = None
        self._jwks = None
        self._keys_at = 0

    def _json(self, response):
        if response.status_code != 200 or len(response.content) > 262144:
            raise IdentityError('IDENTITY_PROVIDER_UNAVAILABLE')
        try:
            value = response.json()
            if not isinstance(value, dict): raise ValueError()
            return value
        except ValueError:
            raise IdentityError('INVALID_PROVIDER_RESPONSE') from None

    def metadata(self):
        if self._metadata is None:
            c = self.config
            m = self._json(self.http.get(c.issuer.rstrip('/')+'/.well-known/openid-configuration'))
            if m.get('issuer') != c.issuer or 'S256' not in m.get('code_challenge_methods_supported', []):
                raise IdentityError('PROVIDER_CONFIGURATION_MISMATCH')
            allowed = {self._origin(c.issuer), *c.allowed_endpoint_origins}
            for name in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
                endpoint = m.get(name, '')
                if self._origin(endpoint) not in allowed or urlsplit(endpoint).fragment or urlsplit(endpoint).username:
                    raise IdentityError('UNTRUSTED_PROVIDER_ENDPOINT')
            self._metadata = m
        return self._metadata

    @staticmethod
    def _origin(url):
        p = urlsplit(url)
        return f'{p.scheme}://{p.netloc}'

    def start(self):
        now = int(self.clock())
        binding = secrets.token_urlsafe(32)
        state, nonce, verifier = self.store.begin(binding, now)
        c = self.config
        params = {'response_type':'code', 'client_id':c.client_id, 'redirect_uri':c.redirect_uri,
            'scope':'openid', 'state':state, 'nonce':nonce, 'max_age':c.max_auth_age,
            'code_challenge':b64url(hashlib.sha256(verifier.encode()).digest()), 'code_challenge_method':'S256'}
        if c.required_acr: params['acr_values'] = ' '.join(c.required_acr)
        return self.metadata()['authorization_endpoint']+'?'+urlencode(params), binding

    def _key(self, kid):
        now = self.clock()
        if self._jwks is None or now-self._keys_at > 300:
            self._jwks = self._json(self.http.get(self.metadata()['jwks_uri'])).get('keys', [])
            self._keys_at = now
        matches = [k for k in self._jwks if k.get('kid') == kid and k.get('kty') == 'RSA'
            and k.get('use', 'sig') == 'sig' and k.get('alg', 'RS256') == 'RS256']
        if not matches and now-self._keys_at > 5:
            self._jwks = None
            return self._key(kid)
        if len(matches) != 1:
            raise IdentityError('UNKNOWN_OR_AMBIGUOUS_SIGNING_KEY')
        key = jwt.PyJWK.from_dict(matches[0], algorithm='RS256').key
        if key.key_size < 2048: raise IdentityError('WEAK_SIGNING_KEY')
        return key

    def validate_id_token(self, encoded: str, nonce: str, access_token: str | None = None):
        c = self.config
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get('alg') != 'RS256' or not header.get('kid') or any(k in header for k in ('jku','x5u','crit')):
                raise IdentityError('INVALID_TOKEN_HEADER')
            claims = jwt.decode(encoded, self._key(header['kid']), algorithms=['RS256'], issuer=c.issuer,
                audience=c.client_id, leeway=30,
                options={'require':['iss','sub','aud','iat','exp','nonce','auth_time']})
            if not isinstance(claims['sub'], str) or not 1 <= len(claims['sub']) <= 256:
                raise IdentityError('INVALID_SUBJECT')
            if not isinstance(claims['nonce'], str) or not hmac.compare_digest(claims['nonce'], nonce):
                raise IdentityError('NONCE_MISMATCH')
            aud = claims['aud']
            if (isinstance(aud, list) and len(aud) > 1 and claims.get('azp') != c.client_id) or (
                'azp' in claims and claims['azp'] != c.client_id):
                raise IdentityError('AUTHORIZED_PARTY_MISMATCH')
            now = int(self.clock())
            if not isinstance(claims['auth_time'], int) or claims['auth_time'] > now+30 or now-claims['auth_time'] > c.max_auth_age+30:
                raise IdentityError('FRESH_AUTHENTICATION_REQUIRED')
            if c.required_acr and claims.get('acr') not in c.required_acr:
                raise IdentityError('ASSURANCE_POLICY_NOT_MET')
            if 'at_hash' in claims:
                if not access_token or not hmac.compare_digest(claims['at_hash'], b64url(hashlib.sha256(access_token.encode()).digest()[:16])):
                    raise IdentityError('ACCESS_TOKEN_HASH_MISMATCH')
            return claims
        except (PyJWTError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, IdentityError): raise
            raise IdentityError('INVALID_ID_TOKEN') from None

    def finish(self, code: str, state: str, binding: str):
        if not code or len(code) > 2048:
            raise IdentityError('INVALID_AUTHORIZATION_CODE')
        nonce, verifier = self.store.consume(state, binding, int(self.clock()))
        c = self.config
        data = {'grant_type':'authorization_code', 'code':code, 'redirect_uri':c.redirect_uri,
                'code_verifier':verifier, 'client_id':c.client_id}
        auth = httpx.BasicAuth(c.client_id, c.client_secret) if c.client_secret else None
        tokens = self._json(self.http.post(self.metadata()['token_endpoint'], data=data, auth=auth))
        claims = self.validate_id_token(tokens.get('id_token', ''), nonce, tokens.get('access_token'))
        return self.store.issue(claims, c, int(self.clock()))


def register_oidc_routes(app, service: OidcService):
    from fastapi import Request, HTTPException
    from fastapi.responses import RedirectResponse, JSONResponse
    c = service.config

    @app.get('/v71/auth/config')
    def config():
        return {'mode':'oidc', 'start':'/v71/auth/start', 'csrf_cookie':c.cookie('csrf'),
                'corporate_connection_verified':False, 'session_storage':'server-side opaque token hash'}

    @app.get('/v71/auth/start')
    def start():
        try: url, binding = service.start()
        except (IdentityError, httpx.HTTPError): raise HTTPException(503, 'Identity service unavailable') from None
        response = RedirectResponse(url, status_code=303)
        response.set_cookie(c.cookie('oidc'), binding, max_age=300, httponly=True, secure=c.secure, samesite='lax', path='/')
        return response

    @app.get('/v71/auth/callback')
    def callback(request: Request, code: str = '', state: str = ''):
        try: raw, csrf = service.finish(code, state, request.cookies.get(c.cookie('oidc'), ''))
        except (IdentityError, httpx.HTTPError): raise HTTPException(401, 'Corporate sign-in could not be verified') from None
        response = RedirectResponse('/lab', status_code=303)
        response.delete_cookie(c.cookie('oidc'), path='/', secure=c.secure, httponly=True, samesite='lax')
        response.set_cookie(c.cookie('session'), raw, max_age=c.session_ttl, httponly=True, secure=c.secure, samesite='lax', path='/')
        response.set_cookie(c.cookie('csrf'), csrf, max_age=c.session_ttl, httponly=False, secure=c.secure, samesite='lax', path='/')
        return response
