"""Report likely word splits between adjacent chunks; no content is modified."""
import csv,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app.knowledge import DocumentLoader,Chunker
kb=root/'data/knowledge';loader=DocumentLoader(kb);rows=[]
for path in sorted(kb.rglob('*.md')):
 try:
  chunks=Chunker().split(loader.load(path))
  for i,c in enumerate(chunks):
   if c.metadata['section_chunk_index']:
    text=c.text.split('\n',1)[-1];prev=chunks[i-1].text
    if re.match(r'^[а-яa-zё]',text) and re.search(r'[а-яa-zё]$',prev,re.I):
     rows.append({'path':path.relative_to(root).as_posix(),'section':c.section,'index':c.metadata['section_chunk_index'],'previous_end':prev[-60:],'next_start':text[:60]})
 except Exception as e:print('ERROR',path,type(e).__name__,str(e))
out=root/'reports/kb_review_b2_quality/chunk_boundary_review.csv'
with out.open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,['path','section','index','previous_end','next_start'],lineterminator='\n');w.writeheader();w.writerows(rows)
print('possible midword cuts:',len(rows),'files:',len({r['path'] for r in rows}))
