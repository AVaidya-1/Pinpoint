"""Loopback dashboard and durable owner-to-Director console. Standard library only."""
import argparse
import ctypes
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser
import urllib.request
import socket


class DashboardServer(ThreadingHTTPServer):
    allow_reuse_address = False
    director_dispatcher = None

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def service_actions(self):
        # serve_forever calls this independently of browser refreshes, so a
        # queued message is answered after the supervisor becomes idle even if
        # the owner closes the dashboard tab.
        if self.director_dispatcher:
            self.director_dispatcher.tick()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / 'out/orchestration/runtime'
MESSAGE_ID = re.compile(r'^\d{17}_[a-f0-9]{32}$')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read_messages(directory):
    messages = []
    for path in sorted((directory / 'memory/messages').glob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError, OSError):
            continue
        if not isinstance(value, dict) or not MESSAGE_ID.fullmatch(str(value.get('id', ''))):
            continue
        messages.append(value)
    return messages


def director_conversation(directory):
    result = []
    for message in read_messages(directory):
        owner_to_director = message.get('from') == 'Owner' and message.get('to') == 'Director'
        director_to_owner = message.get('from') == 'Director' and message.get('to') == 'Owner'
        if owner_to_director or director_to_owner:
            result.append({key: message.get(key, '') for key in
                           ('id', 'from', 'to', 'task', 'kind', 'body', 'reply_to', 'created')})
    return result[-40:]


def pending_director_messages(directory):
    messages = read_messages(directory)
    answered = {str(item.get('reply_to', '')) for item in messages
                if item.get('from') == 'Director' and item.get('to') == 'Owner'}
    return [item for item in messages
            if item.get('from') == 'Owner' and item.get('to') == 'Director'
            and item.get('id') not in answered]


def create_owner_message(directory, body, kind):
    body = str(body).strip()
    if kind not in ('QUESTION', 'DECISION'):
        raise ValueError('Choose question or direction.')
    if not body or len(body) > 3000:
        raise ValueError('Message must contain 1–3,000 characters.')
    message_id = datetime.now().strftime('%Y%m%d%H%M%S%f')[:17] + '_' + uuid.uuid4().hex
    message = dict(id=message_id, from_='Owner', to='Director', task='OWNER-CONSOLE',
                   kind=kind, body=body, evidence=[], reply_to='',
                   created=datetime.now().astimezone().isoformat())
    message['from'] = message.pop('from_')
    path = directory / 'memory/messages' / f'{message_id}.json'
    write_json(path, message)
    markdown = (f"# {kind} | {message_id}\nFrom: Owner\nTo: Director\n"
                f"Task: OWNER-CONSOLE\nReply-To: \n\n{body}\n\nEvidence: ")
    path.with_suffix('.md').write_text(markdown, encoding='utf-8')
    if kind == 'DECISION':
        write_json(directory / 'director-execution.json',
                   dict(status='AWAITING_DIRECTOR', message_id=message_id,
                        updated=datetime.now().astimezone().isoformat()))
    return message


