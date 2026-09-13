import importlib.util
import http.client
import json
import threading
import tempfile
import unittest
import uuid
from unittest import mock
from datetime import datetime
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'team_dashboard.py'
SPEC = importlib.util.spec_from_file_location('team_dashboard', MODULE_PATH)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_owner_message_is_durable_and_pending(self):
        message = dashboard.create_owner_message(self.directory, 'What is next?', 'QUESTION')
        saved = json.loads((self.directory / 'memory/messages' / f"{message['id']}.json").read_text())
        self.assertEqual(saved['from'], 'Owner')
        self.assertEqual(saved['to'], 'Director')
        self.assertEqual([message['id']], [item['id'] for item in dashboard.pending_director_messages(self.directory)])

    def test_direction_is_queued_for_automatic_execution(self):
        message = dashboard.create_owner_message(self.directory, 'Continue the reviewed work.', 'DECISION')
        execution = json.loads((self.directory / 'director-execution.json').read_text())
        self.assertEqual('AWAITING_DIRECTOR', execution['status'])
        self.assertEqual(message['id'], execution['message_id'])

    def test_answered_direction_starts_supervisor(self):
        message = dashboard.create_owner_message(self.directory, 'Continue the reviewed work.', 'DECISION')
        reply_id = datetime.now().strftime('%Y%m%d%H%M%S%f')[:17] + '_' + uuid.uuid4().hex
        reply = {'id': reply_id, 'from': 'Director', 'to': 'Owner', 'task': 'OWNER-CONSOLE',
                 'kind': 'ANSWER', 'body': 'DIRECTION: QUEUE\nProceeding.', 'evidence': [],
                 'reply_to': message['id'], 'created': datetime.now().astimezone().isoformat()}
        dashboard.write_json(self.directory / 'memory/messages' / f'{reply_id}.json', reply)
        fake_process = mock.Mock(pid=4321)
        fake_process.poll.return_value = None
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        with mock.patch.object(dashboard.subprocess, 'Popen', return_value=fake_process) as launch:
            dispatcher._start_directed_work()
        execution = json.loads((self.directory / 'director-execution.json').read_text())
        self.assertEqual('STARTED', execution['status'])
        self.assertTrue(any(str(item).endswith('team_control.ps1') for item in launch.call_args.args[0]))
        self.assertIn('resume', launch.call_args.args[0])

    def test_replan_direction_replaces_hard_stop_and_restarts(self):
        message = dashboard.create_owner_message(self.directory, 'Replace the old goal.', 'DECISION')
        reply_id = datetime.now().strftime('%Y%m%d%H%M%S%f')[:17] + '_' + uuid.uuid4().hex
        dashboard.write_json(self.directory / 'memory/messages' / f'{reply_id}.json',
                             {'id': reply_id, 'from': 'Director', 'to': 'Owner', 'task': 'OWNER-CONSOLE',
                              'kind': 'ANSWER', 'body': 'DIRECTION: REPLAN\nThe old plan is superseded.',
                              'evidence': [], 'reply_to': message['id'],
                              'created': datetime.now().astimezone().isoformat()})
        dashboard.write_json(self.directory / 'hard-stop.json', {'status': 'BLOCKED', 'role': 'Director', 'reason': 'old'})
        fake_process = mock.Mock(pid=4321)
        fake_process.poll.return_value = None
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        with mock.patch.object(dashboard.subprocess, 'Popen', return_value=fake_process):
            dispatcher._start_directed_work()
        execution = json.loads((self.directory / 'director-execution.json').read_text())
        self.assertEqual('STARTED', execution['status'])
        self.assertFalse((self.directory / 'hard-stop.json').exists())
        self.assertTrue(Path(execution['replaced_hard_stop']).exists())

    def test_pause_direction_never_restarts_supervisor(self):
        message = dashboard.create_owner_message(self.directory, 'Pause safely now.', 'DECISION')
        reply_id = datetime.now().strftime('%Y%m%d%H%M%S%f')[:17] + '_' + uuid.uuid4().hex
        dashboard.write_json(self.directory / 'memory/messages' / f'{reply_id}.json',
                             {'id': reply_id, 'from': 'Director', 'to': 'Owner', 'task': 'OWNER-CONSOLE',
                              'kind': 'ANSWER', 'body': 'DIRECTION: PAUSE\nCheckpoint and hold.',
                              'evidence': [], 'reply_to': message['id'],
                              'created': datetime.now().astimezone().isoformat()})
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        with mock.patch.object(dashboard.subprocess, 'Popen') as launch:
            dispatcher._start_directed_work()
        execution = json.loads((self.directory / 'director-execution.json').read_text())
        self.assertEqual('PAUSED', execution['status'])
        launch.assert_not_called()

    def test_director_reply_closes_console_queue(self):
        message = dashboard.create_owner_message(self.directory, 'Use the reviewed plan.', 'DECISION')
        reply_id = datetime.now().strftime('%Y%m%d%H%M%S%f')[:17] + '_' + uuid.uuid4().hex
        reply = dict(id=reply_id, from_='Director', to='Owner',
                     task='OWNER-CONSOLE', kind='ANSWER', body='Acknowledged.', evidence=[],
                     reply_to=message['id'], created=datetime.now().astimezone().isoformat())
        reply['from'] = reply.pop('from_')
        dashboard.write_json(self.directory / 'memory/messages' / f"{reply['id']}.json", reply)
        self.assertEqual([], dashboard.pending_director_messages(self.directory))
        self.assertEqual(['Owner', 'Director'], [item['from'] for item in dashboard.director_conversation(self.directory)])

    def test_question_dispatches_while_supervisor_is_active(self):
        message = dashboard.create_owner_message(self.directory, 'What is happening now?', 'QUESTION')
        dashboard.write_json(self.directory / 'runtime.json',
                             {'status': 'RUNNING', 'role': 'Worker', 'action': 'active task',
                              'supervisor_pid': 1234, 'run_started': datetime.now().astimezone().isoformat()})
        fake_process = mock.Mock(pid=9876)
        fake_process.poll.return_value = None
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        with mock.patch.object(dashboard.subprocess, 'Popen', return_value=fake_process) as launch:
            dispatcher.tick()
        self.assertTrue(launch.called)
        command = launch.call_args.args[0]
        self.assertTrue(any(str(item).endswith('director_console.ps1') for item in command))
        self.assertIn(message['id'], command)

    def test_invalid_messages_are_rejected(self):
        for body, kind in [('', 'QUESTION'), ('x' * 3001, 'QUESTION'), ('hello', 'FINDING')]:
            with self.assertRaises(ValueError):
                dashboard.create_owner_message(self.directory, body, kind)

    def test_pause_uses_control_plane_without_model(self):
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        process = mock.Mock(pid=9876)
        process.poll.return_value = None
        with mock.patch.object(dashboard.subprocess, 'Popen', return_value=process) as launch:
            dispatcher.request_pause()
            dispatcher.request_pause()
            self.assertEqual(1, launch.call_count)
            self.assertIn('pause', launch.call_args.args[0])
            self.assertNotIn('codex', launch.call_args.args[0])
        self.assertEqual('PAUSING', dashboard.snapshot(self.directory)['controls']['status'])
        process.poll.return_value = 0
        process.returncode = 0
        dispatcher._finish_pause()
        self.assertEqual('PAUSED', dashboard.snapshot(self.directory)['controls']['status'])

    def test_failed_pause_never_claims_safety(self):
        dispatcher = dashboard.DirectorDispatcher(self.directory)
        process = mock.Mock(returncode=1)
        process.poll.return_value = 1
        dispatcher.pause_process = process
        dispatcher._finish_pause()
        self.assertEqual('ERROR', dashboard.snapshot(self.directory)['controls']['status'])

    def test_pause_endpoint_has_origin_protection(self):
        dispatcher = mock.Mock()
        server = dashboard.DashboardServer(('127.0.0.1', 0), dashboard.make_handler(self.directory, dispatcher))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            for origin, status in [('https://example.com', 403), (f'http://127.0.0.1:{server.server_port}', 202)]:
                connection.request('POST', '/api/control/pause', '{}', {'Content-Type':'application/json','Origin':origin})
                response = connection.getresponse()
                response.read()
                self.assertEqual(status, response.status)
            dispatcher.request_pause.assert_called_once()
        finally:
            server.shutdown()
            server.server_close()

    def test_same_origin_post_creates_message(self):
        server = dashboard.DashboardServer(('127.0.0.1', 0), dashboard.make_handler(self.directory))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps({'type': 'question', 'body': 'Are you available?'})
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            connection.request('POST', '/api/director/messages', body,
                               {'Content-Type': 'application/json',
                                'Origin': f'http://127.0.0.1:{server.server_port}'})
            response = connection.getresponse()
            value = json.loads(response.read())
            self.assertEqual(202, response.status)
            self.assertTrue(value['id'])
            self.assertEqual(1, len(dashboard.pending_director_messages(self.directory)))
        finally:
            server.shutdown()
            server.server_close()

    def test_cross_origin_post_is_rejected(self):
        server = dashboard.DashboardServer(('127.0.0.1', 0), dashboard.make_handler(self.directory))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            body = json.dumps({'type': 'question', 'body': 'Do not accept this.'})
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
            connection.request('POST', '/api/director/messages', body,
                               {'Content-Type': 'application/json', 'Origin': 'https://example.com'})
            response = connection.getresponse()
            response.read()
            self.assertEqual(403, response.status)
            self.assertEqual([], dashboard.pending_director_messages(self.directory))
        finally:
            server.shutdown()
            server.server_close()

    def test_chat_refresh_preserves_scrolled_position(self):
        page = (MODULE_PATH.parent / 'dashboard' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('followConversation', page)
        self.assertIn('followConversation?conversation.scrollHeight:priorScroll', page)
        self.assertNotIn("$('conversation').scrollTop=$('conversation').scrollHeight", page)


if __name__ == '__main__':
    unittest.main()
