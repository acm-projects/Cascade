"""Install the audited free compositor; no npm scripts, models, keys or services.

Run from the Cascade root: python3 scripts/install_fablecut.py
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

COMMIT='579b08ec1a789baec5cbf06d7430373460508d09'
root=Path(__file__).resolve().parents[1]
target=root/'backend/editor/.cache/fablecut'
if (target/'server.js').is_file():
    if (target/'CASCADE_PIN').read_text().strip()!=COMMIT:
        raise RuntimeError('Existing FableCut is not the audited revision. It was not overwritten.')
    print(f'Audited FableCut already installed at {target}; existing installation retained.')
else:
    with tempfile.TemporaryDirectory(prefix='cascade-fablecut-install-') as directory:
        checkout=Path(directory)/'source'
        subprocess.run(['git','init',str(checkout)],check=True)
        subprocess.run(['git','-C',str(checkout),'remote','add','origin','https://github.com/ronak-create/FableCut.git'],check=True)
        subprocess.run(['git','-C',str(checkout),'fetch','--depth','1','origin',COMMIT],check=True)
        subprocess.run(['git','-C',str(checkout),'checkout',COMMIT],check=True)
        if not (checkout/'LICENSE').read_text().startswith('MIT License'):
            raise RuntimeError('Expected MIT license; installation stopped.')
        target.mkdir(parents=True,exist_ok=False)
        for file in checkout.iterdir():
            if file.is_file() and (file.suffix in ('.js','.json') or file.name in ('index.html','style.css','favicon.svg','LICENSE')):
                shutil.copy2(file,target/file.name)
        for name in ('library','icons'):
            shutil.copytree(checkout/name,target/name)
        (target/'CASCADE_PIN').write_text(COMMIT+'\n')
    print(f'Installed MIT FableCut 1.18.0 at {target}. No inference or model downloads were performed.')
