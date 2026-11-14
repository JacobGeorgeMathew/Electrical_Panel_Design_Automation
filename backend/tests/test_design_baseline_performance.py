"""Opt-in timings on a fixture-owned disposable PostgreSQL database.

PANEL_RUN_POSTGRES_TESTS=1 PANEL_MEASURE_BASELINE=1 .venv/bin/python -m pytest \
    tests/test_design_baseline_performance.py -q -s
No latency threshold is asserted: proposed lifecycle targets are not approved.
"""
import json
import math
import os
import platform
import statistics
import time

import pytest

from app.persistence.assets import content_hash
from tests.design_baseline_support import CASES


def summary(samples):
    return dict(samples_ms=samples, median_ms=statistics.median(samples),
                nearest_rank_p95_ms=sorted(samples)[math.ceil(.95*len(samples))-1])


@pytest.mark.skipif(os.environ.get('PANEL_MEASURE_BASELINE') != '1', reason='Set PANEL_MEASURE_BASELINE=1 for opt-in timing evidence.')
@pytest.mark.parametrize('case', CASES['feasible'], ids=lambda c: c['id'])
def test_saved_open_and_generate_timings(api, case):
    response = api.post('/api/projects', json=dict(name='Performance '+case['id'],
        requirements={**CASES['requirements'], 'num_feeders':case['num_feeders']}))
    assert response.status_code == 201, response.text
    project = response.json()
    path = '/api/projects/'+project['id']
    version = project['lock_version']
    generations, opens = [], []
    reference = None
    for iteration in range(6):  # first sample retained separately as warm-up
        started = time.perf_counter_ns()
        response = api.post(path+'/revisions', json={'expected_version':version})
        elapsed = (time.perf_counter_ns()-started)/1e6
        assert response.status_code == 201, response.text
        saved = response.json()
        version = saved['lock_version']
        semantic = {k:saved[k] for k in ('cem','pdm','schematic','cad','bom','validation_errors')}
        digest = content_hash(semantic)
        if reference is None:
            reference = digest
            warm_generate = elapsed
        assert digest == reference  # same project, IDs, catalog pins and exact output
        if iteration:
            generations.append(elapsed)
        started = time.perf_counter_ns()
        opened = api.post(path+'/open')
        reopened = api.get(path+'/design')
        elapsed = (time.perf_counter_ns()-started)/1e6
        assert opened.status_code == reopened.status_code == 200
        assert reopened.json()['snapshot_sha256'] == saved['snapshot_sha256']
        assert {k:reopened.json()[k] for k in semantic} == semantic
        assert opened.json()['lock_version'] == version
        if iteration:
            opens.append(elapsed)
        else:
            warm_open = elapsed
    # Evidence intentionally excludes UUID-bearing payloads/credentials/paths.
    print('BASELINE_PERFORMANCE '+json.dumps(dict(
        case=case['id'], python=platform.python_version(),
        components=len(saved['pdm']['components']), routes=len(saved['pdm']['routes']),
        enclosure_mm=[saved['pdm']['enclosure_'+axis] for axis in ('width','height','depth')],
        warmup_generate_ms=warm_generate, warmup_open_ms=warm_open,
        generate=summary(generations), open=summary(opens),
        engine_version=saved['manifest']['engine_version'],
        generator=saved['manifest']['generator'],
        artifact_hashes={a['file_format']:a['sha256'] for a in saved['artifacts']},
        semantic_sha256=reference,
    )), flush=True)
