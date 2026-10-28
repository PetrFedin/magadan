from pathlib import Path
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.section import WD_SECTION_START
import sys,datetime,collections
sys.path.insert(0,'/mnt/data/hydro_v6')
from build_spec_data import REQS,DATA,API,RACI,PILOTS,SOURCES
root=Path('/mnt/data')
base=Document(next(root.glob('*_V4.docx')))
ru_title=base.paragraphs[0].text
ru_note=base.paragraphs[4].text
ru_region=base.paragraphs[5].text
out=root/'HydroKontur_360_Magadan_V6_Engineering_Specification.docx'
doc=Document()
sec=doc.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11)
sec.top_margin=Inches(.73);sec.bottom_margin=Inches(.65);sec.left_margin=Inches(.75);sec.right_margin=Inches(.75)
sec.header_distance=Inches(.3);sec.footer_distance=Inches(.32)
styles=doc.styles
styles['Normal'].font.name='Arial';styles['Normal'].font.size=Pt(9.3);styles['Normal'].font.color.rgb=RGBColor(37,52,66)
styles['Normal'].paragraph_format.space_after=Pt(5)
for name,size,before,after in [('Title',19,6,7),('Heading 1',15,17,9),('Heading 2',12,12,6),('Heading 3',10.5,8,4)]:
 st=styles[name];st.font.name='Arial';st.font.size=Pt(size);st.font.bold=True;st.font.color.rgb=RGBColor(21,64,90)
 st.paragraph_format.space_before=Pt(before);st.paragraph_format.space_after=Pt(after)
 st.paragraph_format.keep_with_next=True
if 'Compact' not in styles:
 st=styles.add_style('Compact',WD_STYLE_TYPE.PARAGRAPH)
 st.base_style=styles['Normal'];st.font.name='Arial';st.font.size=Pt(8.7);st.paragraph_format.space_after=Pt(3)
head=sec.header.paragraphs[0];head.text='HYDROKONTUR 360  /  MAGADAN  /  INTERNAL ENGINEERING DOSSIER  /  V6';head.style='Normal';head.alignment=WD_ALIGN_PARAGRAPH.RIGHT
head.runs[0].font.size=Pt(7);head.runs[0].font.color.rgb=RGBColor(98,121,137)
foot=sec.footer.paragraphs[0];foot.alignment=WD_ALIGN_PARAGRAPH.RIGHT
r=foot.add_run('WORKING SPECIFICATION  |  20 OCT 2026  |  PAGE ');r.font.size=Pt(7)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');foot._p.append(fld)

def P(text='',style=None):return doc.add_paragraph(text,style=style)
def H(t,l=1):return doc.add_heading(t,level=l)
def cellText(cell,text):
 cell.text=str(text)
 for p in cell.paragraphs:
  p.paragraph_format.space_after=Pt(2)
  for r in p.runs:r.font.size=Pt(8.4)
 cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER

def makeTable(headers,rows,widths=None):
 t=doc.add_table(rows=1,cols=len(headers));t.style='Light Shading Accent 1';t.alignment=WD_TABLE_ALIGNMENT.CENTER
 for j,h in enumerate(headers):
  cellText(t.rows[0].cells[j],h)
  for r in t.rows[0].cells[j].paragraphs[0].runs:r.font.bold=True;r.font.color.rgb=RGBColor(15,58,79)
 for k,row in enumerate(rows):
  cc=t.add_row().cells
  for j,v in enumerate(row):cellText(cc[j],v)
  trPr=t.rows[-1]._tr.get_or_add_trPr();cant=OxmlElement('w:cantSplit');trPr.append(cant)
 trPr=t.rows[0]._tr.get_or_add_trPr();repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');trPr.append(repeat)
 if widths:
  for row in t.rows:
   for j,width in enumerate(widths):row.cells[j].width=Inches(width)
 doc.add_paragraph('')
 return t

