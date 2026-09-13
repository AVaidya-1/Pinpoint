"""Read account limits through Codex app-server; never start a model turn."""
import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import threading
import time


def summarize(result):
    buckets = result.get('rateLimitsByLimitId')
    bucket = buckets.get('codex') if buckets is not None else result.get('rateLimits')
    if not bucket:
        return {'available': None, 'reset_at': None}
    windows = [bucket.get(k) for k in ('primary', 'secondary')]
    blocked = [w for w in windows if w and w.get('usedPercent') is not None and w['usedPercent'] >= 100]
    resets = [w.get('resetsAt') for w in blocked]
    reset = None
    if blocked and all(isinstance(r, (int, float)) for r in resets):
        reset = dt.datetime.fromtimestamp(max(resets), dt.timezone.utc).isoformat()
    known = all(w and w.get('usedPercent') is not None for w in windows)
    available = False if blocked else (True if known and not bucket.get('rateLimitReachedType') and not bucket.get('spendControlReached') else None)
    return {'available': available, 'reset_at': reset}


def read_limits(timeout=20):
    executable = shutil.which('codex.cmd' if os.name == 'nt' else 'codex')
    if not executable:
        raise RuntimeError('Codex CLI not found')
    process = subprocess.Popen([executable, 'app-server'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8',
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    messages = queue.Queue()
    def reader():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
    def response(identifier):
        while True:
            message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if message.get('id') == identifier:
                if 'error' in message:
                    raise RuntimeError('Account limits request rejected')
                return message['result']
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'agent-orchestration_usage', 'version': '1.0'}}})
        response(1)
        send({'method': 'initialized'})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        return summarize(response(2))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5)
            else:
                process.kill()
            process.wait(timeout=5)


if __name__ == '__main__':
    try:
        status = read_limits()
    except (OSError, RuntimeError, queue.Empty, subprocess.SubprocessError):
        status = {'available': None, 'reset_at': None}
    status['checked_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    status['source'] = 'Codex account/rateLimits/read'
    print(json.dumps(status))
