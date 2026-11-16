from pathlib import Path
import sys, math, zipfile, tempfile, shutil, re
import xml.etree.ElementTree as ET
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
sys.path.insert(0,'/mnt/data/hydro_v6')
from build_spec_data import REQS,DATA,API,RACI,PILOTS,SOURCES
root=Path('/mnt/data')
source=next(root.glob('*_V5.xlsx'))
out=source.with_name(source.name.replace('_V5.xlsx','_V6.xlsx'))
wb=openpyxl.load_workbook(source)
navy='17324A';slate='486174';teal='0F6A75';purple='735296';pale='EAF2F6';white='FFFFFF';orange='AE6B1B';grey='687987';blue='0000FF';green='008000'
fill_head=PatternFill('solid',fgColor=navy)
fill_info=PatternFill('solid',fgColor=pale)
fill_attention=PatternFill('solid',fgColor='FFF0D5')
fill_input=PatternFill('solid',fgColor='FFFADE')
fmt='#,##0.00;[Red](#,##0.00);-'

def tab(name,title,subtitle,headers,rows,widths):
  w=wb.create_sheet(name)
  w.sheet_view.showGridLines=False
  n=len(headers);w.merge_cells(start_row=1,start_column=1,end_row=1,end_column=n)
  w.cell(1,1,title);w.cell(1,1).font=Font(name='Aptos Display',size=16,bold=True,color=white);w.cell(1,1).fill=fill_head;w.cell(1,1).alignment=Alignment(vertical='center');w.row_dimensions[1].height=31
  w.merge_cells(start_row=2,start_column=1,end_row=2,end_column=n)
  w.cell(2,1,subtitle);w.cell(2,1).font=Font(size=10,italic=True,color=slate);w.row_dimensions[2].height=28
  for j,c in enumerate(headers,1):
    cc=w.cell(4,j,c);cc.fill=fill_head;cc.font=Font(size=10,bold=True,color=white);cc.alignment=Alignment(wrap_text=True,vertical='center')
  w.row_dimensions[4].height=33
  for i,row in enumerate(rows,5):
    for j,v in enumerate(row,1):
      c=w.cell(i,j,v);c.font=Font(name='Aptos',size=9,color='222222');c.alignment=Alignment(wrap_text=True,vertical='top')
      if i%2==1:c.fill=fill_info
    w.row_dimensions[i].height=50 if n>=6 else 36
  for i,width in enumerate(widths,1):w.column_dimensions[get_column_letter(i)].width=width
  w.freeze_panes='D5' if n>=6 else 'B5'
  w.auto_filter.ref=f'A4:{get_column_letter(n)}{4+len(rows)}'
  w.sheet_properties.tabColor=teal
  return w

reqs=[(r['id'],r['module'],r['priority'],r['feature'],r['inputs'],r['rule'],r['acceptance'],r['owner'],r['status'],r['pilotScope']) for r in REQS]
tab('V6_REQ','V6 | ENGINEERING REQUIREMENTS','108 PROPOSED controls; stage approval and site baselines are NOT yet confirmed.',
  ['ID','Module','Priority','Feature','Required data','Hard rule or design intent','Acceptance check','Owner candidate','Status','Pilot context'],reqs,[13,25,12,35,44,55,55,20,18,22])
for row in wb['V6_REQ'].iter_rows(min_row=5,max_row=4+len(reqs)):
  pr=row[2];pr.font=Font(bold=True,color='C65A20' if pr.value=='P0' else purple if pr.value=='P1' else grey)
  row[8].font=Font(color=orange,italic=True,size=9)

rows=[(x[0],x[1],x[2],x[3],x[4],x[5],x[6]) for x in DATA]
tab('V6_DICTIONARY','V6 | CANONICAL DATA DICTIONARY','Owner classification and retention subject to contracts and security assessment.',
  ['Field','Type','Unit','Semantic meaning','Classification proposal','Authoritative source candidate','Missing-data policy'],rows,[28,20,29,60,24,27,25])
rows=[(x[0],x[1],x[2],x[3],x[4]) for x in API]
tab('V6_API','V6 | API DESIGN CONTRACT','Contracts proposed; no server endpoints implemented in V6 demo.',
  ['Method','Endpoint','Input / authorization','Response','Negative acceptance test'],rows,[12,52,67,55,55])
rows=[(i+1,*p) for i,p in enumerate(PILOTS)]
tab('V6_MAGADAN_PILOTS','V6 | MAGADAN PILOT CANDIDATES','The listed facilities and operators are candidates only: no corporate access or pilot approvals confirmed.',
  ['No.','Module','Candidate asset / perimeter','Potential data owner','Minimal evidence / dataset','Proof criterion','Main blocker'],rows,[7,24,42,48,63,63,55])
