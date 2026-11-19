"""Report likely word splits between adjacent chunks; no content is modified."""
import csv,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app.knowledge import DocumentLoader,Chunker
kb=root/'data/knowledge';loader=DocumentLoader(kb);rows=[]
out=root/'reports/kb_review_b2_quality/chunk_boundary_review.csv'
previous={}
if out.exists():
 with out.open(encoding='utf-8-sig',newline='') as f:
  for old in csv.DictReader(f):
   key=(old.get('path',''),old.get('section',''),old.get('index',''))
   previous[key]=old
for path in sorted(kb.rglob('*.md')):
 try:
  doc=loader.load(path);chunks=Chunker().split(doc)
  for i,c in enumerate(chunks):
   if c.metadata['section_chunk_index']:
    text=c.text.split('\n',1)[-1];prev=chunks[i-1].text
    if re.match(r'^[а-яa-zё]',text) and re.search(r'[а-яa-zё]$',prev,re.I):
     key=(path.relative_to(root).as_posix(),c.section,str(c.metadata['section_chunk_index']))
     old=previous.get(key,{})
     rows.append({'path':key[0],'section':c.section,'index':key[2],'previous_end':prev[-60:],'next_start':text[:60],
      'status':doc.status,'review_result':old.get('review_result','unverified'),'risk':old.get('risk','unverified'),
      'recommended_owner':old.get('recommended_owner','unassigned'),'preserve_manual_ui':old.get('preserve_manual_ui','true')})
 except Exception as e:print('ERROR',path,type(e).__name__,str(e))
with out.open('w',encoding='utf-8',newline='') as f:
 fields=['path','section','index','previous_end','next_start','status','review_result','risk','recommended_owner','preserve_manual_ui']
 w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(rows)
print('possible midword cuts:',len(rows),'files:',len({r['path'] for r in rows}))
