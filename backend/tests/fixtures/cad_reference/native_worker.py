"""Native experiment helper, launched only through spike.py native.

Reopen mode reads the STEP in a fresh process, never the source PDM or BREP.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys
import time

import FreeCAD as App
import Part
from PySide import QtCore


def stats(shape):
    b = shape.BoundBox
    return {'bounds_mm': [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax],
            'valid': not shape.isNull() and shape.isValid(), 'volume_mm3': shape.Volume}


def main():
    started = time.perf_counter()
    scratch = Path(os.environ['PANEL_CAD_SPIKE_DIR'])
    mode = os.environ['PANEL_CAD_SPIKE_MODE']
    if '.'.join(App.Version()[:3]) != '1.0.2' or list(sys.version_info[:2]) != [3, 11]:
        raise RuntimeError('Native spike requires FreeCAD 1.0.2 with bundled Python 3.11')
    objects = {}
    if mode == 'export':
        # Exercise the actual repository exporter, not a second shape builder.
        namespace = {}
        path = scratch / 'existing-export.py'
        exec(compile(path.read_text(), str(path), 'exec'), namespace)
        doc = namespace['doc']
        objects = {obj.Name: stats(obj.Shape) for obj in doc.Objects}
        shape = Part.makeCompound([obj.Shape for obj in doc.Objects])
    elif mode == 'reopen':
        shape = Part.read(str(scratch / 'panel_model.step'))
    else:
        raise ValueError(mode)
    step = (scratch / 'panel_model.step').read_bytes()
    text = step.decode('ascii', errors='replace')
    report = {**stats(shape), 'solid_count': len(shape.Solids),
              'solids': [stats(s) for s in shape.Solids], 'objects': objects,
              'step_units_mm': bool(re.search(r'SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)', text)),
              'step_sha256': hashlib.sha256(step).hexdigest(), 'step_bytes': len(step),
              'freecad_version': '.'.join(App.Version()[:3]), 'occt_version': Part.OCC_VERSION,
              'freecad_build': App.Version(), 'pid': os.getpid(),
              'executable': sys.executable, 'prefix': sys.prefix,
              'freecad_module': getattr(App, '__file__', 'built-in (FreeCADCmd)'),
              'part_module': getattr(Part, '__file__', 'built-in (FreeCADCmd)'),
              'entry_module_name': __name__,
              'qt_version': QtCore.qVersion(),
              'runtime_environment': {k: os.environ.get(k) for k in (
                  'PYTHONHOME', 'PATH_TO_FREECAD_LIBDIR', 'LD_LIBRARY_PATH',
                  'QT_QPA_PLATFORM', 'DISPLAY', 'WAYLAND_DISPLAY')},
              'loaded_native_libraries': sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                  if any(name in line for name in ('libstdc++', 'libpython', 'libQt5Core', 'libTKernel'))}),
              'python_major_minor': list(sys.version_info[:2]), 'python': sys.version,
              'max_rss_kib_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'operation_ms': (time.perf_counter()-started)*1000}
    (scratch / (mode + '.json')).write_text(json.dumps(report, indent=2))


# FreeCADCmd executes .py files with its own module name, not __main__.
if os.environ.get('PANEL_CAD_SPIKE_MODE') in {'export', 'reopen'} and not os.environ.get('PANEL_CAD_SPIKE_STARTED'):
    os.environ['PANEL_CAD_SPIKE_STARTED'] = '1'
    main()
