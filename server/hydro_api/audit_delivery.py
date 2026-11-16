"""Transactional-outbox transport with pinned Ed25519 receipt verification.
LAB_FILE storage is deliberately NOT described as WORM. S3 COMPLIANCE adapter
requires bucket versioning, retention readback and a pinned object version.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


MAX_ENVELOPE_BYTES = 262144
MAX_RECEIPT_BYTES = 1048576


class AuditError(ValueError):
    pass


class Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['hk-audit-v1'] = 'hk-audit-v1'
    event_id: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    org_id: str = Field(min_length=1,max_length=100)
    seq: int = Field(ge=1)
    event_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    previous_hash: str = Field(pattern=r'^(GENESIS|[0-9a-f]{64})$')
    actor_id: str = Field(min_length=1,max_length=100)
    event_type: str = Field(min_length=1,max_length=100)
    object_type: str = Field(min_length=1,max_length=100)
    object_id: str = Field(min_length=1,max_length=100)
    payload: dict
    timestamp_ms: int = Field(gt=0)


class LocalReceiptStore:
    """Independent local process/directory only; host admin can alter files.
    Atomic publish and write-once application semantics, not physical WORM.
    """
    mode = 'LAB_FILE'

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()

    def store(self, envelope: dict, until: datetime):
        content=canonical(envelope)
        directory=self.directory/sha(envelope['org_id'].encode())
        directory.mkdir(exist_ok=True,mode=0o700)
        target=directory/(f"{envelope['seq']:012d}.json")
        record={'envelope':envelope,'retention_until':until.isoformat()}
        with self.lock:
            if target.exists():
                old=json.loads(target.read_text())
                if canonical(old['envelope'])!=content: raise AuditError('SEQUENCE_CONTENT_CONFLICT')
                return str(target.relative_to(self.directory)),sha(target.read_bytes()),old['retention_until']
            if envelope['seq']==1:
                if envelope['previous_hash']!='GENESIS':raise AuditError('BROKEN_FIRST_EVENT')
            else:
                prior=directory/(f"{envelope['seq']-1:012d}.json")
                if not prior.exists():raise AuditError('PREVIOUS_EVENT_NOT_SEALED')
                if json.loads(prior.read_text())['envelope']['event_hash']!=envelope['previous_hash']:
                    raise AuditError('PREVIOUS_HASH_MISMATCH')
            data=canonical(record)
            fd,tmp=tempfile.mkstemp(dir=directory,prefix='.pending-')
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.chmod(tmp,0o440)
                os.link(tmp,target)
                dirfd=os.open(directory,os.O_RDONLY)
                try: os.fsync(dirfd)
                finally: os.close(dirfd)
            finally:
                os.unlink(tmp)
        return str(target.relative_to(self.directory)),sha(data),until.isoformat()


class S3ComplianceStore:
    """A protocol adapter, not a declaration of domestic/corporate approval.
    Use only an approved service with independently tested Object Lock semantics.
    """
    mode='COMPLIANCE'

    def __init__(self, client, bucket: str, prefix='hydrokontur-audit-v71'):
        self.client,self.bucket,self.prefix=client,bucket,prefix.strip('/')

    def validate_configuration(self):
        c=self.client
        if c.get_bucket_versioning(Bucket=self.bucket).get('Status')!='Enabled':
            raise AuditError('VERSIONING_REQUIRED')
        config=c.get_object_lock_configuration(Bucket=self.bucket).get('ObjectLockConfiguration',{})
        if config.get('ObjectLockEnabled')!='Enabled':raise AuditError('OBJECT_LOCK_REQUIRED')

    def store(self,envelope:dict,until:datetime):
        from botocore.exceptions import ClientError
        self.validate_configuration()
        data=canonical(envelope)
        # A single stable key per organization+sequence detects competing events.
        key=f"{self.prefix}/{sha(envelope['org_id'].encode())}/{envelope['seq']:012d}.json"
        duplicate=False
        try:
            response=self.client.put_object(Bucket=self.bucket,Key=key,Body=data,
                ContentType='application/json',IfNoneMatch='*',ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode(),
                ObjectLockMode='COMPLIANCE',ObjectLockRetainUntilDate=until)
            version=response.get('VersionId')
        except ClientError as err:
            if err.response.get('ResponseMetadata',{}).get('HTTPStatusCode') not in (409,412):raise
            duplicate=True
            existing=self.client.get_object(Bucket=self.bucket,Key=key)
            if existing['Body'].read()!=data:raise AuditError('SEQUENCE_CONTENT_CONFLICT')
            version=existing.get('VersionId')
        if not version or version=='null':raise AuditError('VERSION_ID_REQUIRED')
        proof=self.client.head_object(Bucket=self.bucket,Key=key,VersionId=version)
        actual=proof.get('ObjectLockRetainUntilDate')
        minimum=datetime.now(timezone.utc)+timedelta(hours=1) if duplicate else until-timedelta(seconds=5)
        if proof.get('ObjectLockMode')!='COMPLIANCE' or not actual or actual<minimum:
            raise AuditError('RETENTION_READBACK_FAILED')
        return key,version,actual.isoformat()


class ReceiptSigner:
    def __init__(self,key:Ed25519PrivateKey, *, database_receipt_key: bytes | None = None):
        self.key=key
        self.database_receipt_key=database_receipt_key
        if database_receipt_key is not None and len(database_receipt_key)<32:
            raise AuditError('RECEIPT_MAC_KEY_TOO_SHORT')
        pub=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.key_id=sha(pub)

    def sign(self,body):
        body={**body,'key_id':self.key_id}
        result={'receipt':body,'signature':base64.b64encode(self.key.sign(canonical(body))).decode('ascii')}
        if self.database_receipt_key is not None:
            wire=canonical(body)
            result['db_attestation']={'payload_b64':base64.b64encode(wire).decode('ascii'),
                'mac':hmac.new(self.database_receipt_key,wire,'sha256').hexdigest()}
        return result


def verify_receipt(signed:dict,public_key:Ed25519PublicKey,envelope:dict,*,require_compliance:bool,min_retention_seconds:int=3600):
    try:
        r=signed['receipt']
        public_key.verify(base64.b64decode(signed['signature'],validate=True),canonical(r))
        expected_key=sha(public_key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
        if r['key_id']!=expected_key or any(r[k]!=envelope[k] for k in ('event_id','org_id','seq','event_hash')):
            raise AuditError('RECEIPT_BINDING_FAILED')
        if r.get('sealed_event')!=envelope or r['envelope_sha256']!=sha(canonical(envelope)):
            raise AuditError('RECEIPT_CONTENT_MISMATCH')
        if not r['object_key'] or not r['version_id']:raise AuditError('RECEIPT_VERSION_MISSING')
        until=datetime.fromisoformat(r['retention_until'])
        if until.tzinfo is None or until<datetime.now(timezone.utc)+timedelta(seconds=min_retention_seconds):
            raise AuditError('INSUFFICIENT_RETENTION')
        if require_compliance and r['retention_mode']!='COMPLIANCE':raise AuditError('WORM_REQUIRED')
        if r['retention_mode'] not in ('COMPLIANCE','LAB_FILE'):raise AuditError('UNKNOWN_RETENTION_MODE')
        return r
    except (KeyError,ValueError,TypeError,InvalidSignature) as exc:
        if isinstance(exc,AuditError):raise
        raise AuditError('INVALID_EXTERNAL_RECEIPT') from None


def create_audit_receiver(store,signer:ReceiptSigner,transport_secret:str,*,retention_days:int=30):
    if len(transport_secret)<32 or retention_days<1:raise AuditError('INVALID_RECEIVER_CONFIGURATION')
    app=FastAPI(title='HydroKontur independent audit receiver',version='0.7.1')

    @app.post('/v1/events')
    def receive(envelope:Envelope,authorization:str=Header(default='')):
        if not hmac.compare_digest(authorization,'Bearer '+transport_secret):raise HTTPException(401,'Authentication required')
        data=envelope.model_dump(mode='json')
        if len(canonical(data))>MAX_ENVELOPE_BYTES:raise HTTPException(413,'Audit envelope too large')
        until=datetime.now(timezone.utc)+timedelta(days=retention_days)
        try: key,version,actual=store.store(data,until)
        except AuditError as exc:raise HTTPException(409,str(exc)) from None
        return signer.sign({'event_id':data['event_id'],'org_id':data['org_id'],'seq':data['seq'],
            'event_hash':data['event_hash'],'envelope_sha256':sha(canonical(data)),'sealed_event':data,
            'object_key':key,'version_id':version,'retention_mode':store.mode,'retention_until':actual})

    @app.get('/health')
    def health():return {'mode':store.mode,'production_worm_claim':False if store.mode=='LAB_FILE' else 'requires-deployment-acceptance'}
    return app


class AuditExporter:
    def __init__(self,engine,endpoint:str,transport_secret:str,receipt_key:Ed25519PublicKey,*,
                 require_compliance=True,client:httpx.Client|None=None,allow_loopback_http=False):
        from urllib.parse import urlsplit
        u=urlsplit(endpoint)
        if u.username or u.password or u.fragment or not u.hostname:raise AuditError('INVALID_AUDIT_ENDPOINT')
        if u.scheme!='https' and not(allow_loopback_http and u.hostname in ('127.0.0.1','localhost','testserver')):
            raise AuditError('AUDIT_HTTPS_REQUIRED')
        self.engine,self.endpoint,self.secret,self.key=engine,endpoint,transport_secret,receipt_key
        self.require_compliance=require_compliance
        self.http=client or httpx.Client(timeout=8,follow_redirects=False,trust_env=False)

    def deliver(self,envelope):
        r=self.http.post(self.endpoint+'/v1/events',headers={'Authorization':'Bearer '+self.secret},json=envelope)
        if r.status_code!=200 or len(r.content)>MAX_RECEIPT_BYTES:raise AuditError('EXTERNAL_DELIVERY_REJECTED')
        signed=r.json()
        verify_receipt(signed,self.key,envelope,require_compliance=self.require_compliance)
        return signed

    def run_once(self):
        # One pending event per tenant; retries are safe after a crash between remote
        # persistence and local COMMIT. Credentials have NO delete rights on the sink.
        with self.engine.begin() as db:
            row=db.execute(text('''SELECT e.*,q.attempts FROM audit_outbox q
                JOIN audit_events e ON e.id=q.event_id
                WHERE q.delivered_at IS NULL AND q.available_at<=clock_timestamp()
                 AND NOT EXISTS(SELECT 1 FROM audit_outbox p WHERE p.org_id=q.org_id
                      AND p.seq<q.seq AND p.delivered_at IS NULL)
                ORDER BY q.org_id,q.seq FOR UPDATE OF q SKIP LOCKED LIMIT 1''')).mappings().first()
            if not row:return {'status':'idle'}
            envelope=Envelope(event_id=row['id'],**{k:row[k] for k in ('org_id','seq','event_hash','previous_hash','actor_id','event_type','object_type','object_id','payload','timestamp_ms')}).model_dump(mode='json')
            try:signed=self.deliver(envelope)
            except (AuditError,httpx.HTTPError,ValueError):
                delay=min(3600,2**min(row['attempts']+1,11))
                db.execute(text("UPDATE audit_outbox SET attempts=attempts+1,last_error_code='DELIVERY_OR_RECEIPT_FAILED',available_at=clock_timestamp()+make_interval(secs=>:delay) WHERE event_id=:id"),{'id':row['id'],'delay':delay})
                return {'status':'retry','event_id':row['id']}
            db.execute(text('''INSERT INTO audit_receipts(event_id,org_id,event_hash,envelope_sha256,receipt)
                VALUES(:id,:org,:hash,:bodyhash,CAST(:receipt AS jsonb)) ON CONFLICT(event_id) DO NOTHING'''),
                {'id':row['id'],'org':row['org_id'],'hash':row['event_hash'],
                 'bodyhash':sha(canonical(envelope)),'receipt':canonical(signed).decode()})
            db.execute(text('UPDATE audit_outbox SET delivered_at=clock_timestamp(),last_error_code=NULL WHERE event_id=:id'),{'id':row['id']})
            return {'status':'delivered','event_id':row['id']}