p=doc.add_paragraph();p.style='Title';p.add_run(ru_title)
p=doc.add_paragraph('V6 / Technical specification and verification plan / Six linked product modules')
p.style='Subtitle'
p=doc.add_paragraph('INTERNAL DEVELOPMENT DOSSIER  |  20 OCTOBER 2026  |  STATUS: PROPOSED / LAB-VALIDATED ONLY')
p.runs[0].font.color.rgb=RGBColor(128,79,34);p.runs[0].font.bold=True
P(ru_note)
P(ru_region)
P('This annex contains 108 proposed requirements, 48 canonical data fields, 15 API contracts, 12 responsibility workflows and 6 candidate Magadan-region pilot perimeters. No client acceptance, production telemetry, site rights, procurement award or implementation readiness is implied.')
makeTable(['Package component','Status','Evidence'],[
('V5 historical finance book and competitor audit','Preserved in V6 XLSX','21 original worksheets unchanged in role'),
('V6 executable assurance model','Locally tested','63 / 63 Node tests passed'),
('V6 browser QA','Locally tested','6 module screens, 7 transition steps, 8 assay interactions, mobile 375px'),
('Engineering solvers and field integrations','NOT IMPLEMENTED','Production HOLD until independent validation and owner consent'),
('Magadan region facilities','Candidate sites only','No private asset data represented')],[2.4,1.8,2.5])

H('1. Product boundary, mission and proof standard')
P('Customer-first objective: provide the owner/operator of energy assets with reproducible engineering evidence linked to the economic and financial consequences of feasible decisions. This is not a replacement for SCADA, dispatch operations, certified hydraulic or power-system solvers, the ERP accounting ledger or government authorization procedures.')
P('Technical value chain: controlled observation -> verified dataset snapshot -> approved mathematical model -> explicit constraints -> comparable alternatives -> engineering review -> finance review -> authorized decision -> execution record -> independent post-investment outcome.')
P('Evidence classes: KNOWN FROM AUTHORIZED SOURCE; DESIGN PROPOSAL; SYNTHETIC DEMONSTRATION; MISSING OWNER DATA. Each report must show class, responsible legal owner, source time, model version and limitation. Numeric output lacking the required evidence class shall not be promoted to an approved production result.')
P('Development and capital construction are separate financial scopes. No operating benefits, grant funding or construction quantities are confirmed in this V6 annex. Stage gate agreements are prerequisites to client-facing return projections.')

H('2. Magadan pilot perimeters and rights')
P('Candidate physical perimeters are the Kolyma and Ust-Srednekan hydropower assets and individually authorized network/heat-system sections within the Magadan Region. No single sponsor is assumed to own data, operating rights or approvals for all candidates.')
makeTable(['Module','Candidate / proof need','Principal blocker'],[(p[0],p[1]+'; '+p[4],p[5]) for p in PILOTS],[1.35,3.8,1.65])
P('G0 shall not pass unless every participating organization signs the permitted data perimeter, data class, responsible engineer, independent acceptance method and non-control integration boundary. Sensitive drawings and operating setpoints must never be bundled with public demonstration artifacts.')

H('3. Data plane and canonical evidence objects')
P('Data registry keys: (owner_org_id, asset_id, source_id, valid_time, available_time, version_id). Observed time and information availability time are distinct. A forecast may use only input features available at or before its issue timestamp. Corrections create new versions; old observations and decision baselines remain reproducible.')
P('Typed measurement contract: organization_id, asset_id, metric_id, value, unit, observed_at, available_at, ingested_at, source_id, quality_flag, method_version and immutable evidence reference. A value of zero is a valid measured value; null denotes missingness and cannot be silently converted to zero.')
makeTable(['Field / unit','Meaning and owner reference','Missing-data control'],[(d[0]+' / '+d[2],d[3]+'; source: '+d[5],d[6]) for d in DATA],[2.25,3.4,1.15])