rows=[(i+1,*x) for i,x in enumerate(RACI)]
tab('V6_RACI','V6 | PROPOSED RESPONSIBILITY MATRIX','All roles must be reconciled with actual delegation of authority of each legal entity.',
  ['No.','Workstream','Responsible','Accountable / decision owner','Consulted','Informed'],rows,[7,44,40,40,40,40])
rows=[(k,v,'OFFICIAL_REFERENCE','Use as comparative or design context; no claim of product parity') for k,v in SOURCES.items()]
tab('V6_REFERENCES','V6 | SOURCE REGISTRY','Clickable URLs for official engineering and project-controls materials.',
  ['Code','Official source URL','Evidence class','Limitation'],rows,[24,90,25,84])
for row in wb['V6_REFERENCES'].iter_rows(min_row=5):
 c=row[1];c.hyperlink=c.value;c.font=Font(color='0563C1',underline='single',size=9)

def demo():
 w=wb.create_sheet('V6_FIN_DEMO');w.sheet_view.showGridLines=False;w.sheet_properties.tabColor='D28E30';w.column_dimensions['A'].width=45;w.column_dimensions['B'].width=28;w.column_dimensions['C'].width=55
 w.merge_cells('A1:C1');w['A1']='V6 | SYNTHETIC PILOT ECONOMICS';w['A1'].fill=fill_head;w['A1'].font=Font(color=white,bold=True,size=16);w.row_dimensions[1].height=33
 w.merge_cells('A2:C2');w['A2']='Demonstration inputs only. Not an approved estimate and not Magadanenergo or RusHydro operating data.';w['A2'].font=Font(color=orange,italic=True,size=10);w.row_dimensions[2].height=28
 w['A5']='Adjustable inputs';w['A5'].font=Font(bold=True,color=navy,size=12)
 rows=[(7,'Annual avoided losses','MWh/year',2400),(8,'Economic energy unit cost','RUB/kWh',4),(9,'Other supported annual saving','million RUB/year',1.1),(10,'Incremental operating cost','million RUB/year',1.5),(11,'Initial capital cost','million RUB',28),(12,'Discount rate','fraction',0.12),(13,'Evaluation horizon','years',8)]
 for ri,label,unit,value in rows:
  w.cell(ri,1,label);w.cell(ri,2,value);w.cell(ri,3,unit);w.cell(ri,2).font=Font(color=blue,bold=True);w.cell(ri,2).fill=fill_input;w.cell(ri,2).comment=Comment('SYNTHETIC / INTERNAL ASSUMPTION. Replace only with signed engineering and finance data.','Design team')
 for ri,label,formula in [(16,'Annual energy saving (million RUB)','=B7*B8/1000'),(17,'Net annual cash flow (million RUB)','=B16+B9-B10'),(18,'Discount annuity factor','=IF(B12=0,B13,(1-(1+B12)^(-B13))/B12)'),(19,'Illustrative NPV (million RUB)','= -B11+B17*B18'),(20,'Simple payback (years)','=IF(B17<=0,"NO_PAYBACK",B11/B17)')]:
  w.cell(ri,1,label);w.cell(ri,2,formula);w.cell(ri,2).font=Font(color='000000',bold=True);w.cell(ri,2).fill=fill_info
 w['A23']='Independent example: -28 + (2400*4/1000 + 1.1 - 1.5) * (1-1.12^(-8)) / .12';w.merge_cells('A23:C23');w['A23'].font=Font(italic=True,color=grey,size=9)
 w['A25']='Decision rule';w['B25']='Engineering and legal obligations take precedence over financial ranking.';w.merge_cells('B25:C25')
 for row in w.iter_rows():
  for c in row:
   if c.coordinate not in ['A1','A2'] and c.value is not None:c.alignment=Alignment(wrap_text=True,vertical='center')
 for r in range(1,27):w.row_dimensions[r].height=25
 w['B12'].number_format='0.0%'
 for ri in list(range(7,12))+[16,17,19,20]:w.cell(ri,2).number_format=fmt
 w.freeze_panes='B7'
 dv=DataValidation(type='decimal',operator='between',formula1='0',formula2='1',allow_blank=False);dv.error='Discount rate must be in [0,1]';dv.errorTitle='Invalid rate';dv.showErrorMessage=True;w.add_data_validation(dv);dv.add(w['B12'])
 return w

