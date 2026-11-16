from pathlib import Path
from tempfile import NamedTemporaryFile
import zipfile,os,math
from lxml import etree
import numpy as np
from openpyxl import load_workbook
import formulas
P=next(Path('/mnt/data').glob('*_V6.xlsx'))
w=load_workbook(P)
model=formulas.ExcelModel().loads(str(P)).finish()
sol=model.calculate()
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ns_url=ns['m']
allcaches={}
unknown=[]
for idx,ws in enumerate(w.worksheets,1):
 cmap={}
 for row in ws:
  for cell in row:
   if cell.data_type!='f':continue
   k=f"'[{P.name}]{ws.title.upper()}'!{cell.coordinate}"
   if k not in sol:
    unknown.append((ws.title,cell.coordinate,'missing key'));continue
   x=sol[k]
   try:v=x.value if hasattr(x,'value') else x
   except Exception:v=x
   if hasattr(v,'shape'):
    try:v=v.reshape(-1)[0]
    except Exception:unknown.append((ws.title,cell.coordinate,'shape'));continue
   if v is None:continue
   if isinstance(v,(int,float,np.number)):
    if not math.isfinite(float(v)):
     unknown.append((ws.title,cell.coordinate,str(v)));continue
    v=float(v)
   elif isinstance(v,(str,np.str_)):
    v=str(v)
    if v.startswith('#'):unknown.append((ws.title,cell.coordinate,v));continue
   elif isinstance(v,(bool,np.bool_)):v=bool(v)
   else:unknown.append((ws.title,cell.coordinate,type(v).__name__));continue
   cmap[cell.coordinate]=v
 allcaches[f'xl/worksheets/sheet{idx}.xml']=cmap
count=0
temp=P.with_name('tmp_recalc_v6.xlsx')
with zipfile.ZipFile(P,'r') as zi,zipfile.ZipFile(temp,'w') as zo:
 for item in zi.infolist():
  content=zi.read(item.filename)
  if item.filename in allcaches and allcaches[item.filename]:
   root=etree.fromstring(content)
   for c in root.xpath('//m:c[m:f]',namespaces=ns):
    ref=c.get('r')
    if ref not in allcaches[item.filename]:continue
    val=allcaches[item.filename][ref]
    old=c.find(f'{{{ns_url}}}v')
    if old is None:old=etree.SubElement(c,f'{{{ns_url}}}v')
    if isinstance(val,str):c.set('t','str');old.text=val
    elif isinstance(val,bool):c.set('t','b');old.text='1' if val else '0'
    else:
     if c.get('t')=='str':c.attrib.pop('t')
     old.text=str(val)
    count+=1
   content=etree.tostring(root,encoding='UTF-8')
  zo.writestr(item,content)
os.replace(temp,P)
print('CACHED',count,'FORMULA TOTAL',sum(c.data_type=='f' for s in w for row in s for c in row),'UNKNOWN',len(unknown))
print('UNKNOWN_EXAMPLES',unknown[:15])
c=load_workbook(P,data_only=True)
for sheet,cell in [('V6_INDEX','B5'),('V6_INDEX','B6'),('V6_FIN_DEMO','B19'),(c.worksheets[11].title,'C16')]:
 print('CHECK',sheet,cell,c[sheet][cell].value)
assert c['V6_INDEX']['B5'].value==108
assert c['V6_INDEX']['B6'].value==56
assert abs(c['V6_FIN_DEMO']['B19'].value-17.70228585491504)<1e-8
assert abs(c.worksheets[11]['C16'].value-17.70228585491504)<1e-8
assert abs(c.worksheets[11]['B16'].value-(-15.084136606219662))<1e-8
assert abs(c.worksheets[11]['D16'].value-39.037248665791864)<1e-8
print('V6 FINANCIAL MODEL QA PASS')