H('4. Module-by-module technical requirements')
intro={
'HydroForecast':'Hydrological truth must be evaluated using issue-time-safe backtesting. The first claimed improvement is relative skill and calibrated uncertainty, not extra generation revenue.',
'CascadeEconomics':'The proposed water-energy scenario layer compares only physically, institutionally and legally admissible alternatives; it never issues plant control commands.',
'TurbineReliability':'Abnormal telemetry is not automatically a failure or a calibrated probability of failure. Engineer labels and validated historical events are mandatory.',
'GridLossPlanner':'A metering residual is not proof of theft or a technical loss. Physical model, topology, meter clocks and financial methods require independent approval.',
'HeatNetEconomics':'Heating flow, pressure and heat balances require hydraulic/thermal reference verification; estimated cost saving must be normalized for weather and consumption.',
'HydroCAPEX':'Investment alternatives must retain their engineering cause, hard obligations, budget versions, WBS, dependencies, funding conditions and post-investment outcome.',
'CorePlatform':'Control-plane and trust rules protect all six modules: organizational isolation, immutable snapshots, independently anchored audit and no industrial control writes.'
}
for module in ['HydroForecast','CascadeEconomics','TurbineReliability','GridLossPlanner','HeatNetEconomics','HydroCAPEX','CorePlatform']:
    H('4.'+str(['HydroForecast','CascadeEconomics','TurbineReliability','GridLossPlanner','HeatNetEconomics','HydroCAPEX','CorePlatform'].index(module)+1)+' '+module,2)
    P(intro[module])
    rows=[]
    for r in REQS:
      if r['module']!=module:continue
      rows.append((r['id']+' / '+r['priority'],r['feature']+'\nINPUTS: '+r['inputs'], 'RULE: '+r['rule']+'\nTEST: '+r['acceptance']))
    makeTable(['ID / gate','Function and source fields','Engineering rule and acceptance evidence'],rows,[1.0,2.35,3.55])

H('5. Draft API and integration contracts')
P('These endpoints are not implemented. All production interfaces require a signed contract, HTTP identity and authorization enforcement, replay-safe idempotency, immutable version IDs, structured errors, object- and organization-level permissions and a prohibited-direction network policy for industrial control systems.')
for x in API:
    H(x[0]+' '+x[1],3)
    P('Request and authority: '+x[2],style='Compact')
    P('Response: '+x[3],style='Compact')
    P('Mandatory negative test: '+x[4],style='Compact')

H('6. Financial models and benefit reconciliation')
P('A scenario may be ranked only after hard-constraint verification and comparability checks. The reference investment valuation uses real cash-flow periods and an approved rate: NPV = -I0 + sum_t(CF_t / (1+r)^t). Benefits must be identified by legal owner, causal intervention and evidence; the same physical result appearing in two modules can be counted only once.')
P('Illustrative synthetic network case: 2,400 MWh/year times RUB 4/kWh equals RUB 9.6 million/year gross energy benefit. Additional assumptions: RUB 1.1 million/year other benefits, RUB 1.5 million/year operating cost, RUB 28 million initial investment, 12% annual discount, 8-year horizon. Net annual cash flow is 9.2 million; NPV is approximately RUB 17.702 million. No number in this example is a RusHydro or Magadan asset estimate.')
P('Production model requires tariff and cost accounting method, taxes, inflation/nominal-vs-real discipline, schedule of capital expenditures, renewals and decommissioning effects where applicable, alternative risk scenarios and baseline attribution. Statutory safety measures are not discarded solely for negative NPV.')

H('7. Engineering-to-construction proof packages')
P('For proposed line, heat-network or generating-asset works, build a separate WBS/BOQ estimate; verify ownership, survey data, plan drawings, actual dimensions and required statutory permits. Construction budgets are distinct from software development and research budgets. No engineering quantities have been authorized for this dossier.')
makeTable(['Document package','Minimum acceptance','Decision usage'],[
('AS-IS asset register','Owner, effective topology, condition history, approved drawings','Choose a valid candidate asset'),
('Survey and baseline evidence','Professional survey, actual parameters, independent reviewer','Engineering feasibility'),
('Three admissible options or documented fewer','Scope, constraints, costs, limitations, non-action safety status','Avoid single-option justification'),
('WBS and quantity take-off','Explicit quantity, unit, rate source and revision','Defensible CAPEX estimate'),
('Cost baseline and schedule','Cash flow by year, contingency methodology and dependencies','Funding and logistics'),
('Permit and compliance matrix','Applicability per object type and permit evidence','Construction go/no-go'),
('Commissioning protocol','As-built evidence and required test reports','Technically validated completion'),
('Post-investment audit','Comparable baseline, actual, confounder adjustment','Verified value, not claimed value')],[2.1,2.8,1.9])

