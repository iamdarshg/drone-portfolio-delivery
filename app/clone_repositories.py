"""Explicit, read-only-source cloning utility. Never executes cloned code."""
import argparse
import json
import os
import shutil
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

REPOS = ('drone-arm', 'drone-mech')
def command(*args):
    return ['git', '-c', 'core.hooksPath=', '-c', 'init.templateDir=', '-c', 'submodule.recurse=false', *args]
def git_environment():
    environment={key:value for key,value in os.environ.items() if not key.startswith('GIT_')}
    environment.update({'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,'GIT_TERMINAL_PROMPT':'0'})
    return environment
def run(destination, dry_run=False, repo_url=None):
    destination=Path(destination).expanduser().resolve()
    repositories=[(name,'https://github.com/iamdarshg/'+name+'.git') for name in REPOS]
    if repo_url:
        match=re.fullmatch(r'https://github\.com/iamdarshg/([A-Za-z0-9_-][A-Za-z0-9_.-]*?)(?:\.git)?',repo_url)
        if not match or match[1] in {'.','..'}:raise ValueError('Only HTTPS GitHub repositories owned by iamdarshg are supported')
        repositories=[(match[1],'https://github.com/iamdarshg/'+match[1]+'.git')]
    if dry_run:
        for name,url in repositories:
            print(json.dumps({'destination':str(destination/name),'command':command('clone','--no-recurse-submodules','--',url,str(destination/name))}))
        return 0
    if not shutil.which('git'):
        print('Git is not installed. No repositories changed. Install Git manually or download source ZIPs:')
        for name,url in repositories:print('https://github.com/iamdarshg/'+name+' (Code > Download ZIP)')
        return 1
    destination.mkdir(parents=True,exist_ok=True)
    records=[]
    for name,url in repositories:
        target=destination/name
        if target.exists():
            print('Skipped existing destination:',target)
            records.append({'repository':name,'status':'skipped-existing','destination':str(target)})
            continue
        try:
            subprocess.run(command('clone','--no-recurse-submodules','--',url,str(target)),check=True,timeout=600,env=git_environment())
            commit=subprocess.check_output(command('-C',str(target),'rev-parse','HEAD'),text=True,timeout=15,env=git_environment()).strip()
            records.append({'repository':name,'status':'cloned','destination':str(target),'commit':commit,'fetched_at':datetime.now(timezone.utc).isoformat()})
            print(name,commit)
        except (subprocess.SubprocessError,OSError) as error:
            print('Clone incomplete; existing files preserved:',name,type(error).__name__)
            records.append({'repository':name,'status':'failed-preserved','destination':str(target)})
    report=destination/'clone-results.json'
    if not report.exists():report.write_text(json.dumps(records,indent=2))
    else:print('Existing clone-results.json preserved; current results:',json.dumps(records,indent=2))
    return int(any(r['status']=='failed-preserved' for r in records))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Clone public source repositories; no repository code is executed.')
    parser.add_argument('--destination',type=Path,default=Path(__file__).resolve().parent/'repos')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--repo-url',help='Explicit delivery repository HTTPS URL owned by iamdarshg; no URL is guessed')
    args=parser.parse_args()
    raise SystemExit(run(args.destination,args.dry_run,args.repo_url))
