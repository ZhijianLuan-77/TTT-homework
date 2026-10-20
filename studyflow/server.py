"""StudyFlow: dependency-free SQLite-backed full-stack course project."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT / 'data')))
DATABASE = Path(os.environ.get('DATABASE_PATH', str(DATA_DIR / 'studyflow.sqlite3')))
MAX_BODY = 65536
SESSION_SECONDS = 7 * 86400
PROJECT_COLORS = ('violet', 'sky', 'mint', 'peach')
STATUSES = ('todo', 'doing', 'done')
PRIORITIES = ('high', 'medium', 'low')

def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

@contextmanager
def db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    # Autocommit before returning HTTP responses, so follow-up requests see writes immediately.
    con = sqlite3.connect(DATABASE, timeout=10, isolation_level=None)
    try:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=10000')
        yield con
    finally:
        con.close()

def init_db():
    with db() as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo', priority TEXT NOT NULL DEFAULT 'medium',
            due_date TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            minutes INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_focus_user_date ON focus_sessions(user_id, created_at);
        ''')

def hashed_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 260000)
    return f'{salt.hex()}:{digest.hex()}'

def check_password(password, encoded):
    try:
        salt, digest = encoded.split(':', 1)
        guess = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000)
        return hmac.compare_digest(guess, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

def clean_text(obj, field, maximum, *, required=False, default=''):
    value = obj.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f'{field} 必须是文本')
    value = value.strip()
    if len(value) > maximum or (required and not value):
        raise ValueError(f'{field} 长度不符合要求（1–{maximum} 字）')
    return value

def clean_date(value):
    if value in ('', None):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('日期格式应为 YYYY-MM-DD')
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise ValueError('日期无效') from None
    return value

def rowdict(row):
    return dict(row) if row else None

def seed_user(con, user_id):
    now = utcnow()
    p1 = con.execute('INSERT INTO projects(user_id,title,description,color,created_at) VALUES(?,?,?,?,?)',
        (user_id, '课程项目开发', '从需求到部署，完整实践软件工程流程', 'violet', now)).lastrowid
    p2 = con.execute('INSERT INTO projects(user_id,title,description,color,created_at) VALUES(?,?,?,?,?)',
        (user_id, '本周学习计划', '知识积累、任务跟进与效率复盘', 'sky', now)).lastrowid
    samples = [
        (p1, '整理项目需求与用户故事', 'done', 'high', -2),
        (p1, '完成前后端接口设计', 'done', 'high', -1),
        (p1, '实现数据库持久化与权限校验', 'doing', 'high', 1),
        (p1, '编写自动化测试用例', 'doing', 'medium', 2),
        (p1, '部署并验证线上访问', 'todo', 'high', 3),
        (p1, '录制完整项目演示视频', 'todo', 'medium', 4),
        (p2, '总结本周阅读与收获', 'todo', 'low', 2),
        (p2, '完成一组算法练习', 'done', 'medium', -1),
    ]
    for proj, title, status, priority, delta in samples:
        due = (datetime.now().date() + timedelta(days=delta)).isoformat()
        con.execute('''INSERT INTO tasks(user_id,project_id,title,status,priority,due_date,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)''', (user_id, proj, title, status, priority, due, now, now))
    con.execute('INSERT INTO notes(user_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)',
        (user_id, '项目开发日志', '## 本周目标\n\n- 完成需求分析和系统设计\n- 实现可运行的前后端\n- 用自动化测试验证关键功能\n\n保持持续迭代，每天都有可见的进步。', now, now))
    for day, mins in ((0, 45), (-1, 65), (-2, 25), (-3, 50), (-5, 40)):
        stamp = (datetime.now(timezone.utc) + timedelta(days=day)).replace(microsecond=0).isoformat()
        con.execute('INSERT INTO focus_sessions(user_id,minutes,note,created_at) VALUES(?,?,?,?)',
            (user_id, mins, '专注学习', stamp))

class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

class Handler(BaseHTTPRequestHandler):
    server_version = 'StudyFlow/1.0'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (self.log_date_time_string(), fmt % args))

    def respond(self, status=200, data=None, *, cookie=None, content_type='application/json; charset=utf-8'):
        body = json.dumps(data if data is not None else {}, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, message):
        self.respond(status, {'error': message})

    def body(self):
        origin = self.headers.get('Origin')
        if origin:
            host = self.headers.get('Host', '')
            parsed = urlsplit(origin)
            if parsed.netloc != host or parsed.scheme not in ('http', 'https'):
                raise APIError(403, '拒绝跨站修改请求')
        if self.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
            raise APIError(415, '请求需要 application/json')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BODY:
                raise APIError(413, '请求内容过大或为空')
            result = json.loads(self.rfile.read(size))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise APIError(400, 'JSON 请求格式无效') from None

    def cookie_token(self):
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
        except Exception:
            return None
        return jar['sf_session'].value if 'sf_session' in jar else None

    def user(self, con, required=True):
        token = self.cookie_token()
        if token and re.fullmatch(r'[a-f0-9]{64}', token):
            match = con.execute('''SELECT users.id,users.username FROM users JOIN sessions
                ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires_at>?''',
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
            if match:
                return dict(match)
        if required:
            raise APIError(401, '请先登录')
        return None

    def set_session(self, con, user_id):
        token = secrets.token_hex(32)
        con.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)',
            (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + SESSION_SECONDS))
        secure = '; Secure' if self.headers.get('X-Forwarded-Proto', '') == 'https' else ''
        return f'sf_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_SECONDS}{secure}'

    def route(self):
        path = urlsplit(self.path).path
        if path == '/api/health' and self.command == 'GET':
            return self.respond(200, {'ok': True, 'service': 'StudyFlow', 'database': 'SQLite'})
        if not path.startswith('/api/'):
            return self.static(path)
        with db() as con:
            if path == '/api/auth/me' and self.command == 'GET':
                return self.respond(200, {'user': self.user(con, required=False)})
            if path == '/api/auth/register' and self.command == 'POST':
                data = self.body()
                username = clean_text(data, 'username', 32, required=True)
                password = data.get('password')
                if not re.fullmatch(r'[\w\u4e00-\u9fff]{2,32}', username):
                    raise APIError(400, '用户名须为 2–32 位中文、字母、数字或下划线')
                if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
                    raise APIError(400, '密码须为 8–128 位')
                try:
                    user_id = con.execute('INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)',
                        (username, hashed_password(password), utcnow())).lastrowid
                except sqlite3.IntegrityError:
                    raise APIError(409, '该用户名已被注册') from None
                seed_user(con, user_id)
                return self.respond(201, {'user': {'id': user_id, 'username': username}}, cookie=self.set_session(con, user_id))
            if path == '/api/auth/login' and self.command == 'POST':
                data = self.body()
                username = clean_text(data, 'username', 32)
                password = data.get('password', '')
                row = con.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                if not isinstance(password, str) or not row or not check_password(password, row['password_hash']):
                    raise APIError(401, '用户名或密码不正确')
                return self.respond(200, {'user': {'id': row['id'], 'username': row['username']}}, cookie=self.set_session(con, row['id']))
            if path == '/api/auth/logout' and self.command == 'POST':
                self.body()
                token = self.cookie_token()
                if token:
                    con.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
                return self.respond(200, {'ok': True}, cookie='sf_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')
            user = self.user(con)
            uid = user['id']
            if path == '/api/dashboard' and self.command == 'GET':
                tasks = con.execute('SELECT status,priority,due_date FROM tasks WHERE user_id=?', (uid,)).fetchall()
                focus = con.execute('SELECT minutes,created_at FROM focus_sessions WHERE user_id=?', (uid,)).fetchall()
                dates = [(datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
                by_date = {date: 0 for date in dates}
                for f in focus:
                    key = f['created_at'][:10]
                    if key in by_date:
                        by_date[key] += f['minutes']
                today = datetime.now().date().isoformat()
                stats = {
                    'total': len(tasks), 'done': sum(t['status'] == 'done' for t in tasks),
                    'doing': sum(t['status'] == 'doing' for t in tasks),
                    'overdue': sum(bool(t['due_date'] and t['due_date'] < today and t['status'] != 'done') for t in tasks),
                    'focus_minutes': sum(f['minutes'] for f in focus),
                    'projects': con.execute('SELECT COUNT(*) FROM projects WHERE user_id=?', (uid,)).fetchone()[0],
                    'notes': con.execute('SELECT COUNT(*) FROM notes WHERE user_id=?', (uid,)).fetchone()[0],
                    'weekly_focus': [{'date': k, 'minutes': v} for k, v in by_date.items()],
                }
                return self.respond(200, stats)
            if path == '/api/export' and self.command == 'GET':
                bundle = {key: [dict(r) for r in con.execute(f'SELECT * FROM {table} WHERE user_id=? ORDER BY id', (uid,))]
                          for key, table in [('projects', 'projects'), ('tasks', 'tasks'), ('notes', 'notes'), ('focus_sessions', 'focus_sessions')]}
                return self.respond(200, {'version': 1, 'exported_at': utcnow(), 'data': bundle})
            if path == '/api/projects':
                if self.command == 'GET':
                    rows = con.execute('''SELECT p.*, COUNT(t.id) task_count,
                        COALESCE(SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END),0) done_count
                        FROM projects p LEFT JOIN tasks t ON t.project_id=p.id AND t.user_id=p.user_id
                        WHERE p.user_id=? GROUP BY p.id ORDER BY p.id DESC''', (uid,)).fetchall()
                    return self.respond(200, {'items': [dict(x) for x in rows]})
                if self.command == 'POST':
                    data = self.body()
                    title = clean_text(data, 'title', 80, required=True)
                    desc = clean_text(data, 'description', 400)
                    color = data.get('color', 'violet')
                    if color not in PROJECT_COLORS:
                        raise APIError(400, '颜色值无效')
                    new_id = con.execute('INSERT INTO projects(user_id,title,description,color,created_at) VALUES(?,?,?,?,?)',
                                         (uid, title, desc, color, utcnow())).lastrowid
                    return self.respond(201, {'id': new_id})
            if path == '/api/tasks':
                if self.command == 'GET':
                    rows = con.execute('''SELECT t.*,p.title project_title,p.color project_color FROM tasks t
                        LEFT JOIN projects p ON p.id=t.project_id AND p.user_id=t.user_id
                        WHERE t.user_id=? ORDER BY CASE t.status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END,
                        t.id DESC''', (uid,)).fetchall()
                    return self.respond(200, {'items': [dict(x) for x in rows]})
                if self.command == 'POST':
                    d = self.body()
                    title = clean_text(d, 'title', 120, required=True)
                    desc = clean_text(d, 'description', 1000)
                    status = d.get('status', 'todo')
                    priority = d.get('priority', 'medium')
                    if status not in STATUSES or priority not in PRIORITIES:
                        raise APIError(400, '任务状态或优先级无效')
                    due = clean_date(d.get('due_date'))
                    proj = self.project_id(con, uid, d.get('project_id'))
                    now = utcnow()
                    new_id = con.execute('''INSERT INTO tasks(user_id,project_id,title,description,status,priority,due_date,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?)''', (uid, proj, title, desc, status, priority, due, now, now)).lastrowid
                    return self.respond(201, {'id': new_id})
            if path == '/api/notes':
                if self.command == 'GET':
                    rows = con.execute('SELECT * FROM notes WHERE user_id=? ORDER BY updated_at DESC,id DESC', (uid,)).fetchall()
                    return self.respond(200, {'items': [dict(x) for x in rows]})
                if self.command == 'POST':
                    d = self.body()
                    title = clean_text(d, 'title', 120, required=True)
                    content = clean_text(d, 'content', 12000)
                    now = utcnow()
                    new_id = con.execute('INSERT INTO notes(user_id,title,content,created_at,updated_at) VALUES(?,?,?,?,?)',
                        (uid, title, content, now, now)).lastrowid
                    return self.respond(201, {'id': new_id})
            if path == '/api/focus':
                if self.command == 'GET':
                    rows = con.execute('SELECT * FROM focus_sessions WHERE user_id=? ORDER BY id DESC LIMIT 30', (uid,)).fetchall()
                    return self.respond(200, {'items': [dict(x) for x in rows]})
                if self.command == 'POST':
                    d = self.body()
                    minutes = d.get('minutes')
                    if type(minutes) is not int or not (1 <= minutes <= 240):
                        raise APIError(400, '专注时长必须为 1–240 分钟')
                    note = clean_text(d, 'note', 120)
                    new_id = con.execute('INSERT INTO focus_sessions(user_id,minutes,note,created_at) VALUES(?,?,?,?)',
                                         (uid, minutes, note, utcnow())).lastrowid
                    return self.respond(201, {'id': new_id})
            match = re.fullmatch(r'/api/(projects|tasks|notes)/(\d+)', path)
            if match and self.command in ('PATCH', 'DELETE'):
                table, item_id = match.group(1), int(match.group(2))
                old = con.execute(f'SELECT * FROM {table} WHERE id=? AND user_id=?', (item_id, uid)).fetchone()
                if not old:
                    raise APIError(404, '记录不存在')
                if self.command == 'DELETE':
                    con.execute(f'DELETE FROM {table} WHERE id=? AND user_id=?', (item_id, uid))
                    return self.respond(200, {'ok': True})
                d = self.body()
                if not d:
                    raise APIError(400, '没有提供更新字段')
                allowed = {'tasks': ('title','description','status','priority','due_date','project_id'),
                           'projects': ('title','description','color'), 'notes': ('title','content')}[table]
                if any(key not in allowed for key in d):
                    raise APIError(400, '包含不支持的字段')
                out = {}
                for key in d:
                    if key in ('title', 'description', 'content'):
                        limit = {'title': 120 if table != 'projects' else 80,
                                 'description': 1000 if table == 'tasks' else 400, 'content': 12000}[key]
                        out[key] = clean_text(d, key, limit, required=key == 'title')
                    elif key == 'status':
                        if d[key] not in STATUSES: raise APIError(400, '状态无效')
                        out[key] = d[key]
                    elif key == 'priority':
                        if d[key] not in PRIORITIES: raise APIError(400, '优先级无效')
                        out[key] = d[key]
                    elif key == 'color':
                        if d[key] not in PROJECT_COLORS: raise APIError(400, '颜色无效')
                        out[key] = d[key]
                    elif key == 'due_date':
                        out[key] = clean_date(d[key])
                    elif key == 'project_id':
                        out[key] = self.project_id(con, uid, d[key])
                if table in ('tasks', 'notes'):
                    out['updated_at'] = utcnow()
                sets = ','.join(f'{key}=?' for key in out)
                con.execute(f'UPDATE {table} SET {sets} WHERE id=? AND user_id=?', (*out.values(), item_id, uid))
                return self.respond(200, {'ok': True})
            raise APIError(404, '接口不存在')

    def project_id(self, con, uid, value):
        if value is None or value == '':
            return None
        if type(value) is not int or value < 1:
            raise APIError(400, '项目编号无效')
        if not con.execute('SELECT 1 FROM projects WHERE id=? AND user_id=?', (value, uid)).fetchone():
            raise APIError(400, '项目不存在或无权访问')
        return value

    def static(self, path):
        paths = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/favicon.svg': 'favicon.svg'}
        name = paths.get(path)
        if not name:
            raise APIError(404, '页面不存在')
        file = WEB / name
        mime = 'text/html' if name.endswith('.html') else 'text/javascript' if name.endswith('.js') else 'text/css' if name.endswith('.css') else 'image/svg+xml'
        body = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if not name.endswith('.svg') else ''))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.handle_request()
    def do_POST(self):
        self.handle_request()
    def do_PATCH(self):
        self.handle_request()
    def do_DELETE(self):
        self.handle_request()
    def handle_request(self):
        try:
            return self.route()
        except APIError as exc:
            return self.error(exc.status, exc.message)
        except ValueError as exc:
            return self.error(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self.log_message('Unhandled server error: %s', __import__('traceback').format_exc())
            return self.error(500, '服务器发生错误，请稍后重试')

if __name__ == '__main__':
    init_db()
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8001'))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f'StudyFlow ready: http://{host}:{port} (database: {DATABASE})', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()