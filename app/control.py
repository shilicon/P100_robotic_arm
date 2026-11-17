"""Start/stop only this deployment; local HTTP requests bypass system proxies."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from settings import load_config, prepare_directories

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config()
BASE = 'http://127.0.0.1:' + str(CONFIG['port'])
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, post=False):
    req = urllib.request.Request(BASE + path, data=b'' if post else None,
        headers={'Authorization': 'Bearer ' + CONFIG['api_key']})
    with HTTP.open(req, timeout=5) as response:
        return json.load(response)


def status():
    try:
        result = request('/health')
        if result.get('service') != 'rig-local-voice':
            raise RuntimeError('Port is occupied by another service')
        return result
    except (OSError, TimeoutError):
        return None


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'start'
    current = status()
    if action == 'status':
        print(json.dumps(current or {'ready': False}, ensure_ascii=False, indent=2))
        return
    if action == 'stop':
        if current:
            request('/local/shutdown', post=True)
            for _ in range(50):
                if status() is None:
                    print('Local voice services stopped.')
                    return
                time.sleep(0.2)
            raise RuntimeError('Shutdown is still in progress; inspect logs/server.log')
        print('Local voice services are already stopped.')
        return
    if action != 'start':
        raise ValueError('Expected start, stop, or status')
    if current:
        print('Local voice services are already ready: ' + BASE + '/health')
        return
    if os.name != "nt":
        raise RuntimeError("Live inference and Windows TTS require Windows; offline tests support other platforms")
    prepare_directories()
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    with (ROOT / 'logs' / 'server.log').open('ab') as log:
        process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'app/server.py')],
            cwd=ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError('Service exited; inspect logs/server.log')
        ready = status()
        if ready and ready.get('ready'):
            print('Local voice services ready: ' + BASE + '/health')
            print('Robot endpoint: http://' + CONFIG['lan_host'] + ':' + str(CONFIG['port']))
            return
        time.sleep(1)
    raise RuntimeError('Startup is still in progress; inspect logs/server.log')


if __name__ == '__main__':
    main()
