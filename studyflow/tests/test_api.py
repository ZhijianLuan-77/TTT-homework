"""Integration tests against a real HTTP server and a disposable SQLite database."""
import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import server

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DATABASE = Path(cls.tmp.name) / 'test.sqlite3'
        server.init_db()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=3)
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, method='GET', data=None, client=None, headers=None):
        opener = client or self.client
        payload = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        request = urllib.request.Request(self.url + path, data=payload, method=method,
                headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with opener.open(request, timeout=4) as r:
                content = r.read()
                return r.status, json.loads(content) if content else None
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def register(self, username, client=None):
        return self.request('/api/auth/register', 'POST',
              {'username': username, 'password': 'SecurePassword2026'}, client)

    def test_01_health_static_and_first_visit(self):
        self.assertTrue(self.request('/api/health')[1]['ok'])
        with urllib.request.urlopen(self.url + '/') as res:
            self.assertIn(b'StudyFlow', res.read())
        self.assertIsNone(self.request('/api/auth/me')[1]['user'])
        self.assertEqual(self.request('/api/tasks')[0], 401)

    def test_02_registration_creates_seeded_data_and_session(self):
        status, data = self.register('student01')
        self.assertEqual(status, 201)
        self.assertEqual(data['user']['username'], 'student01')
        self.assertEqual(self.request('/api/projects')[0], 200)
        self.assertEqual(len(self.request('/api/tasks')[1]['items']), 8)
        self.assertEqual(self.request('/api/dashboard')[1]['done'], 3)

    def test_03_login_logout_and_invalid_password(self):
        self.register('student02')
        self.assertEqual(self.request('/api/auth/logout', 'POST', {})[0], 200)
        self.assertEqual(self.request('/api/tasks')[0], 401)
        self.assertEqual(self.request('/api/auth/login', 'POST', {'username':'student02','password':'invalid'} )[0], 401)
        self.assertEqual(self.request('/api/auth/login', 'POST', {'username':'student02','password':'SecurePassword2026'} )[0], 200)
        self.assertEqual(self.request('/api/tasks')[0], 200)

    def test_04_crud_tasks_projects_notes_focus_export(self):
        self.register('student03')
        st, p = self.request('/api/projects','POST',{'title':'软件工程项目','description':'研究课程内容','color':'sky'})
        self.assertEqual(st, 201)
        st, t = self.request('/api/tasks', 'POST', {'title':'编写验收文档','priority':'high','project_id':p['id'],'due_date':'2026-10-23'})
        self.assertEqual(st, 201)
        tid=t['id']
        self.assertEqual(self.request(f'/api/tasks/{tid}', 'PATCH', {'status':'done'})[0],200)
        record=next(x for x in self.request('/api/tasks')[1]['items'] if x['id']==tid)
        self.assertEqual(record['status'], 'done')
        st,n=self.request('/api/notes', 'POST', {'title':'测试笔记','content':'真实数据库持久化'})
        self.assertEqual(st,201)
        self.assertEqual(self.request(f"/api/notes/{n['id']}",'PATCH',{'title':'新标题'})[0],200)
        self.assertEqual(self.request('/api/focus', 'POST', {'minutes':25,'note':'高效学习'})[0],201)
        bundle=self.request('/api/export')[1]['data']
        self.assertTrue(any(x['id']==tid for x in bundle['tasks']))
        self.assertTrue(any(x['title']=='新标题' for x in bundle['notes']))
        self.assertEqual(self.request(f'/api/tasks/{tid}', 'DELETE')[0],200)
        self.assertEqual(self.request(f'/api/notes/{n["id"]}', 'DELETE')[0],200)
        self.assertEqual(self.request(f'/api/projects/{p["id"]}', 'DELETE')[0],200)
        self.assertEqual(self.request(f'/api/tasks/{tid}', 'PATCH', {'status':'todo'})[0],404)

    def test_05_cross_account_isolation_on_get_modify_delete(self):
        first=self.client
        self.register('student04',first)
        p=self.request('/api/projects','POST', {'title':'秘密项目'},first)[1]['id']
        other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.register('student05',other)
        self.assertFalse(any(x['id']==p for x in self.request('/api/projects',client=other)[1]['items']))
        self.assertEqual(self.request(f'/api/projects/{p}', 'PATCH', {'title':'攻击'},other)[0],404)
        self.assertEqual(self.request(f'/api/projects/{p}', 'DELETE',client=other)[0],404)
        self.assertTrue(any(x['id']==p for x in self.request('/api/projects',client=first)[1]['items']))
        self.assertFalse(any(x['id']==p for x in self.request('/api/export',client=other)[1]['data']['projects']))

    def test_06_strict_validation_and_no_sql_injection(self):
        self.register('student06')
        self.assertEqual(self.request('/api/tasks', 'POST', {'title':'','status':'todo'})[0],400)
        self.assertEqual(self.request('/api/tasks', 'POST', {'title':'test','project_id':999999})[0],400)
        self.assertEqual(self.request('/api/tasks', 'POST', {'title':'test','due_date':'2026-02-30'})[0],400)
        self.assertEqual(self.request('/api/focus','POST',{'minutes':0})[0],400)
        self.assertEqual(self.request('/api/focus','POST',{'minutes':True})[0],400)
        self.assertEqual(self.request('/api/auth/register','POST',{'username':'student06','password':'SecurePassword2026'})[0],409)
        st, created = self.request('/api/tasks', 'POST', {'title':"'); DROP TABLE users; --"})
        self.assertEqual(st, 201)
        self.assertEqual(self.request('/api/auth/me')[0],200)
        self.assertEqual(self.request(f"/api/tasks/{created['id']}",'PATCH',{'user_id':42})[0],400)

    def test_07_origin_check_and_content_type_enforced(self):
        self.register('student07')
        self.assertEqual(self.request('/api/tasks','POST',{'title':'cross site'},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/tasks','POST',{'title':'right origin'},headers={'Origin':self.url})[0],201)
        self.assertEqual(self.request('/api/tasks','POST',{'title':'non-json'},headers={'Content-Type':'text/plain'})[0],415)

    def test_08_aggregate_stats_and_project_delete_preserves_task(self):
        self.register('student08')
        proj=self.request('/api/projects','POST',{'title':'临时项目'})[1]['id']
        task=self.request('/api/tasks','POST',{'title':'转为独立任务','project_id':proj})[1]['id']
        self.request(f'/api/projects/{proj}','DELETE')
        entry=next(x for x in self.request('/api/tasks')[1]['items'] if x['id']==task)
        self.assertIsNone(entry['project_id'])
        stats=self.request('/api/dashboard')[1]
        self.assertEqual(stats['total'],9)
        self.assertEqual(len(stats['weekly_focus']),7)

if __name__=='__main__':
    unittest.main(verbosity=2)