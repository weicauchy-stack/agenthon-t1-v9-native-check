"""Native x86_64 Linux validation only; no publishing, credentials or paid calls."""
from pathlib import Path
import hashlib,io,json,os,platform,shutil,subprocess,tarfile,tempfile,time,urllib.request
IMAGE='docker.io/weimys/agenthon-t1@sha256:0f6594fa9ed3cf3fc4a712aea0c3557ba9b9e4e1ad6b1c5cd9843932da1c6fe4'
EXPECTED_SOURCES={'tracks/t1/repair.py': '16c53ed0083e3d4309af6871a06cdd9ed331be9b13a24c4c8b861fbd3bc48555', 'tracks/t1/composer.py': '939d523b45cfe71ce64eba0a7426985532d20c4f3c67e0a0daf02926e873a8e5', 'tracks/t1/response.py': '994c19dddebd6b0ab3908798bb13a956966b8ff8883c22e43b2c591a2425bb67', 'tracks/t1/runtime.py': 'd9be5828123dcea2ceeecc277dc7732e3f42ad4157b4db3b66f93ffd6fd3f3cb', 'tracks/t1/prompts.py': 'cd680e0b2c1d5464c5aac72905165855c22130fd912a8597ff47f5b06b170f85', 'tracks/t1/agent.py': 'afed4ce0ca0846ff2df1ed6dbdb6680145ff3b839811fd3799db16ab2d4d8714', 'tracks/t1/quant.py': 'd527cfbd4dfbd86d192fd3999dc86181c1c2cfa67f01d67bf10d7660bc64de5a', 'tracks/t1/modules.py': '109e9b7cde19c0d7ca72a9c3d6d99fffea2164879ffbbc2b30bb14f60a108eb8', 'tracks/t1/taskio.py': 'd0877a64b6b0c9d1651ba0f43e11296ddc943411ba82dffc1bb99a49eacb2e21', 'finaldev/house.py': 'dbc4830efec62c2c68d269921f4eef26b008f31c4b70cebefdd7ec180a0b1e87'}
ARCHIVE_URL='https://codeload.github.com/Agenthon-2026/track1-coding-public/tar.gz/1f77390c1363047aea20d2e67bb31715ff5dbc53'
ARCHIVE_SHA256='184bbe9923dca3fe08990fc7dad9fd3d7ce1ecd3dcd97c2b8651fc19e4528fce'
assert platform.system()=='Linux' and platform.machine()=='x86_64','Native x86_64 Linux host required'
ROOT=Path.cwd();WORK=ROOT/'validation-output';WORK.mkdir(exist_ok=False)
results=[]
def command(label,args,timeout=120):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 (WORK/(label+'.log')).write_text(p.stdout+p.stderr)
 if p.returncode: print('FAILED_CHECK='+label+'\n'+p.stdout+p.stderr,flush=True)
 return p
pull=command('pull',['docker','pull',IMAGE],300);assert pull.returncode==0,'Anonymous image pull failed'
meta=json.loads(command('inspect',['docker','image','inspect',IMAGE]).stdout)[0]
assert meta['Architecture']=='amd64' and meta['Os']=='linux'
assert meta['Config'].get('Labels',{}).get('qfbench2.interface_version')=='2.0' and not meta['Config'].get('Volumes')
def run(label,args,mounts=(),timeout=150):
 name='v9-native-'+label+'-'+str(time.time_ns())
 base=['docker','run','--rm','--name',name,'--network=none','--read-only','--user','1000:1000','--cap-drop=ALL','--security-opt=no-new-privileges','--cpus=2','--memory=4g','--pids-limit=512','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=1g']
 for mount in mounts:base+=['-v',mount]
 try:return command(label,base+args,timeout)
 finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