class DirectorDispatcher:
    """Runs at most one idle-time Director response process."""
    def __init__(self, directory):
        self.directory = directory
        self.guard = threading.Lock()
        self.process = None
        self.supervisor_process = None
        self.pause_process = None

    def request_pause(self):
        """Owner control must remain available even while a model is quota-limited."""
        with self.guard:
            if self.pause_process is not None and self.pause_process.poll() is None:
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            command = [os.environ.get('SystemRoot', r'C:\Windows') + r'\System32\WindowsPowerShell\v1.0\powershell.exe',
                       '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts/team_control.ps1'),
                       '-Action', 'pause', '-RuntimeDirectory', str(self.directory)]
            log_path = self.directory / 'app-pause.log'
            with log_path.open('ab') as log:
                self.pause_process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                                      stdout=log, stderr=log,
                                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            write_json(self.directory / 'director-execution.json', {'status':'PAUSED', 'message':'Owner requested pause through the app.'})
            write_json(self.directory / 'app-control.json', {'status':'PAUSING', 'log':str(log_path),
                       'updated':datetime.now().astimezone().isoformat()})

    def _finish_pause(self):
        if self.pause_process is None or self.pause_process.poll() is None:
            return
        code = self.pause_process.returncode
        write_json(self.directory / 'app-control.json', {'status':'PAUSED' if code == 0 else 'ERROR',
                   'message':'Safe pause confirmed.' if code == 0 else 'Pause did not confirm shutdown safety. Inspect app-pause.log.',
                   'updated':datetime.now().astimezone().isoformat()})
        self.pause_process = None

    def _finish_supervisor(self):
        if self.supervisor_process is None or self.supervisor_process.poll() is None:
            return False
        exit_code = self.supervisor_process.returncode
        self.supervisor_process = None
        path = self.directory / 'director-execution.json'
        try:
            record = json.loads(path.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, ValueError, OSError):
            record = {}
        record.update(status='FINISHED' if exit_code == 0 else 'ERROR', exit_code=exit_code,
                      updated=datetime.now().astimezone().isoformat())
        write_json(path, record)
        return True

    def _start_directed_work(self):
        if self.pause_process is not None:
            return
        path = self.directory / 'director-execution.json'
        try:
            record = json.loads(path.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, ValueError, OSError):
            return
        if record.get('status') != 'AWAITING_DIRECTOR':
            return
        message_id = str(record.get('message_id', ''))
        replies = [item for item in read_messages(self.directory)
                   if item.get('from') == 'Director' and item.get('to') == 'Owner'
                   and item.get('reply_to') == message_id]
        if not replies:
            return
        director_action = ''
        action_match = re.match(r'^\s*DIRECTION:\s*(QUEUE|REPLAN|PAUSE)\s*(?:\r?\n|$)',
                                str(replies[0].get('body', '')), re.IGNORECASE)
        if action_match:
            director_action = action_match.group(1).upper()
        owner_message = next((item for item in read_messages(self.directory)
                              if item.get('id') == message_id and item.get('from') == 'Owner'), None)
        if owner_message and owner_message.get('kind') == 'DECISION' and not director_action:
            record.update(status='ERROR', error='The Director did not classify this direction as QUEUE, REPLAN, or PAUSE.',
                          updated=datetime.now().astimezone().isoformat())
            write_json(path, record)
            return
        current = snapshot(self.directory, include_console=False)
        runtime = current.get('runtime', {})
        active = runtime.get('status') in ('RUNNING', 'STARTING', 'QUOTA-WAIT', 'RETRY-WAIT',
                                           'REPAIRING', 'DIRECTOR-RECOVERY-WAIT', 'FOREMAN1-HOLD')
        if active and current.get('alive') is not False:
            return
        if director_action == 'PAUSE':
            record.update(status='PAUSED',
                          message='The Director paused dispatch. The dashboard will not restart work until the owner resumes it.',
                          updated=datetime.now().astimezone().isoformat())
            write_json(path, record)
            return
        hard_stop = self.directory / 'hard-stop.json'
        hard_stop_record = {}
        try:
            hard_stop_record = json.loads(hard_stop.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, ValueError, OSError):
            pass
        director_hard_stop = (hard_stop_record.get('role') == 'Director'
                              and hard_stop_record.get('status') in ('DONE', 'BLOCKED'))
        if director_hard_stop:
            if director_action != 'REPLAN':
                record.update(status='BLOCKED', error='A hard stop requires an owner direction classified by the Director as REPLAN.',
                              updated=datetime.now().astimezone().isoformat())
                write_json(path, record)
                return
            archive = self.directory / 'logs' / f'owner-replan-{message_id}-hard-stop.json'
            archive.parent.mkdir(parents=True, exist_ok=True)
            os.replace(hard_stop, archive)
            record['replaced_hard_stop'] = str(archive)
        command = [
            os.environ.get('SystemRoot', r'C:\Windows') + r'\System32\WindowsPowerShell\v1.0\powershell.exe',
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(ROOT / 'scripts/team_control.ps1'), '-Action', 'resume'
        ]
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            self.supervisor_process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            record.update(status='STARTED', pid=self.supervisor_process.pid,
                          updated=datetime.now().astimezone().isoformat())
            write_json(path, record)
            write_json(self.directory / 'app-control.json', {'status':'RUNNING', 'message':''})
        except OSError as error:
            record.update(status='ERROR', error=f'Could not start the supervisor: {error}',
                          updated=datetime.now().astimezone().isoformat())
            write_json(path, record)

    def tick(self):
        with self.guard:
            self._finish_pause()
            self._finish_supervisor()
            if self.process is not None:
                if self.process.poll() is None:
                    return
                self.process = None
            pending = pending_director_messages(self.directory)
            if not pending:
                self._start_directed_work()
                return
            record_path = self.directory / 'director-console.json'
            try:
                record = json.loads(record_path.read_text(encoding='utf-8-sig'))
            except (FileNotFoundError, ValueError, OSError):
                record = {}
            failed_id = record.get('message_id') if record.get('status') == 'ERROR' else None
            # Do not hammer a terminally failed message, but do not let it block
            # newer owner messages from reaching the Director.
            eligible = [item for item in pending if item.get('id') != failed_id]
            if not eligible:
                return
            next_message = eligible[0]
            command = [
                os.environ.get('SystemRoot', r'C:\Windows') + r'\System32\WindowsPowerShell\v1.0\powershell.exe',
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT / 'scripts/director_console.ps1'),
                '-RuntimeDirectory', str(self.directory), '-MessageId', str(next_message['id'])
            ]
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            try:
                self.process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                creationflags=flags)
            except OSError as error:
                write_json(record_path, dict(status='ERROR', message_id=next_message['id'],
                                             error=f'Could not start the Director: {error}',
                                             updated=datetime.now().astimezone().isoformat()))


