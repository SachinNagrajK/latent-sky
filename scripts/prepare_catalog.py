import sys,json,csv,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from worker.science import ROOT,now
endpoint='https://datalab.noirlab.edu/query/query'
def query(sql):
    response=httpx.get(endpoint,params={'sql':sql,'ofmt':'csv','out':'','async':'False','drop':'False'},headers={'X-DL-AuthToken':'anonymous.0.0.anon_access','X-DL-TimeoutRequest':'40'},timeout=50,follow_redirects=True)
    response.raise_for_status()
    if response.text.lstrip().startswith(('<','Error')): raise RuntimeError('Catalog service error: '+response.text[:1800])
    return response.text
schema=query("SELECT * FROM ls_dr10.tractor LIMIT 0")
names={name.lower() for name in next(csv.reader(io.StringIO(schema)))}
if not {'ls_id','ra','dec'}<=names: raise RuntimeError('Live DR10 schema did not contain required fields')
sql="SELECT ls_id,ra,dec FROM ls_dr10.tractor WHERE q3c_radial_query(ra,dec,195.033738,27.977025,0.035) LIMIT 5000"
text=query(sql);catalog=list(csv.DictReader(io.StringIO(text)))
if not catalog: raise RuntimeError('No reference sources returned')
folder=ROOT/'fixtures/catalogs';folder.mkdir(parents=True,exist_ok=True)
(folder/'coma.csv').write_text(text)
(folder/'schema.csv').write_text(schema)
(folder/'manifest.json').write_text(json.dumps({'endpoint':endpoint,'query':sql,'retrieved_at':now(),'count':len(catalog),'sha256':hashlib.sha256(text.encode()).hexdigest(),'attribution':'NOIRLab Astro Data Lab / DESI Legacy Imaging Surveys DR10'},indent=2))
print('Catalog verified and saved:',len(catalog),'rows')
