"""Container-only HTTP plumbing fixture. Never copied into the submission image.

The responder is scripted, NOT House or another model. Its one exemplar computation
tests transport/execution/official grading together; it is not a solve-rate experiment.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

SOLUTION = '''import os
from pathlib import Path
import pandas as pd
from tracks.t1.quant import bs_greeks
root,out=Path(os.environ['INPUT_DIR']),Path(os.environ['OUTPUT_DIR'])
df=pd.read_parquet(root/'environment/data/options.parquet')
g=bs_greeks(df['S'],df['K'],df['T'],df['r'],df['sigma'],df['option_type'])
result=pd.DataFrame({'option_id':df.option_id,**{k:g[k] for k in ['price','delta','gamma','vega','theta']}})
result['theta']/=365
result.to_parquet(out/'results.parquet',index=False)
'''
CHECK = '''import os,math
from pathlib import Path
import pandas as pd
from scipy.stats import norm
root,out=Path(os.environ['INPUT_DIR']),Path(os.environ['OUTPUT_DIR'])
df=pd.read_parquet(root/'environment/data/options.parquet')
res=pd.read_parquet(out/'results.parquet')
assert list(res.option_id)==list(df.option_id)
assert res[['price','delta','gamma','vega','theta']].notna().all().all()
for row,actual in zip(df.itertuples(),res.itertuples()):
    S,K,T,r,v=row.S,row.K,row.T,row.r,row.sigma
    d1=(math.log(S/K)+(r+v*v/2)*T)/(v*math.sqrt(T))
    d2=d1-v*math.sqrt(T)
    sign=1 if row.option_type=='call' else -1
    price=sign*(S*norm.cdf(sign*d1)-K*math.exp(-r*T)*norm.cdf(sign*d2))
    assert abs(actual.price-price)<1e-8
'''


class Handler(BaseHTTPRequestHandler):
    count = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        assert self.path == "/v1/chat/completions"
        assert self.headers["Authorization"] == "Bearer synthetic-fixture-token"
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["max_tokens"] <= 4000
        assert request["model"] == "scripted-fixture-not-house"
        assert not request.get("tools")
        assert len(request["messages"]) >= 2
        Handler.count += 1
        code = SOLUTION
        if os.environ.get('PROBE_NEGATIVE') == '1':
            code = code.replace("result.to_parquet", "result['price']=-1.0\nresult.to_parquet")
        response = ({"action":"solve", "code":code,"self_check":CHECK}
                    if Handler.count == 1 else {"action":"check","code":CHECK})
        payload = json.dumps({"choices":[{"message":{"content":json.dumps(response)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    assert Path("/.dockerenv").exists()
    server = HTTPServer(("127.0.0.1",0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    env = {**os.environ,"MODEL_ENDPOINT":f"http://127.0.0.1:{server.server_port}",
           "MODEL_NAME":"scripted-fixture-not-house","MODEL_TOKEN":"synthetic-fixture-token",
           "NO_PROXY":"127.0.0.1,localhost"}
    try:
        proc = subprocess.run([sys.executable,"/agent/tracks/t1/agent.py","solve",
                               "--task-dir","/input","--out","/output"],env=env,timeout=150)
        print(json.dumps({"fixture_http_requests":Handler.count,"real_house":False}),flush=True)
        return proc.returncode
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
