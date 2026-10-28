from pathlib import Path
r=Path(__file__).parent
page=(r/'index.html').read_text('utf-8')
css=(r/'src/styles.css').read_text('utf-8')
core=(r/'src/domain.mjs').read_text('utf-8').replace('export const ','const ').replace('export function ','function ').replace('export async function ','async function ')
app=(r/'src/app.mjs').read_text('utf-8')
assurance=(r/'src/assurance.mjs').read_text('utf-8').replace('export function ','function ')
app='\n'.join(line for line in app.splitlines() if not line.startswith('import {'))
page=page.replace('<link rel="stylesheet" href="src/styles.css">','<style>'+css+'</style>')
page=page.replace('<script type="module" src="src/app.mjs"></script>','<script>\n(async()=>{\n'+core+'\n'+assurance+'\n'+app+'\n})().catch(e=>console.error(e));\n</script>')
out=r/'dist'/'standalone.html'
out.parent.mkdir(exist_ok=True)
out.write_text(page,'utf-8')
print('Standalone in project:',out, 'size',out.stat().st_size)
export=Path('/mnt/data/ГИДРОКОНТУР_360_МАГАДАН_Лабораторный_прототип_V6.html')
if export.parent.exists():
    export.write_text(page,'utf-8')
    print('Export:',export)