demo()
idx=wb.create_sheet('V6_INDEX',0);idx.sheet_view.showGridLines=False;idx.sheet_properties.tabColor=navy
idx.merge_cells('A1:E1');idx['A1']='HYDROKONTUR 360 | V6 DELIVERY CONTROL';idx['A1'].fill=fill_head;idx['A1'].font=Font(color=white,bold=True,size=16);idx.row_dimensions[1].height=33
idx.merge_cells('A2:E2');idx['A2']='Working requirements, not completed industrial engineering. Dates and cost inputs are hypotheses unless sourced.';idx['A2'].font=Font(italic=True,color=orange)
summary=[('New engineering requirements','=COUNTA(V6_REQ!A5:A112)'),('P0 requirements','=COUNTIF(V6_REQ!C5:C112,"P0")'),('P1 requirements','=COUNTIF(V6_REQ!C5:C112,"P1")'),('P2 requirements','=COUNTIF(V6_REQ!C5:C112,"P2")'),('Dictionary fields','=COUNTA(V6_DICTIONARY!A5:A52)'),('Proposed API contracts','=COUNTA(V6_API!B5:B19)'),('Magadan pilot candidates','=COUNTA(V6_MAGADAN_PILOTS!B5:B10)'),('Reference links','=COUNTA(V6_REFERENCES!A5:A12)')]
for r,(title,formula) in enumerate(summary,5):
 idx.cell(r,1,title);idx.cell(r,2,formula);idx.cell(r,2).font=Font(color=green,bold=True)
idx.merge_cells('A15:E15');idx['A15']='P0 DATA ACCESS HOLD: industrial pilot requires legally obtained object data, engineering reference, independent review and owner authorization.';idx['A15'].font=Font(color=orange,bold=True);idx['A15'].fill=fill_attention
idx['A17']='Navigation';idx['A17'].font=Font(bold=True,size=12,color=navy)
for r,sheetname in enumerate(['V6_REQ','V6_DICTIONARY','V6_API','V6_MAGADAN_PILOTS','V6_RACI','V6_FIN_DEMO','V6_REFERENCES'],18):
 c=idx.cell(r,1,sheetname);c.hyperlink=f"#'{sheetname}'!A1";c.font=Font(color='0563C1',underline='single')
idx.column_dimensions['A'].width=48;idx.column_dimensions['B'].width=20
for c in ['C','D','E']:idx.column_dimensions[c].width=18
for r in range(1,27):idx.row_dimensions[r].height=25
wb.calculation=openpyxl.workbook.properties.CalcProperties(calcMode='auto',fullCalcOnLoad=True,forceFullCalc=True)
wb.save(out)

# Restore cached results from existing 21 V5 sheets without recalculating their formulas.
# Cache data only for formulas that are textually identical in the source and output.
ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
q='{'+ns['x']+'}'
old_cache={}
with zipfile.ZipFile(source) as zin:
 for i in range(1,22):
  f=f'xl/worksheets/sheet{i}.xml'
  tree=ET.fromstring(zin.read(f)); entries={}
  for cell in tree.findall('.//x:c',ns):
   form=cell.find('x:f',ns);value=cell.find('x:v',ns)
   if form is not None and value is not None and value.text is not None:
    entries[cell.get('r')]=(form.text or '',value.text,cell.get('t'))
  old_cache[f]=entries
new_cache={'B16':2400*4/1000,'B17':2400*4/1000+1.1-1.5}
new_cache['B18']=(1-(1+0.12)**(-8))/0.12
new_cache['B19']=-28+new_cache['B17']*new_cache['B18']
new_cache['B20']=28/new_cache['B17']
new_idx={'B5':len(REQS),'B6':sum(r['priority']=='P0' for r in REQS),'B7':sum(r['priority']=='P1' for r in REQS),'B8':sum(r['priority']=='P2' for r in REQS),'B9':len(DATA),'B10':len(API),'B11':len(PILOTS),'B12':len(SOURCES)}
oldcount=0;newcount=0
work=Path(tempfile.mktemp(suffix='.xlsx'))
with zipfile.ZipFile(out) as zin,zipfile.ZipFile(work,'w') as zout:
 for info in zin.infolist():
  raw=zin.read(info.filename)
  is_sheet=info.filename.startswith('xl/worksheets/sheet') and info.filename.endswith('.xml')
  if is_sheet:
   m=re.search(r'sheet(\d+)\.xml$',info.filename)
   j=int(m.group(1)) if m else 0
   if j==1: target=new_idx
   elif j==len(wb.sheetnames): target=new_cache
   else:target={}
   tree=ET.fromstring(raw)
   for cell in tree.findall('.//x:c',ns):
    form=cell.find('x:f',ns)
    if form is None:continue
    coord=cell.get('r')
    v=cell.find('x:v',ns)
    if v is None:v=ET.SubElement(cell,q+'v')
    if coord in target:
     v.text=str(target[coord]);newcount+=1
    elif 2<=j<=22:
     old=old_cache.get(f'xl/worksheets/sheet{j-1}.xml',{}).get(coord)
     if old and (form.text or '')==old[0]:v.text=old[1];oldcount+=1
   raw=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
  zout.writestr(info,raw)
shutil.move(work,out)
print('EXPORTED',out,'SHEETS',len(wb.sheetnames),'OLD_FORMULA_CACHES',oldcount,'NEW_CACHES',newcount)
print('SYNTHETIC_MODEL_NPV',round(new_cache['B19'],6))
