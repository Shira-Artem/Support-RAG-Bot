from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter
import csv,re
import yaml
root=Path('data/knowledge'); docs=[]
previous={}
output=Path('reports/kb_review_b2_quality/semantic_overlap_candidates.csv')
if output.exists():
 with output.open(encoding='utf-8',newline='') as f:
  previous={(r['path_a'],r['path_b']):r['manual_review'] for r in csv.DictReader(f)}
for p in sorted(root.rglob('*.md')):
 s=p.read_text();parts=s.split('---',2);meta=yaml.safe_load(parts[1]);body=parts[2].casefold();tokens=set(re.findall(r'[а-яёa-z0-9]{4,}',body));docs.append((str(p),meta,tokens))
candidates=[]
for i,(pa,ma,a) in enumerate(docs):
 for pb,mb,b in docs[i+1:]:
  common=a&b
  if len(common)<12:continue
  jac=len(common)/len(a|b); overlap=len(common)/min(len(a),len(b))
  if jac>=.33 or (overlap>=.70 and len(common)>=18):candidates.append({'path_a':pa,'document_id_a':ma.get('document_id'),'status_a':ma.get('status'),'path_b':pb,'document_id_b':mb.get('document_id'),'status_b':mb.get('status'),'jaccard':round(jac,3),'overlap':round(overlap,3),'manual_review':previous.get((pa,pb),'unverified')})
candidates.sort(key=lambda r:(-r['jaccard'],-r['overlap']))
with open('reports/kb_review_b2_quality/semantic_overlap_candidates.csv','w',encoding='utf-8',newline='') as f:
 fields=['path_a','document_id_a','status_a','path_b','document_id_b','status_b','jaccard','overlap','manual_review'];w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(candidates)
print('candidates',len(candidates))
for c in candidates[:24]:print(c['jaccard'],c['overlap'],c['path_a'],c['path_b'])