H('8. Ownership, accountability and stage-gates')
makeTable(['Process','Responsible','Approving / accountable','Consulted'],[(x[0],x[1],x[2],x[3]) for x in RACI],[2.0,1.6,1.7,1.55])
P('Gate G0: owner permission and exact data scope. Gate G1: quality and legal provenance. Gate G2: solver and model verification. Gate G3: comparable economic case and independent finance tieout. Gate G4: engineering, legal and security approval. Gate G5: procurement/funding approvals and work authorization. Gate G6: acceptance testing. Gate G7: independent outcome verification. Any failed gate pauses the corresponding workstream; it does not silently convert to GREEN.')

H('9. Quality control, demonstrator limitations and release criteria')
P('Local Node tests: 63/63 passed. Browser control flow: six modular screens, seven role transitions, an eight-event laboratory audit trace, eight V6 assurance interactions, and 375-pixel responsive viewport. Browser localStorage is not an authorized source of truth; role switch is not identity, and client-side digest is not an immutable archive.')
P('The V6 analytics laboratory cannot command turbine gates, electric protection devices, grid switching or heat system controls. It has no SCADA connector, authoritative meter telemetry, signed operating restrictions, professional hydraulic/electrical solver, tenant-secure server or approval from an energy operator. Production status is HOLD.')
P('Exit criteria for industrial trial: real and legally provided source snapshot; approved reference calculation; tested no-future leakage; independent engineering signoff; documented stakeholder authority; financial source tieout; audit retention; formal threat and integration boundary review; limited acceptance scope and rollback plan.')

H('10. Reference documentation (external sources)')
for key,url in SOURCES.items():
    P(f'{key}: {url}',style='Compact')
P('The external sources above are design and comparison references, not evidence that HYDROKONTUR has equivalent certified functionality. For ISO 55001:2024, legal applicability and procurement of the complete standard must be evaluated separately. For construction approval, apply the Russian statutory and owner-specific documentation matrix produced during G0.')

H('11. Open issues before funding release')
makeTable(['Blocking question','Required evidence','Owner to confirm'],[
('Which incumbent systems are used at each candidate asset?','Read-only inventory, architecture and workflow maps','Asset owner + IT'),
('Which party owns each dataset?','Legal contract, data classification and scope','Legal/data steward'),
('Are field events sufficient for reliability models?','History of confirmed defects and sample statistics','Reliability engineers'),
('Are accepted hydro rules and models available?','Active operating constraints and signed characteristics','Hydrology/cascade owner'),
('What cost model applies to electricity losses?','Approved energy settlement/valuation methodology','Finance and grid owner'),
('What is the lifecycle scope of investments?','BOQ, WBS, pricing, schedule, financing and taxes','PMO + finance'),
('Which demonstration can be accepted?','Signed numerical and operating acceptance gates','Project sponsor'),
('Who authorizes deployment?','Security, engineering and information system owner decisions','Authorized approving bodies')],[2.15,3.2,1.55])
P('A production-ready tender or grant request must not assert confirmed reductions in losses, failures, cost or useable generation before these gaps are closed.')

doc.core_properties.title='HydroKontur 360 Magadan | V6 engineering specification'
doc.core_properties.subject='108 requirement catalogue, data contracts, pilot gates and financial evidence'
doc.core_properties.author='HYDROKONTUR 360 / internal working package'
doc.save(out)
print(out,'paragraphs',len(doc.paragraphs),'tables',len(doc.tables),'bytes',out.stat().st_size)
