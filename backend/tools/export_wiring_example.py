"""Export reviewable drawing and routing evidence from a running local API.

Usage: python tools/export_wiring_example.py --project PROJ_DB_DEMO_001
Output is documentation/example data, not a reusable catalog CAD asset.
"""
import argparse
import json
from html import escape
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote


def export_example(design,output):
    output.mkdir(parents=True,exist_ok=True)
    drawing=design['schematic']
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {drawing["width"]} {drawing["height"]}" role="img" aria-label="Generated DB schematic">',
        '<rect width="100%" height="100%" fill="#020617"/>']
    for wire in drawing['wires']:
        svg.append(f'<path d="{escape(wire["svg_path"])}" stroke="{wire["color"]}" stroke-width="2" fill="none"><title>{escape(wire["id"]+" | "+wire["net_name"])}</title></path>')
        for point in wire.get('crossings',[]):
            x,y=point['x'],point['y']
            path=f'M {x} {y-5} V {y+5}' if point.get('axis')=='VERTICAL' else f'M {x-5} {y} H {x+5}'
            svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#020617"/><path d="{path}" stroke="{wire["color"]}" stroke-width="2"/>')
        for point in wire.get('junctions',[]):svg.append(f'<circle cx="{point["x"]}" cy="{point["y"]}" r="3" fill="{wire["color"]}"/>')
    for symbol in drawing['symbols']:
        x,y,w,h=(symbol[k] for k in ('x','y','width','height'))
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#0f172a" stroke="#64748b"/>')
        for i,line in enumerate(symbol['label'].splitlines()):
            svg.append(f'<text x="{x+w/2}" y="{y+28+i*16}" text-anchor="middle" font-family="monospace" font-size="12" fill="white">{escape(line)}</text>')
        for terminal in symbol['terminals']:
            svg.append(f'<circle cx="{terminal["x"]}" cy="{terminal["y"]}" r="2.5" fill="#cbd5e1"><title>{escape(terminal["port_id"])}</title></circle>')
    svg.append('</svg>')
    (output/'DB-schematic.svg').write_text('\n'.join(svg),encoding='utf-8')
    evidence={'revision_id':design['revision_id'],'revision_no':design['revision_no'],'engine_version':design['manifest']['engine_version'],
        'units':'mm','coordinate_system':'PDM-lower-left-front-right-handed','physical_violations':design['pdm']['validation_results'],
        'schematic_checks':drawing.get('validation_results',[]),'routes':design['pdm']['routes']}
    (output/'DB-wiring.json').write_text(json.dumps(evidence,indent=2,allow_nan=False),encoding='utf-8')
    return len(evidence['routes'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',default='PROJ_DB_DEMO_001')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'docs/examples/wiring')
    args=parser.parse_args()
    with urlopen('http://127.0.0.1:8731/api/projects/'+quote(args.project,safe='')+'/design',timeout=60) as response:design=json.load(response)
    if design.get('is_stale'):raise SystemExit('Generate the current project revision before exporting an example.')
    print('Exported',export_example(design,args.output),'conductors to',str(args.output.resolve()))
