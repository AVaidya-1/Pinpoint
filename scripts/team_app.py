"""Open the local control UI as a dedicated Edge/Chrome app window."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]

def service_identity(url, runtime):
    try:
        with urllib.request.urlopen(url + '/api/status', timeout=1) as response:
            value = json.load(response)
        return value.get('application') == 'agent-orchestration-team-dashboard' and value.get('directory') == str(runtime.resolve())
    except (OSError, ValueError):
        return False

def browser_command(url):
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if not base:
            continue
        for relative in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
            executable = Path(base) / relative
            if executable.is_file():
                return [str(executable), '--app=' + url]
    return None

def launch(port=8765):
    runtime = ROOT / 'out/orchestration/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    url = f'http://127.0.0.1:{port}'
    if not service_identity(url, runtime):
        output = ROOT / 'out/team-app-server.log'
        with output.open('ab') as log:
            server = subprocess.Popen([sys.executable, str(ROOT / 'scripts/team_dashboard.py'), '--port', str(port)],
                                      cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if service_identity(url, runtime):
                break
            if server.poll() is not None:
                raise RuntimeError(f'The dashboard could not start on port {port}. Another app may be using it. See {output}.')
            time.sleep(.2)
        else:
            raise RuntimeError(f'Dashboard startup did not finish. See {output}.')
    command = browser_command(url)
    if command:
        subprocess.Popen(command, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        webbrowser.open(url)
    return url

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError('Choose a port between 1024 and 65535.')
        launch(args.port)
    except Exception as error:
        (ROOT / 'out').mkdir(exist_ok=True)
        (ROOT / 'out/team-app-error.log').write_text(str(error), encoding='utf-8')
        import tkinter
        from tkinter import messagebox
        window = tkinter.Tk()
        window.withdraw()
        messagebox.showerror('Agent Orchestration', str(error), parent=window)
        window.destroy()
        raise SystemExit(1)