def process_alive(pid, started):
    if os.name != 'nt':
        return None
    # Match creation time as well as PID; Windows can reuse exited process IDs.
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    try:
        values = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(wintypes.HANDLE(handle), *[ctypes.byref(v) for v in values]):
            return None
        created = ((values[0].dwHighDateTime << 32) + values[0].dwLowDateTime) / 10000000 - 11644473600
        return created <= datetime.fromisoformat(started).timestamp()
    finally:
        kernel.CloseHandle(wintypes.HANDLE(handle))


def snapshot(directory, include_console=True):
    warnings = []
    def read(name, default=None):
        try:
            return json.loads((directory / name).read_text(encoding='utf-8-sig'))
        except FileNotFoundError:
            return default
        except (ValueError, OSError):
            warnings.append(f'Cannot read {name}; awaiting a valid update.')
            return default
    def tail(path, size=18000):
        try:
            with path.open('rb') as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - size))
                return stream.read(size).decode('utf-8-sig', errors='replace')
        except OSError:
            return ''
    runtime = read('runtime.json', {}) or {}
    alive = None
    try:
        alive = process_alive(runtime['supervisor_pid'], runtime['run_started'])
    except (KeyError, ValueError, TypeError, OSError):
        pass
    status = runtime.get('status', 'NOT-STARTED')
    if alive is False and status in ('RUNNING', 'STARTING', 'QUOTA-WAIT', 'RETRY-WAIT'):
        status = 'INTERRUPTED'
    log = ''
    if runtime.get('log_file'):
        path = Path(runtime['log_file']).resolve()
        # Never serve arbitrary paths from a tampered runtime record.
        if path.is_relative_to(directory.resolve()):
            log = tail(path)
    tasks = read('state.json', []) or []
    if isinstance(tasks, dict):
        tasks = [tasks]
    console = read('director-console.json', {}) or {}
    if include_console:
        console['messages'] = director_conversation(directory)
        console['pending_count'] = len(pending_director_messages(directory))
        console['execution'] = read('director-execution.json', {}) or {}
    return dict(application='agent-orchestration-team-dashboard', directory=str(directory.resolve()), now=datetime.now(timezone.utc).isoformat(), runtime=runtime,
                status=status, alive=alive, stop=(directory / 'STOP.txt').exists(),
                tasks=tasks, context=read('memory/last_packet.json', {}),
                pending=read('pending-operation.json'),
                providers={p: read(f'usage-{p}.json') for p in ('anthropic', 'openai', 'opencode')},
                handoffs=tail(directory / 'communications.md', 30000),
                questions=tail(directory / 'OWNER_QUESTIONS.md', 8000),
                log=log, console=console, controls=read('app-control.json', {}),
                models=read_product_models(), warnings=warnings)


