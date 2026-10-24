"""Exercise the frozen entrypoint and its real HTTP client using a local fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pandas as pd

from tracks.t2.context import load
from tracks.t2.distribution import Config, sample

p = argparse.ArgumentParser()
p.add_argument('--mode', choices=['adjust', 'abstain', 'invalid', 'unavailable'], required=True)
a = p.parse_args()
ctx = load(Path('/input/panels'), Path('/input/text'), '2019-01-07')
config = Config(**json.loads(Path('/agent/tracks/t2/selected_config.json').read_text()))
baseline, _ = sample(ctx, config)
calls = []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path == '/v1/chat/completions'
        assert self.headers['Authorization'] == 'Bearer synthetic-fixture-only'
        assert body['model'] == 'house-fixture' and body['max_tokens'] <= 4000
        assert body['temperature'] == 0 and body['seed'] == 1729
        data = json.loads(body['messages'][1]['content'])
        assert 'market_context' in data and all('passages' in d for d in data['documents'])
        rows = [{'asset': asset, 'horizon': h, 'decision': 'abstain',
                 'reason_code': 'insufficient_evidence',
                 'brief_reason': 'Synthetic fixture checks routing and validation only.',
                 'mean_sd': 0, 'scale': 1, 'evidence': [], 'market_evidence': []}
                for asset in data['assets'] for h in data['horizons']]
        if a.mode in {'adjust', 'invalid'}:
            chosen = None
            for doc in data['documents']:
                for passage in doc['passages']:
                    quote = passage['text'][:100]
                    matches = sum(x['text'].count(quote) for x in doc['passages'])
                    if len(quote) >= 16 and matches == 1:
                        chosen = {'doc_id': doc['doc_id'], 'quote': quote}
                        break
                if chosen:
                    break
            assert chosen is not None
            if a.mode == 'invalid':
                chosen['quote'] = 'This fabricated citation is absent from every supplied passage.'
            rows[0].update(decision='adjust', reason_code='actionable_evidence',
                           mean_sd=.1, evidence=[chosen])
        calls.append({'v3_request': True, 'cells': len(rows)})
        raw = json.dumps({'choices': [{'message': {'content': json.dumps({'decisions': rows})},
                                      'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

server = None
if a.mode != 'unavailable':
    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ.update(MODEL_ENDPOINT=f'http://127.0.0.1:{server.server_port}',
                      MODEL_TOKEN='synthetic-fixture-only', MODEL_NAME='house-fixture',
                      NO_PROXY='127.0.0.1', no_proxy='127.0.0.1')
else:
    for key in ('MODEL_ENDPOINT', 'MODEL_TOKEN', 'MODEL_NAME'):
        os.environ.pop(key, None)
sys.argv = ['agent.py', 'forecast', '--panels', '/input/panels', '--text', '/input/text',
            '--asof', ctx.asof, '--out', '/output/forecast.parquet']
try:
    runpy.run_path('/agent/tracks/t2/agent.py', run_name='__main__')
except SystemExit as exc:
    assert exc.code in (None, 0)
finally:
    if server:
        server.shutdown()
assert len(calls) == (0 if a.mode == 'unavailable' else 1)
out = Path('/output')
assert sorted(x.name for x in out.iterdir()) == ['forecast.parquet', 'forecast_meta.json', 'forecast_rationale.md']
values = pd.read_parquet(out/'forecast.parquet')['value'].to_numpy().reshape(baseline.shape)
expected = baseline.copy()
if a.mode == 'adjust':
    expected[:, 0, 0] += .1*np.std(baseline[:, 0, 0], ddof=1)
np.testing.assert_allclose(values, expected, rtol=1e-14, atol=1e-14)
rationale = (out/'forecast_rationale.md').read_text()
status = 'fallback' if a.mode in {'invalid', 'unavailable'} else 'validated'
assert f'"text_status": "{status}"' in rationale and '"text_protocol": "v3"' in rationale
assert ('"text_used": true' in rationale) == (a.mode == 'adjust')
print(json.dumps({'mode': a.mode, 'passed': True, 'http_calls': len(calls),
                  'text_status': status, 'expected_distribution_matches': True,
                  'forecast_sha256': hashlib.sha256((out/'forecast.parquet').read_bytes()).hexdigest()}))