probe="import pathlib,hashlib,json; r=pathlib.Path('/agent'); f="+repr(list(EXPECTED_SOURCES))+"; print(json.dumps({p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in f}))"
p=run('source-hashes',['--entrypoint','python',IMAGE,'-c',probe]);assert p.returncode==0 and json.loads(p.stdout)==EXPECTED_SOURCES
results.append({'check':'frozen_v9_source_hashes','passed':True})
p=run('numeric-imports',['--entrypoint','python',IMAGE,'-c',"import numpy,pandas,scipy.stats,numba,arch,pyarrow; from tracks.t1 import quant; print('numeric_imports_ok')"]);assert p.returncode==0,'Numeric imports failed'
results.append({'check':'numeric_imports','passed':True})
p=run('cli-help',[IMAGE,'solve','--help']);assert p.returncode==0
results.append({'check':'cli_help','passed':True})
EXPECTED_UNIT_HASHES={'card.toml': '7efda91bb4336fb9632fe33027e4df9defd830fb3b42a0053c463217badc23ae', 'checks/test.sh': '039ed310de430f1941f419d0b17e17396676de113248ccab9195a43b36ea412c', 'checks/test_outputs.py': 'e3fd43cccf31a4e2d743098c20a5acf13a6be6cf422891f59ae3d40adec2bdd5', 'environment/Dockerfile': 'ee026bb23083d503f6ad58fdaee2bc889135b475fe3a830262b89632e3c69365', 'environment/data/options.parquet': '9e9464abd1aa3935ee4857f2112b6d4b79d60ca3e1ee2081ba2976f488e8f156', 'instruction.md': 'aa65cc320e5f3c01a759f951f80c39a1ccafb6a378cd08af2c46043bf5fa936a', 'manifest.json': 'f2394924c2ec10bed4d7fc2628ffdc1b6058fc38ec21f18b787bcc2e323e49e3'}
unit=WORK/'official-unit';unit.mkdir()
for relative,expected in EXPECTED_UNIT_HASHES.items():
 url='https://raw.githubusercontent.com/Agenthon-2026/track1-coding-public/1f77390c1363047aea20d2e67bb31715ff5dbc53/units/t1-EXAMPLE-bs-greeks-pde/'+relative
 with urllib.request.urlopen(url,timeout=60) as response:payload=response.read(8*1024*1024+1)
 assert len(payload)<=8*1024*1024 and hashlib.sha256(payload).hexdigest()==expected,'Official exemplar file hash mismatch'
 target=unit/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
print('OFFICIAL_EXEMPLAR_FILES_MATCH_LOCKED_SNAPSHOT=7/7',flush=True)
staged=WORK/'staged-input';shutil.copytree(unit,staged,ignore=shutil.ignore_patterns('checks','solution','solutions','reference','references','reference_data'))
scorer="""import json,pathlib,tomllib
from qfbench2_common.manifest import verify_manifest
from qfbench2_track_coding.scoring import build_verifier
u=pathlib.Path('/unit');assert not verify_manifest(u)
c=tomllib.loads((u/'card.toml').read_text())
ctx={'unit_dir':u,'output_dir':pathlib.Path('/candidate'),'agent_timeout_sec':c['agent']['timeout_sec'],'canary_registry':{c.get('contamination',{}).get('canary_guid','')}-{''}}
v=build_verifier(ctx).run(ctx)
print(json.dumps({'admissible':v.admissible,'gates':{k:g.passed for k,g in v.gate_results.items()},'labels':[x.value for x in v.labels]}))
"""
for negative in (False,True):
 label='negative' if negative else 'positive';out=WORK/(label+'-output');out.mkdir();out.chmod(0o777)
 p=run(label+'-agent',['-e','PROBE_NEGATIVE='+str(int(negative)),'--entrypoint','python',IMAGE,'/fixture_probe.py'],[str(staged)+':/input:ro',str(out)+':/output',str(out)+':/app/output',str(ROOT/'fixture_probe.py')+':/fixture_probe.py:ro'],450)
 agent_rc=p.returncode
 p=run(label+'-grader',['--entrypoint','python',IMAGE,'-c',scorer],[str(unit)+':/unit:ro',str(out)+':/candidate:ro'],330)
 assert p.returncode==0,'Original checker did not complete'
 verdict=json.loads(p.stdout.strip().splitlines()[-1])
 passed=(agent_rc==0 and (not verdict['admissible'] and verdict['gates'].get('g1_schema') is True and verdict['gates'].get('g3_domain_semantics') is False if negative else verdict['admissible']))
 results.append({'check':label+'_fixture_original_grader','passed':bool(passed),'agent_exit_code':agent_rc,'verdict':verdict})
 assert passed,label+' fixture failed'
report={'passed':True,'native_amd64_validated':True,'host_machine':platform.machine(),'host_system':platform.system(),'image':IMAGE,'runtime_sources_match':True,'original_t1_archive_sha256':ARCHIVE_SHA256,'official_exemplar_files_match_locked_snapshot':True,'checks':results,'real_house':False,'model_performance_test':False,'paid_calls':0,'submitted':False}
(WORK/'native-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('NATIVE_VALIDATION_RESULT='+json.dumps(report),flush=True)
summary=os.environ.get('GITHUB_STEP_SUMMARY')
if summary:Path(summary).write_text('# T1 v9 native amd64 validation\n\nAll source, import, CLI and original positive/negative checks passed. No model calls or competition upload.\n\nImage: `'+IMAGE+'`\n')