def read_product_models():
    try:
        return json.loads((ROOT / 'orchestration.json').read_text(encoding='utf-8-sig')).get('models', {})
    except (ValueError, OSError):
        return {}


def make_handler(directory, dispatcher=None):
    class Handler(BaseHTTPRequestHandler):
        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def send_json(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.allowed_host():
                self.send_error(403)
                return
            if self.path == '/api/status':
                if dispatcher:
                    dispatcher.tick()
                data = json.dumps(snapshot(directory)).encode()
                kind = 'application/json'
            elif self.path == '/':
                data = (ROOT / 'scripts/dashboard/index.html').read_bytes()
                kind = 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self.allowed_host() or self.path not in ('/api/director/messages', '/api/control/pause'):
                self.send_error(403 if not self.allowed_host() else 404)
                return
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}',
                               f'http://localhost:{self.server.server_port}')
            if self.headers.get('Origin') not in allowed_origins:
                self.send_error(403)
                return
            if self.headers.get_content_type() != 'application/json':
                self.send_error(415)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if length < 2 or length > 12000:
                self.send_error(413)
                return
            try:
                value = json.loads(self.rfile.read(length).decode('utf-8'))
                if self.path == '/api/control/pause':
                    if not dispatcher:
                        self.send_json(409, {'error':'Control dispatcher is unavailable.'})
                        return
                    try:
                        dispatcher.request_pause()
                    except OSError as error:
                        self.send_json(500, {'error':str(error)})
                        return
                    self.send_json(202, {'status':'PAUSING'})
                    return
                kind = 'QUESTION' if value.get('type') == 'question' else 'DECISION' if value.get('type') == 'direction' else ''
                message = create_owner_message(directory, value.get('body', ''), kind)
            except (ValueError, UnicodeError, AttributeError) as error:
                self.send_json(400, {'error': str(error)})
                return
            if dispatcher:
                dispatcher.tick()
            self.send_json(202, {'id': message['id'], 'status': 'queued'})

        def log_message(self, *args):
            pass
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-directory', type=Path, default=DEFAULT)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    try:
        runtime_directory = args.runtime_directory.resolve()
        (runtime_directory / 'logs').mkdir(parents=True, exist_ok=True)
        dispatcher = DirectorDispatcher(runtime_directory)
        server = DashboardServer(('127.0.0.1', args.port), make_handler(runtime_directory, dispatcher))
        server.director_dispatcher = dispatcher
    except OSError:
        # Reopening the launcher reuses only our server for this runtime directory.
        url = f'http://127.0.0.1:{args.port}'
        try:
            with urllib.request.urlopen(url + '/api/status', timeout=2) as response:
                existing = json.load(response)
            if existing.get('application') != 'agent-orchestration-team-dashboard' or existing.get('directory') != str(args.runtime_directory.resolve()):
                raise ValueError('Different service or runtime directory')
        except Exception:
            parser.exit(1, 'Dashboard port is occupied. Choose another port with --port.\n')
        if args.open:
            webbrowser.open(url)
        parser.exit(0, f'Dashboard already running: {url}\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Team dashboard: {url}', flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
