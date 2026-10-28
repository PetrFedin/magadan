#!/usr/bin/env python3
"""Launch an isolated receiver or deliver one PostgreSQL outbox entry.
Secrets MUST be mounted files outside this repository. No default credentials.
S3-compatible configuration is a deployment contract, not verified WORM status.
"""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from sqlalchemy import create_engine
from hydro_api.audit_delivery import LocalReceiptStore,S3ComplianceStore,ReceiptSigner,AuditExporter,create_audit_receiver

def secret(name):
    path=Path(os.environ[name]);return path.read_text().strip()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['receiver','export-once'])
    parser.add_argument('--mode',choices=['lab','compliance'],default='compliance')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8091)
    args=parser.parse_args();transport=secret('HYDRO_AUDIT_TRANSPORT_SECRET_FILE')
    if args.action=='receiver':
        import uvicorn
        key=serialization.load_pem_private_key(Path(os.environ['HYDRO_AUDIT_SIGNING_KEY_FILE']).read_bytes(),password=None)
        if not isinstance(key,Ed25519PrivateKey):raise SystemExit('Ed25519 receiver key required')
        mac=bytes.fromhex(secret('HYDRO_AUDIT_DATABASE_MAC_FILE'))
        if args.mode=='lab':
            if args.host!='127.0.0.1':raise SystemExit('Lab receiver must bind loopback')
            store=LocalReceiptStore(Path(os.environ['HYDRO_AUDIT_LAB_DIR']))
        else:
            import boto3
            endpoint=os.environ['HYDRO_APPROVED_S3_ENDPOINT']
            if not endpoint.startswith('https://'):raise SystemExit('Approved HTTPS endpoint required')
            store=S3ComplianceStore(boto3.client('s3',endpoint_url=endpoint),os.environ['HYDRO_AUDIT_BUCKET'])
            store.validate_configuration()
        app=create_audit_receiver(store,ReceiptSigner(key,database_receipt_key=mac),transport,
                                  retention_days=int(os.environ.get('HYDRO_AUDIT_RETENTION_DAYS','30')))
        uvicorn.run(app,host=args.host,port=args.port,access_log=False,loop='asyncio',ws='none')
    else:
        public=serialization.load_pem_public_key(Path(os.environ['HYDRO_AUDIT_PUBLIC_KEY_FILE']).read_bytes())
        if not isinstance(public,Ed25519PublicKey):raise SystemExit('Pinned Ed25519 public key required')
        engine=create_engine(os.environ['HYDRO_EXPORT_DATABASE_URL'],pool_pre_ping=True)
        exporter=AuditExporter(engine,os.environ['HYDRO_AUDIT_RECEIVER_URL'],transport,public,
                              require_compliance=args.mode=='compliance',allow_loopback_http=args.mode=='lab')
        try:print(json.dumps(exporter.run_once()))
        finally:exporter.http.close();engine.dispose()

if __name__=='__main__':main()
