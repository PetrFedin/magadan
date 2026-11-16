from pathlib import Path
p=Path('/mnt/data/hydro_v6/build_standalone.py')
s=p.read_text()
s=s.replace("app='\\n'.join(line for line in app.splitlines() if not line.startswith('import {MODULES'))", "assurance=(r/'src/assurance.mjs').read_text('utf-8').replace('export function ','function ')\napp='\\n'.join(line for line in app.splitlines() if not line.startswith('import {'))")
s=s.replace("'+core+'\\n'+app+'", "'+core+'\\n'+assurance+'\\n'+app+'")
s=s.replace("export=Path('/mnt/data/", "export=Path('/mnt/data/")
s=s.replace('_V5.html', '_V6.html')
p.write_text(s)
root=Path('/mnt/data')
for f in root.glob('*_V5.html'):
 if 'hydrokontur-v6-lab-state' in f.read_text(encoding='utf-8'):
  f.write_text(Path('/mnt/data/hydro_v5/dist/standalone.html').read_text(encoding='utf-8'),encoding='utf-8')
  print('RESTORED original:',f)
