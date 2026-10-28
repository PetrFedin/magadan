import copy
import json
import socket
import threading
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
import httpx
import uvicorn
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hydro_api.audit_delivery import (AuditError,Envelope,LocalReceiptStore,ReceiptSigner,
    S3ComplianceStore,create_audit_receiver,verify_receipt,canonical,AuditExporter)

SECRET='isolated-audit-transport-secret-tests-only-0123456789'

def event(seq=1,**changes):
    return Envelope(event_id=f'event-{seq}',org_id='magadan-synthetic-lab',seq=seq,event_hash=str(seq)*64,
        previous_hash='GENESIS' if seq==1 else str(seq-1)*64,actor_id='engineer-synthetic',
        event_type='calculation.completed',object_type='run',object_id='run-lab',payload={'classification':'SYNTHETIC'},
        timestamp_ms=int(time.time()*1000),**changes).model_dump(mode='json')

@pytest.fixture
def receiver(tmp_path):
    key=Ed25519PrivateKey.generate();store=LocalReceiptStore(tmp_path/'independent-audit')
    app=create_audit_receiver(store,ReceiptSigner(key),SECRET)
    client=TestClient(app)
    yield client,key,store,app
    client.close()


def send(client,data):return client.post('/v1/events',headers={'Authorization':'Bearer '+SECRET},json=data)


def test_receipt_is_signed_bound_and_persistent(receiver):
    c,key,store,app=receiver;data=event()
    r=send(c,data);assert r.status_code==200
    body=verify_receipt(r.json(),key.public_key(),data,require_compliance=False)
    assert body['retention_mode']=='LAB_FILE'
    assert json.loads((store.directory/body['object_key']).read_text())['envelope']==data
    assert send(c,data).json()==r.json()


def test_receipt_signature_alteration_rejected(receiver):
    c,key,_,_=receiver;data=event();signed=send(c,data).json()
    signed['receipt']['retention_mode']='COMPLIANCE'
    with pytest.raises(AuditError):verify_receipt(signed,key.public_key(),data,require_compliance=True)


def test_lab_receipt_cannot_pass_production_worm_gate(receiver):
    c,key,_,_=receiver;data=event();signed=send(c,data).json()
    with pytest.raises(AuditError,match='WORM_REQUIRED'):verify_receipt(signed,key.public_key(),data,require_compliance=True)


def test_wrong_key_or_body_rejected(receiver):
    c,key,_,_=receiver;data=event();signed=send(c,data).json()
    with pytest.raises(AuditError):verify_receipt(signed,Ed25519PrivateKey.generate().public_key(),data,require_compliance=False)
    altered=copy.deepcopy(data);altered['payload']['classification']='REAL'
    with pytest.raises(AuditError):verify_receipt(signed,key.public_key(),altered,require_compliance=False)


def test_out_of_order_and_conflicting_event_rejected(receiver):
    c,key,_,_=receiver
    assert send(c,event(2)).status_code==409
    data=event();assert send(c,data).status_code==200
    assert send(c,event(2)).status_code==200
    altered=copy.deepcopy(data);altered['payload']['changed']=True
    assert send(c,altered).status_code==409
    assert c.post('/v1/events',json=event()).status_code==401


def test_receiver_restart_keeps_same_receipt(receiver):
    c,key,store,_=receiver;data=event();first=send(c,data).json()
    new=TestClient(create_audit_receiver(LocalReceiptStore(store.directory),ReceiptSigner(key),SECRET))
    assert send(new,data).json()==first


def test_no_delete_or_replace_http_routes(receiver):
    c,_,_,_=receiver
    assert c.delete('/v1/events/event-1').status_code in (404,405)
    assert c.put('/v1/events/event-1',json={}).status_code in (404,405)


def test_real_loopback_http_delivery(receiver):
    # An actual HTTP socket test; still a local filesystem, not corporate WORM.
    _,key,_,app=receiver
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,loop='asyncio',ws='none'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.02)
        assert server.started
        exporter=AuditExporter(None,f'http://127.0.0.1:{port}',SECRET,key.public_key(),require_compliance=False,allow_loopback_http=True)
        data=event();signed=exporter.deliver(data)
        assert signed['receipt']['event_id']==data['event_id']
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
        if "exporter" in locals():exporter.http.close()


class ContractS3:
    """SDK contract fake, explicitly NOT a live object-store/WORM test."""
    def __init__(self,versioning=True,lock=True,proof=True):self.versioning=versioning;self.lock=lock;self.proof=proof;self.put=None
    def get_bucket_versioning(self,**kw):return {'Status':'Enabled' if self.versioning else 'Suspended'}
    def get_object_lock_configuration(self,**kw):return {'ObjectLockConfiguration':{'ObjectLockEnabled':'Enabled' if self.lock else ''}}
    def put_object(self,**kw):self.put=kw;return {'VersionId':'pinned-version-1'}
    def head_object(self,**kw):
        assert kw['VersionId']=='pinned-version-1'
        return {'ObjectLockMode':'COMPLIANCE' if self.proof else 'GOVERNANCE','ObjectLockRetainUntilDate':datetime.now(timezone.utc)+timedelta(days=40)}

@pytest.mark.parametrize('flags',[(False,True,True),(True,False,True),(True,True,False)])
def test_s3_contract_rejects_missing_protection(flags):
    with pytest.raises(AuditError):S3ComplianceStore(ContractS3(*flags),'approved-test-bucket').store(event(),datetime.now(timezone.utc)+timedelta(days=30))


def test_s3_adapter_pins_version_and_requests_compliance():
    c=ContractS3();key,version,_=S3ComplianceStore(c,'approved-test-bucket').store(event(),datetime.now(timezone.utc)+timedelta(days=30))
    assert c.put['IfNoneMatch']=='*' and c.put['ObjectLockMode']=='COMPLIANCE'
    assert version=='pinned-version-1'
    assert c.put['ChecksumSHA256']


def test_receiver_mac_attestation_binds_exact_receipt_bytes():
    import base64,hashlib,hmac
    key=Ed25519PrivateKey.generate();mac_key=b'different-database-secret-32-bytes-minimum'
    signed=ReceiptSigner(key,database_receipt_key=mac_key).sign({'value':'lab-only'})
    raw=base64.b64decode(signed['db_attestation']['payload_b64'],validate=True)
    assert json.loads(raw)==signed['receipt']
    assert hmac.compare_digest(signed['db_attestation']['mac'],hmac.new(mac_key,raw,hashlib.sha256).hexdigest())
    wrong=hmac.new(mac_key,raw+b' ',hashlib.sha256).hexdigest()
    assert wrong!=signed['db_attestation']['mac']


def test_large_supported_receipt_is_not_rejected_by_transport(receiver):
    c,key,_,_=receiver;data=event();data['payload']['sample']='x'*90000
    exporter=AuditExporter(None,'http://testserver',SECRET,key.public_key(),require_compliance=False,client=c,allow_loopback_http=True)
    assert exporter.deliver(data)['receipt']['sealed_event']==data


def test_oversized_event_rejected(receiver):
    c,_,_,_=receiver;data=event();data['payload']['sample']='x'*270000
    assert send(c,data).status_code==413
