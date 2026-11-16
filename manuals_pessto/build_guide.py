"""Build the standalone three-workflow EFOSC manual with embedded saved figures."""
from pathlib import Path
import base64
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
content = (ROOT/'guide-content.html').read_text()
figures = {}
for name in re.findall(r'src="(figures/[^"]+)"', content):
    data = (ROOT/name).read_bytes()
    figures[name] = hashlib.sha256(data).hexdigest()
    content = content.replace('src="'+name+'"', 'src="data:'+('image/jpeg' if name.endswith('.jpg') else 'image/png')+';base64,'+base64.b64encode(data).decode()+'"')
for name in re.findall(r'href="(figures/[^"]+)"', content):
    data = (ROOT/name).read_bytes()
    mime = 'application/pdf' if name.endswith('.pdf') else 'image/jpeg'
    content = content.replace('href="'+name+'" download', 'href="data:'+mime+';base64,'+base64.b64encode(data).decode()+'" download="'+Path(name).name+'"')
# Embed the helper download so the manual remains a single offline file.
helper = ROOT / 'list_raw_frames.py'
payload = base64.b64encode(helper.read_bytes()).decode()
content = content.replace('href="list_raw_frames.py" download',
                          'href="data:text/x-python;base64,' + payload + '" download="list_raw_frames.py"')
script = '''const dialog=document.querySelector('dialog');
const large=dialog.querySelector('img');
document.querySelectorAll('figure button').forEach(button=>button.addEventListener('click',()=>{
 const small=button.querySelector('img');large.src=small.src;large.alt=small.alt;dialog.showModal();
}));
dialog.querySelector('button').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});'''
page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Reduction Manual</title><style>'
        +(ROOT/'guide.css').read_text()+'</style></head><body><main>'+content
        +'</main><dialog aria-label="Enlarged reduction diagnostic"><button type="button">Close</button>'
        '<img alt=""></dialog><script>'+script+'</script></body></html>')
(ROOT/'index.html').write_text(page)
(ROOT/'figure-hashes.json').write_text(json.dumps(figures,indent=2)+'\n')
print(ROOT/'index.html')
