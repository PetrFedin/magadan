"""Explicit opt-in local demo seed. Prints randomly generated passwords once.
Never run against real user databases or energy-company systems.
"""
import os,sys,secrets
from sqlalchemy import select
from .storage import setup_engine,Organization,User,Membership,Asset
from .main import HASHER

def main():
    if os.environ.get('HYDRO_ALLOW_DEMO_SEED')!='YES':
        print('Refusing: HYDRO_ALLOW_DEMO_SEED=YES required',file=sys.stderr);return 2
    url=os.environ.get('HYDRO_DATABASE_URL','sqlite:///./hydro_v7_lab.db')
    if not url.startswith('sqlite'):
        print('Refusing: demo seed only supports local SQLite',file=sys.stderr);return 2
    engine,Factory=setup_engine(url)
    with Factory() as db:
        if db.scalar(select(Organization.id).limit(1)):
            print('Refusing: the database is not empty',file=sys.stderr);return 2
        org='magadan-synthetic-lab'
        db.add(Organization(id=org,name='Magadan synthetic electrical feeder: NOT a field installation'))
        db.flush()
        db.add(Asset(id='synthetic-feeder-a',org_id=org,name='Synthetic reference 20 kV two-bus feeder',classification='LAB_REFERENCE'))
        print('Generated credentials for local demonstration (not written to a file):')
        for role,name in [('engineer','engineer1'),('engineer','engineer2'),('economist','finance'),('manager','manager'),
                           ('auditor','auditor1'),('auditor','auditor2'),('viewer','viewer')]:
            email=name+'@hydrokontur-lab.invalid';password=secrets.token_urlsafe(25)
            u=User(email=email,password_hash=HASHER.hash(password));db.add(u);db.flush()
            db.add(Membership(org_id=org,user_id=u.id,role=role))
            print(f'{role:10s}  {email:39s}  {password}')
        db.commit()
    print('Keep credentials private. Startup: uvicorn hydro_api.asgi:app --host 127.0.0.1 --port 8000')
    return 0

if __name__=='__main__':raise SystemExit(main())
