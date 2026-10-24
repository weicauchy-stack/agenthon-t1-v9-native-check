"""Use original official gates on every public card; no outcome files are read."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tomllib

from tracks.t2.candidate import main
from qfbench2_common.manifest import verify_manifest
from qfbench2_track_forecasting.scoring import _main

rows = []
for card_path in sorted(Path('/units').glob('*/card.toml')):
    unit = card_path.parent
    assert not verify_manifest(unit)
    card = tomllib.loads(card_path.read_text())
    panels = unit/'panels' if (unit/'panels').is_dir() else unit
    forecast = Path('/output')/unit.name/'forecast.parquet'
    assert main(['--panels', str(panels), '--text', str(unit/'text'),
                 '--asof', card['provenance']['data_cutoff'], '--card', str(card_path),
                 '--config', '/agent/tracks/t2/selected_config.json', '--text-mode', 'off',
                 '--out', str(forecast)]) == 0
    captured = StringIO()
    with redirect_stdout(captured):
        code = _main(['score', '--card', str(card_path), '--forecast', str(forecast)])
    result = json.loads(captured.getvalue())
    assert code == 0 and result['admissible'], unit.name
    rows.append({'unit': unit.name, 'admissible': True})
assert len(rows) == 126
print(json.dumps({'passed': True, 'cards': len(rows), 'admissible': len(rows),
                  'outcomes_read': False, 'rows': rows}))
