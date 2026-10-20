# 技术设计文档｜StudyFlow V1.0

## 1. 总体架构

```text
Web 浏览器（HTML/CSS/原生 JavaScript）
       │  JSON over HTTP
       ▼
Python ThreadingHTTPServer（server.py）
       ├─ 认证 API：/api/auth/*
       ├─ 业务 API：/api/projects、/api/tasks、/api/notes、/api/focus
       ├─ 分析 API：/api/dashboard
       ├─ 导出 API：/api/export
       └─ 同源静态页面：/、/app.js、/styles.css
       │  sqlite3 参数化 SQL
       ▼
SQLite（users / sessions / projects / tasks / notes / focus_sessions）
```

## 2. 技术选型

| 层次 | 技术 | 理由 |
| --- | --- | --- |
| 前端 | 原生 JavaScript + HTML5 + CSS3 | 无需构建工具，迭代快速；能完整演示网络层 API 数据流 |
| 服务端 | Python 3 标准库 HTTP Server | 零第三方依赖、便于课程机器上立即启动；接口由服务端处理 |
| 数据层 | SQLite3 + 外键 + 索引 | 真实关系数据库、持久化、易迁移与可测试 |
| 登录 | PBKDF2-HMAC-SHA256 + 随机盐；Session Cookie | 密码安全摘要；会话 Hash 存储，Cookie HttpOnly + SameSite=Lax |
| 测试 | unittest + 临时 SQLite + HTTP Client | 真实网络请求覆盖核心业务，不依赖 mock API |
| 部署 | Dockerfile / Render Web Service | 统一运行环境，可按需配置端口和数据库目录 |

## 3. 表结构与业务规则

- `users`：`id` 主键、唯一 `username`、`password_hash`、`created_at`。
- `sessions`：SHA256 会话 token 哈希主键、`user_id` 外键、过期时间。
- `projects`：用户外键、标题、描述、颜色、创建时间。
- `tasks`：用户外键、可空 `project_id`、标题、描述、状态 `todo/doing/done`、优先级 `high/medium/low`、截止日期、创建和更新时间。删除项目时，将其任务 `project_id` 置空而非删除任务。
- `notes`：用户外键、标题、正文、创建和更新时间。
- `focus_sessions`：用户外键、专注分钟数、备注、时间戳。

写入时对项目所有权二次校验；任务与笔记修改、删除 SQL 必须带 `user_id`；阅读 SQL 按登录用户过滤。新增账户附带两条演示项目、八条任务、一条笔记和五条专注历史。

## 4. API 样例

| 方法 | 路径 | 业务 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册并建立会话 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 退出 |
| GET | `/api/auth/me` | 获取当前会话身份 |
| GET/POST | `/api/projects` | 项目列表、创建 |
| PATCH/DELETE | `/api/projects/{id}` | 修改、删除 |
| GET/POST | `/api/tasks` | 任务列表、创建 |
| PATCH/DELETE | `/api/tasks/{id}` | 修改状态、编辑、删除 |
| GET/POST | `/api/notes` | 笔记列表、创建 |
| PATCH/DELETE | `/api/notes/{id}` | 修改、删除 |
| GET/POST | `/api/focus` | 专注记录查询与新增 |
| GET | `/api/dashboard` | 任务和最近七日专注统计 |
| GET | `/api/export` | 用户个人数据 JSON 导出 |
| GET | `/api/health` | 服务健康检查 |

HTTP 401：未登录；400：字段校验失败；403：跨站修改请求；404：未知资源、无权访问的资源；409：账户重复；415：非 JSON 写请求。

## 5. 安全与一致性

- 密码 PBKDF2-HMAC-SHA256，26 万轮，加盐，每用户单独存储。
- Token 使用加密安全的 `secrets.token_hex(32)` 生成；数据库只存储 SHA256 摘要。
- Cookie 设置 HttpOnly、SameSite=Lax；经过 HTTPS 反向代理时可增加 Secure；服务上线应确保强制 HTTPS。
- 状态变更接口仅接收 JSON 请求，并核验浏览器 `Origin`（存在时）。
- 数据库启用 WAL 模式、外键、忙等待，数据库连接按请求创建并关闭。自动提交模式保证 HTTP 成功响应后，下一请求立即能读到修改。
- 输出文本由 `html()` 转义；SQL 使用 `?` 占位符，不拼接用户输入。
- 用户名可以包含中文、数字、字母、下划线，最长 32 字符；服务端实施所有字段长度与枚举合法性校验。

## 6. 部署及可用性说明

开发机：`python server.py`，默认 `127.0.0.1:8001`，数据库保存于 `data/studyflow.sqlite3`。容器：`Dockerfile`，由 `HOST=0.0.0.0` 与 `PORT` 配置监听地址和端口；`DATA_DIR` 或 `DATABASE_PATH` 可指定 SQLite 数据位置。

在 Render 免费容器环境，写入本地 SQLite 不应被等同于持久云存储。若演示数据需要跨重启长期保持，需挂载持久磁盘或者迁移到管理型数据库。课程验收的视频以本地数据库读写和真实平台展示为准。