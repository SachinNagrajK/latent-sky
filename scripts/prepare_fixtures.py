import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker.science import prepare, CASES
for slug in CASES:
    manifest=prepare(slug)
    print(slug,[(x['kind'],x['coverage_fraction'],x['checksum'][:12]) for x in manifest['inputs']])
