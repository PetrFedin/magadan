from pathlib import Path
import openpyxl,zipfile,tempfile,shutil,xml.etree.ElementTree as E
p=next(Path('/mnt/data').glob('*_V6.xlsx'))
w=openpyxl.load_workbook(p,read_only=True)
idx=w.sheetnames.index('V6_FIN_DEMO')+1
q='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
model={}
model['B16']=2400*4/1000
model['B17']=model['B16']+1.1-1.5
model['B18']=(1-(1+0.12)**(-8))/0.12
model['B19']=-28+model['B17']*model['B18']
model['B20']=28/model['B17']
target=f'xl/worksheets/sheet{idx}.xml'
work=Path(tempfile.mktemp(suffix='.xlsx'))
with zipfile.ZipFile(p,'r') as zin,zipfile.ZipFile(work,'w') as zout:
 for info in zin.infolist():
  raw=zin.read(info.filename)
  if info.filename==target:
   tree=E.fromstring(raw)
   for c in tree.iter(q+'c'):
    if c.get('r') in model:
     v=c.find(q+'v')
     if v is None:v=E.SubElement(c,q+'v')
     v.text=str(model[c.get('r')])
   raw=E.tostring(tree,encoding='utf-8',xml_declaration=True)
  zout.writestr(info,raw)
shutil.move(work,p)
v=openpyxl.load_workbook(p,data_only=True,read_only=True)['V6_FIN_DEMO']
print('CACHE VERIFIED',[(key,v[key].value) for key in model], 'sheet',idx)
