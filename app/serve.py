"""Loopback-only read-only GitHub workspace. Python standard library."""
import argparse
import datetime as dt
import http.server
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPOS = {'drone-arm', 'drone-mech'}
MAX_BYTES = 1500000
LOCK = threading.Lock()
CACHE = ROOT / '.cache'
def expiry():
    return dt.datetime.fromisoformat(json.loads((ROOT/'config.json').read_text())['expires_at'].replace('Z','+00:00'))
def expired(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)) >= expiry()
def remote(url):
    request=urllib.request.Request(url,headers={'User-Agent':'DroneEngineeringLocal/1.0','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=10) as response:
        data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES: raise ValueError('Preview size limit exceeded')
        return data
def write_cache(path,data):
    CACHE.mkdir(exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)
def snapshot(name, refresh=False):
    path=CACHE/(name+'.json')
    if path.exists() and (not refresh or time.time()-path.stat().st_mtime<20):
        result=json.loads(path.read_text());result['origin']='cached';return result
    try:
        api='https://api.github.com/repos/iamdarshg/'+name
        info=json.loads(remote(api)); commit=json.loads(remote(api+'/commits/'+urllib.parse.quote(info['default_branch'],safe='')))
        tree=json.loads(remote(api+'/git/trees/'+commit['sha']+'?recursive=1'))
        entries=[{'path':e['path'],'size':e.get('size',0),'type':e['type']} for e in tree['tree'] if e['type'] in {'blob','tree'}]
        result={'name':name,'commit':commit['sha'],'branch':info['default_branch'],'date':commit['commit']['committer']['date'],'origin':'latest','truncated':bool(tree.get('truncated')) or len(entries)>6000,'tree':entries[:6000]}
        with LOCK: write_cache(path,json.dumps(result).encode())
        return result
    except Exception:
        if path.exists():
            result=json.loads(path.read_text());result['origin']='cached';return result
        data=json.loads((ROOT/'data.json').read_text());repo=next(r for r in data['repositories'] if r['name']==name)
        return {**repo,'origin':'bundled','date':None,'tree':[{'path':f['path'],'size':0,'type':'blob'} for f in repo['files']]}
def directory(name,commit,path):
    import hashlib
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('Invalid commit')
    if len(path)>400 or '..' in path.split('/') or path.startswith('/') or '\\' in path:raise ValueError('Invalid path')
    cache=CACHE/(hashlib.sha256((name+'/'+commit+'/directory/'+path).encode()).hexdigest()+'.json')
    if cache.exists():return json.loads(cache.read_text())
    response=json.loads(remote('https://api.github.com/repos/iamdarshg/'+name+'/contents/'+urllib.parse.quote(path,safe='/')+'?ref='+commit))
    if not isinstance(response,list):raise ValueError('Not a directory')
    result={'entries':[{'path':e['path'],'size':e.get('size',0),'type':'tree' if e['type']=='dir' else 'blob'} for e in response[:1000] if e['type'] in {'dir','file'}],'limited':len(response)>=1000}
    with LOCK:write_cache(cache,json.dumps(result).encode())
    return result
def file_bytes(name,commit,path):
    import hashlib
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit): raise ValueError('Invalid commit')
    if not path or len(path)>400 or '..' in path.split('/') or path.startswith('/') or '\\' in path: raise ValueError('Invalid path')
    key=hashlib.sha256((name+'/'+commit+'/'+path).encode()).hexdigest()
    cached=CACHE/(key+'.txt')
    if cached.exists():return cached.read_bytes()
    try:
        data=remote('https://raw.githubusercontent.com/iamdarshg/'+name+'/'+commit+'/'+urllib.parse.quote(path,safe='/'))
        if len(list(CACHE.glob('*.txt'))) < 100:
            with LOCK:write_cache(cached,data)
        return data
    except Exception:
        data=json.loads((ROOT/'data.json').read_text());repo=next(r for r in data['repositories'] if r['name']==name)
        match=next((f for f in repo['files'] if f['path']==path and repo['commit']==commit),None)
        if match:return (ROOT/match['cache']).read_bytes()
        raise
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        url=urllib.parse.urlsplit(self.path)
        decoded=urllib.parse.unquote(url.path)
        if any(part.startswith('.') for part in decoded.split('/') if part):
            self.send_error(404);return
        if url.path.startswith('/api/'):
            if expired():self.send_error(410);return
            args=urllib.parse.parse_qs(url.query)
            try:
                name=args.get('repo',[''])[0]
                if name not in REPOS:raise ValueError('Unknown repository')
                if url.path=='/api/snapshot':payload=json.dumps(snapshot(name,args.get('refresh',['0'])[0]=='1')).encode();mime='application/json'
                elif url.path=='/api/directory':payload=json.dumps(directory(name,args.get('commit',[''])[0],args.get('path',[''])[0])).encode();mime='application/json'
                elif url.path=='/api/file':payload=file_bytes(name,args.get('commit',[''])[0],args.get('path',[''])[0]);mime='text/plain; charset=utf-8'
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            except Exception as error:self.send_error(502,str(type(error).__name__))
            return
        super().do_GET()
def run(port=8765,open_browser=False):
    if expired():raise SystemExit('Dynamic app expired 2027-10-01 UTC. Static files remain available via python -m http.server --bind 127.0.0.1.')
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    def shutdown_at_expiry():
        while not expired():time.sleep(min(1,max(.01,(expiry()-dt.datetime.now(dt.timezone.utc)).total_seconds())))
        server.shutdown()
    threading.Thread(target=shutdown_at_expiry,daemon=True).start()
    address='http://127.0.0.1:'+str(server.server_port)
    print(address,flush=True)
    if open_browser:webbrowser.open(address)
    try:server.serve_forever()
    finally:server.server_close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('port',nargs='?',type=int,default=8765);parser.add_argument('--open',action='store_true');args=parser.parse_args();run(args.port,args.open)
