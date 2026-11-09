"""V8.7 unified LOCAL staging evidence: real PostgreSQL17 + OIDC HTTP + Chromium.

The isolated provider is synthetic and does NOT perform MFA. It emits a
laboratory ACR assertion to test fail-closed app enforcement. This is NOT
a corporate IdP, production SSO test, or real MFA enrollment ceremony.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

import jwt
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hydro_api.identity import AuthStore, IdentityMapping, OidcConfig, OidcService, b64url
from hydro_api.main import create_app
from hydro_api.storage import Asset, Membership, Organization, User
from tests_v88.fixture import synthetic_region_v88

CFG_PATH = os.environ.get("HYDRO_NATIVE_CONFIG")
if not CFG_PATH:
    if os.environ.get("HYDRO_NATIVE_TESTS_REQUIRED") == "1":
        raise RuntimeError("V87_UNIFIED_STAGING_BLOCKED: PostgreSQL17 native config missing")
    pytest.skip("V87 requires real PostgreSQL17, not SQLite", allow_module_level=True)
CFG = json.loads(open(CFG_PATH, encoding="utf-8").read())
pytestmark = pytest.mark.native_pg

ACR = "urn:lab:synthetic-mfa-claim-only"
CLIENT_ID = "v87-synthetic-http-staging"
SUBJECTS = {
    "engineer": ("engineer", "org"),
    "auditor": ("auditor", "org"),
    "economist": ("economist", "org"),
    "manager": ("manager", "org"),
    "viewer": ("viewer", "org"),
    "other": ("engineer", "other"),
    "weak": ("engineer", "org"),
}


def reserve_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    return sock, sock.getsockname()[1]


@pytest.fixture(scope="module")
def unified(tmp_path_factory):
    # The administrator is used ONLY for synthetic fixture provisioning.
    # The application itself always uses the low-privilege hk_app role.
    admin_engine = create_engine(CFG["admin_url"].replace("postgresql://", "postgresql+psycopg://", 1))
    auth = AuthStore(CFG["auth_url"])
    suffix = uuid4().hex[:12]
    org, other = "v87-synthetic-" + suffix, "v87-isolated-" + suffix
    uid = {name: uuid4().hex for name in SUBJECTS}
    asset_id = uuid4().hex
    idp_sock, idp_port = reserve_socket()
    api_sock, api_port = reserve_socket()
    issuer = "http://127.0.0.1:" + str(idp_port)
    origin = "http://127.0.0.1:" + str(api_port)

    with sessionmaker(admin_engine).begin() as db:
        db.add_all([
            Organization(id=org, name="V87 SYNTHETIC staging integration, no field data"),
            Organization(id=other, name="V87 isolated tenant, no field data"),
        ])
        db.flush()
        for subject, (role, tenant) in SUBJECTS.items():
            db.add(User(id=uid[subject], email=subject + "-" + suffix + "@lab.invalid",
                        password_hash="!OIDC_SYNTHETIC_ONLY", active=True, token_version=0))
            db.flush()
            db.add(Membership(org_id=org if tenant == "org" else other, user_id=uid[subject],
                              role=role, active=True))
            db.add(IdentityMapping(id=uuid4().hex, issuer=issuer,
                                   subject="v87-" + subject, user_id=uid[subject]))
        # The audit trigger forbids provisioning an asset without a signed
        # runtime session. Create it later through the real engineer API.

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="v87-synthetic", alg="RS256", use="sig")
    codes = {}
    idp = FastAPI()

    @idp.get("/.well-known/openid-configuration")
    def metadata():
        return {
            "issuer": issuer,
            "authorization_endpoint": issuer + "/authorize",
            "token_endpoint": issuer + "/token",
            "jwks_uri": issuer + "/keys",
            "code_challenge_methods_supported": ["S256"],
        }

    @idp.get("/keys")
    def keys():
        return {"keys": [jwk]}

    @idp.get("/choose")
    def choose(sub: str):
        if sub not in SUBJECTS and sub != "unprovisioned":
            raise HTTPException(400, "Unknown synthetic identity")
        response = PlainTextResponse("SYNTHETIC_IDP_SUBJECT_SELECTED_NO_AUTH")
        response.set_cookie("v87_synthetic_subject", sub, httponly=True, samesite="lax")
        return response

    @idp.get("/authorize")
    def authorize(request: Request):
        q = dict(request.query_params)
        sub = request.cookies.get("v87_synthetic_subject")
        if sub not in SUBJECTS and sub != "unprovisioned":
            raise HTTPException(403, "Synthetic identity not selected")
        if (q.get("response_type") != "code"
                or q.get("code_challenge_method") != "S256"
                or q.get("redirect_uri") != origin + "/v71/auth/callback"
                or q.get("client_id") != CLIENT_ID
                or q.get("acr_values") != ACR):
            raise HTTPException(400, "OIDC code-flow invariants broken")
        code = secrets.token_urlsafe(32)
        codes[code] = (q, sub)
        return RedirectResponse(q["redirect_uri"] + "?" + urlencode({
            "code": code, "state": q["state"]
        }), status_code=303)

    @idp.post("/token")
    async def token(request: Request):
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        pair = codes.pop(form.get("code", ""), None)
        if not pair:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        q, sub = pair
        if (form.get("client_id") != CLIENT_ID
                or form.get("redirect_uri") != q["redirect_uri"]
                or b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest()) != q["code_challenge"]):
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        now = int(time.time())
        claims = {
            "iss": issuer, "sub": "v87-" + sub, "aud": CLIENT_ID,
            "iat": now, "exp": now + 600, "auth_time": now,
            "nonce": q["nonce"],
            "acr": "urn:lab:password-only" if sub == "weak" else ACR,
        }
        return {"id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "v87-synthetic"}),
                "token_type": "Bearer", "access_token": "synthetic-no-finance"}

    oidc_config = OidcConfig(
        issuer=issuer, client_id=CLIENT_ID, redirect_uri=origin + "/v71/auth/callback",
        app_origin=origin, required_acr=(ACR,), allow_loopback_http=True
    )
    service = OidcService(oidc_config, auth)
    app = create_app(CFG["app_url"], jwt_secret=secrets.token_urlsafe(48),
                     audit_secret=secrets.token_urlsafe(48), oidc_service=service,
                     allow_test_bearer=False)
    servers, threads = [], []

    def launch(application, sock):
        server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1",
            log_level="error", access_log=False, loop="asyncio", ws="none"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        servers.append(server)
        threads.append(thread)
        thread.start()
        for _ in range(250):
            if server.started:
                return
            time.sleep(0.02)
        raise AssertionError("V87 temporary HTTP service did not start")

    try:
        launch(idp, idp_sock)
        launch(app, api_sock)
        yield {"origin": origin, "issuer": issuer, "org": org, "other": other,
               "uid": uid, "auth": auth, "app": app, "admin": admin_engine, "asset": asset_id,
               "codes": codes, "tmp": tmp_path_factory.mktemp("v87-unified")}
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=10)
        for sock in (idp_sock, api_sock):
            sock.close()
        service.http.close()
        auth.engine.dispose()
        app.state.engine.dispose()
        admin_engine.dispose()
        assert all(not thread.is_alive() for thread in threads), "V87_HTTP_CLEANUP_FAILED"


def test_v87_real_pg17_oidc_http_chromium_roles_and_audit(unified):
    env = unified
    assert env["app"].state.engine.dialect.name == "postgresql"
    executable = os.environ.get("HYDRO_BROWSER_EXECUTABLE")
    screenshots = os.environ.get("HYDRO_BROWSER_EVIDENCE_DIR")
    with sync_playwright() as p:
        opts = {"headless": True, "args": ["--no-proxy-server"]}
        if executable:
            opts["executable_path"] = executable
        browser = p.chromium.launch(**opts)
        contexts = {}
        try:
            for subject in ("engineer", "auditor", "economist", "manager", "viewer", "other"):
                context = browser.new_context(viewport={"width": 390 if subject == "viewer" else 1440,
                                                       "height": 900})
                page = context.new_page()
                response = page.goto(env["issuer"] + "/choose?sub=" + subject)
                assert response.status == 200
                page.goto(env["origin"] + "/v71/auth/start", wait_until="load")
                assert page.url == env["origin"] + "/lab", (subject, page.url)
                expect(page.locator("#lab")).to_be_visible(timeout=10000)
                # A freshly created tenant intentionally has zero assets until the
                # engineer creates one through the audited runtime API.
                expect(page.locator("#notice")).to_contain_text("Вход OIDC", timeout=10000)
                expected_org = env["other"] if subject == "other" else env["org"]
                expect(page.locator("#org")).to_have_value(expected_org)
                expect(page.locator("#role-info")).to_contain_text(SUBJECTS[subject][0])
                assert context.request.get(env["origin"] + "/v7/me").status == 200
                contexts[subject] = (context, page)
                if subject == "engineer":
                    # Fixture creation must go through hk_app + OIDC cookie + CSRF.
                    cookie_name = "hk_lab_csrf"
                    cookies = {c["name"]: c["value"] for c in context.cookies()}
                    assert cookie_name in cookies, "OIDC_CSRF_COOKIE_NOT_SET"
                    added = context.request.post(
                        env["origin"] + "/v7/orgs/" + env["org"] + "/assets",
                        data=json.dumps({"name": "V87 synthetic 20kV feeder",
                                         "classification": "LAB_REFERENCE"}),
                        headers={"Content-Type": "application/json",
                                 "Origin": env["origin"],
                                 "X-CSRF-Token": cookies[cookie_name]})
                    assert added.status == 201, ("ENGINEER_ASSET_CREATE_FAIL", added.status, added.text()[:180])
                    page.reload(wait_until="load")
                    expect(page.locator("#asset option").first).to_be_attached()
                if screenshots:
                    from pathlib import Path
                    target = Path(screenshots)
                    target.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target / ("v87-pg-oidc-" + subject + ".png")), full_page=True)

            # Explicitly assert what the exercise does NOT certify.
            ready = contexts["auditor"][0].request.get(
                env["origin"] + "/v71/meta/readiness")
            assert ready.status == 200
            readiness = ready.json()
            assert readiness["database_backend"] == "postgresql"
            assert readiness["corporate_idp_verified"] is False
            assert readiness["production_ready"] is False
            unauthenticated = browser.new_context()
            assert unauthenticated.request.get(env["origin"] + "/v7/me").status == 401
            unauthenticated.close()

            # Tenant read is forbidden even with a valid session from a different organization.
            assert contexts["other"][0].request.get(
                env["origin"] + "/v7/orgs/" + env["org"] + "/assets").status in (403, 404)

            # Cookie-session mutations must enforce Origin and CSRF token binding.
            assert contexts["engineer"][0].request.post(
                env["origin"] + "/v7/orgs/" + env["org"] + "/assets",
                data={"name": "CSRF should fail"}, headers={"Content-Type": "application/json"}).status == 403

            engineer = contexts["engineer"][1]
            engineer.locator("#create-evidence").click()
            expect(engineer.locator("#evidence-list")).to_contain_text("pending", timeout=10000)
            auditor = contexts["auditor"][1]
            auditor.reload(wait_until="load")
            expect(auditor.locator("#lab")).to_be_visible()
            expect(auditor.locator("#evidence-list")).to_contain_text("pending")
            auditor.locator("#accept-evidence").click()
            expect(auditor.locator("#evidence-list")).to_contain_text("accepted")
            auditor.locator("#verify-audit").click()
            expect(auditor.locator("#audit-result")).to_contain_text('"valid": true')
            delivery = contexts["auditor"][0].request.get(
                env["origin"] + "/v71/orgs/" + env["org"] + "/audit/delivery")
            assert delivery.status == 200, delivery.status
            assert delivery.json()["corporate_worm_verified"] is False
            for subject in ("economist", "manager", "viewer"):
                page = contexts[subject][1]
                page.locator("#fill-sample").click()
                page.locator("#create-evidence").click()
                expect(page.locator("#notice")).to_contain_text("403")

            # V8.8 must also respect real PostgreSQL tenant and OIDC-cookie RBAC.
            # Read-only screening must NOT write to a financial or industrial ledger.
            screen = env["origin"] + "/v88/orgs/" + env["org"] + "/regional-energy/evaluate"
            case = synthetic_region_v88(150)
            def regional_screen(subject, endpoint=screen):
                context = contexts[subject][0]
                csrf = {x["name"]: x["value"] for x in context.cookies()}["hk_lab_csrf"]
                return context.request.post(
                    endpoint, data=json.dumps(case), headers={
                        "Content-Type": "application/json",
                        "Origin": env["origin"], "X-CSRF-Token": csrf,
                    },
                )
            engineer_screen = regional_screen("engineer")
            auditor_screen = regional_screen("auditor")
            assert engineer_screen.status == 200, engineer_screen.text()[:300]
            assert auditor_screen.status == 200, auditor_screen.text()[:300]
            assert engineer_screen.json() == auditor_screen.json()
            report = engineer_screen.json()["report"]
            proof = engineer_screen.json()["proof"]
            assert proof["stateful_record_saved"] is False
            assert proof["financial_ledger_updated"] is False
            assert proof["dispatch_recommendation"] is None
            assert report["investment_decision"] == "HOLD"
            assert report["financial_ledger_eligible"] is False
            assert report["production_dispatch_eligible"] is False
            assert len(report["scenarios"]) == 3
            assert not report["synthetic_all_scenarios_adequate"]
            for restricted in ("economist", "manager", "viewer"):
                assert regional_screen(restricted).status == 403
            assert regional_screen("other").status == 404
            assert contexts["engineer"][0].request.post(
                screen, data=json.dumps(case), headers={"Content-Type": "application/json"}
            ).status == 403
            engineer.locator("#v88-load-mw").select_option("150")
            engineer.locator("#v88-sample").click()
            engineer.locator("#v88-run").click()
            expect(engineer.locator("#v88-scenario-rows tr")).to_have_count(3)
            expect(engineer.locator("#v88-decision")).to_have_text("HOLD")

            # Revocation of one browser session must not revoke another role's cookies.
            engineer.locator("#logout").click()
            expect(engineer.locator("#auth-card")).to_be_visible()
            assert contexts["engineer"][0].request.get(env["origin"] + "/v7/me").status == 401
            assert contexts["auditor"][0].request.get(env["origin"] + "/v7/me").status == 200
        finally:
            for context, _ in contexts.values():
                context.close()
            browser.close()


def test_v87_mfa_claim_policy_enforced_and_no_auto_provision(unified):
    env = unified
    with sync_playwright() as p:
        opts = {"headless": True, "args": ["--no-proxy-server"]}
        if os.environ.get("HYDRO_BROWSER_EXECUTABLE"):
            opts["executable_path"] = os.environ["HYDRO_BROWSER_EXECUTABLE"]
        browser = p.chromium.launch(**opts)
        try:
            for subject in ("weak", "unprovisioned"):
                context = browser.new_context()
                page = context.new_page()
                page.goto(env["issuer"] + "/choose?sub=" + subject)
                result = page.goto(env["origin"] + "/v71/auth/start", wait_until="load")
                assert result.status == 401, (subject, result.status)
                assert context.request.get(env["origin"] + "/v7/me").status == 401
                context.close()
        finally:
            browser.close()
