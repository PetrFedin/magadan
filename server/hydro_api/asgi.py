"""Explicit launch profile; never silently fall back to SQLite in a PG deploy."""
import os
from .main import create_app

profile=os.environ.get('HYDRO_PROFILE','legacy_lab')
if profile=='legacy_lab':
    if os.environ.get('HYDRO_DATABASE_URL','').startswith('postgresql'):
        raise RuntimeError('PostgreSQL requires HYDRO_PROFILE=postgres_lab and explicit OIDC configuration')
    app=create_app()
elif profile=='postgres_lab':
    from .identity import OidcConfig,AuthStore,OidcService
    config=OidcConfig(issuer=os.environ['HYDRO_OIDC_ISSUER'],client_id=os.environ['HYDRO_OIDC_CLIENT_ID'],
        client_secret=os.environ.get('HYDRO_OIDC_CLIENT_SECRET'),
        redirect_uri=os.environ['HYDRO_OIDC_REDIRECT_URI'],app_origin=os.environ['HYDRO_APP_ORIGIN'],
        required_acr=tuple(filter(None,os.environ.get('HYDRO_REQUIRED_ACR','').split(','))),
        allow_loopback_http=os.environ.get('HYDRO_ALLOW_LOOPBACK_HTTP')=='YES')
    identity=OidcService(config,AuthStore(os.environ['HYDRO_AUTH_DATABASE_URL']))
    app=create_app(database_url=os.environ['HYDRO_DATABASE_URL'],oidc_service=identity)
else:
    raise RuntimeError('Production profile is intentionally unavailable until external acceptance gates are signed')
