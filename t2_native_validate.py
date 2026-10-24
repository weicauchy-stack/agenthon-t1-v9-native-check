"""Validate the immutable T2 v3 image on native Linux x86_64; zero paid calls."""
from pathlib import Path
import hashlib
import io
import json
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path.cwd()
META = json.loads((ROOT/'t2-v3-release.json').read_text())
IMAGE = META['image']
assert platform.system() == 'Linux' and platform.machine() == 'x86_64'
WORK = ROOT/'t2-v3-validation-output'
WORK.mkdir(exist_ok=False)
checks = []

def command(label, args, timeout=180):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    (WORK/(label+'.log')).write_text(p.stdout+p.stderr)
    if p.returncode:
        print('FAILED_CHECK='+label+'\n'+p.stdout+p.stderr, flush=True)
    assert p.returncode == 0, label
    return p

command('anonymous-pull', ['docker', 'pull', IMAGE], 300)
meta = json.loads(command('image-inspect', ['docker', 'image', 'inspect', IMAGE]).stdout)[0]
assert meta['Architecture'] == 'amd64' and meta['Os'] == 'linux'
assert meta['Config'].get('Labels', {}).get('qfbench2.interface_version') == '2.0'
assert not meta['Config'].get('Volumes')
assert meta['Config']['Entrypoint'] == ['python', '/agent/tracks/t2/agent.py']
checks.append({'check': 'image_contract', 'passed': True})

def run(label, tail, mounts=(), timeout=180):
    name = 't2-v3-native-'+label+'-'+str(time.time_ns())
    args = ['docker', 'run', '--rm', '--name', name, '--network=none', '--read-only',
            '--user', '1000:1000', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--cpus=2', '--memory=4g', '--pids-limit=512',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1g']
    for source, target, readonly in mounts:
        args += ['-v', str(source)+':'+target+(':ro' if readonly else '')]
    try:
        return command(label, args+tail, timeout)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)

code = "import pathlib,hashlib,json; r=pathlib.Path('/agent'); f="+repr(list(META['runtime_sources']))+"; print(json.dumps({p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in f}))"
p = run('source-hashes', ['--entrypoint', 'python', IMAGE, '-c', code])
assert json.loads(p.stdout) == META['runtime_sources']
checks.append({'check': 'frozen_v3_sources', 'passed': True})
run('numeric-imports', ['--entrypoint', 'python', IMAGE, '-c',
                      'import numpy,pandas,scipy,pyarrow; import tracks.t2.reasoning_v3; print("imports_ok")'])
checks.append({'check': 'numeric_imports', 'passed': True})
run('cli-help', [IMAGE, 'forecast', '--help'])
checks.append({'check': 'cli_help', 'passed': True})

with urllib.request.urlopen(META['official_archive_url'], timeout=90) as response:
    archive = response.read(96*1024*1024+1)
assert len(archive) <= 96*1024*1024
assert hashlib.sha256(archive).hexdigest() == META['official_archive_sha256']
source = WORK/'official'
source.mkdir()
with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
    bundle.extractall(source, filter='data')
units = next(source.iterdir())/'units'
assert len(list(units.glob('*/card.toml'))) == 126
checks.append({'check': 'official_archive_hash', 'passed': True})

unit = units/'t2-F1-curve-ust1y-001-ps1'
staged = WORK/'staged'
staged.mkdir()
for name in ('card.toml', 'forecast_spec.json'):
    if (unit/name).is_file():
        shutil.copy2(unit/name, staged/name)
(staged/'panels').mkdir()
panels = sorted((unit/'panels').glob('*.parquet')) or sorted(unit.glob('*.parquet'))
assert panels
for panel in panels:
    shutil.copy2(panel, staged/'panels'/panel.name)
shutil.copytree(unit/'text', staged/'text')

qa_mounts = [(ROOT/'t2_house_probe.py', '/qa/house_probe.py', True),
             (ROOT/'t2_contract_probe.py', '/qa/contract_probe.py', True)]
for mode in ('adjust', 'abstain', 'invalid', 'unavailable', 'contract'):
    out = WORK/(mode+'-output')
    out.mkdir()
    out.chmod(0o777)
    mounts = qa_mounts+[(out, '/output', False)]
    if mode == 'contract':
        mounts += [(units, '/units', True)]
        tail = ['--entrypoint', 'python', IMAGE, '/qa/contract_probe.py']
    else:
        mounts += [(staged, '/input', True)]
        tail = ['--entrypoint', 'python', IMAGE, '/qa/house_probe.py', '--mode', mode]
    p = run(mode, tail, mounts, 300)
    result = json.loads(p.stdout.strip().splitlines()[-1])
    assert result['passed']
    checks.append({'check': mode, 'passed': True,
                   **{k: v for k, v in result.items() if k != 'rows'}})

report = {'passed': True, 'native_amd64_validated': True,
          'host_system': platform.system(), 'host_machine': platform.machine(),
          'image': IMAGE, 'runtime_sources_match': True, 'default_text_mode': 'house-v3',
          'official_public_cards_admissible': 126, 'house_http_fixture_cases_passed': 4,
          'paid_calls': 0, 'real_house': False, 'model_performance_test': False,
          'checks': checks, 'submitted': False}
(WORK/'native-validation.json').write_text(json.dumps(report, indent=2)+'\n')
print('T2_V3_NATIVE_VALIDATION_RESULT='+json.dumps(report), flush=True)
