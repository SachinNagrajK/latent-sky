from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
for case in ['cosmic-stitch','faint-sources']:
    dest=root/'public/fixtures'/case; dest.mkdir(parents=True,exist_ok=True)
    for path in (root/'output'/case).iterdir():
        if path.suffix in ['.png','.json']: shutil.copy2(path,dest/path.name)
print('Exported real pipeline outputs for the web preview.')
