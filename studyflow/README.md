# StudyFlow｜全栈学习项目管理系统

**全栈课程项目（独立于仓库根目录的旧静态站）**：前端 HTML/CSS/JavaScript + Python 标准库 REST API + SQLite 持久化数据库。无需 pip/npm 安装包。

## 本地一键启动

要求 Python 3.10+。在本目录执行：

```bash
python server.py
```

打开 **http://127.0.0.1:8001/** ，点击「立即注册」，新账号自动创建演示项目、任务、笔记、专注历史；可以直接演示真实数据增删改查。数据库自动生成在 `studyflow/data/studyflow.sqlite3`，退出程序后仍保留，再次登录即可验证。

Windows 用户可以双击仓库内本目录的 `启动StudyFlow.bat`；macOS/Linux 可执行 `python3 server.py`。

## 核心模块

| 模块 | 功能与数据库实现 |
| --- | --- |
| 用户认证 | 注册、登录、登出、密码 PBKDF2+随机盐、HttpOnly 会话 Cookie、SQLite sessions 表 |
| 综合仪表盘 | 任务总数、完成数、进行中、专注时长、进度等后端聚合数据 |
| 任务看板 | 多状态看板（待开始/进行中/已完成）、优先级、项目归属、截止日期、筛选、搜索、编辑、删除 |
| 项目管理 | 创建、编辑、删除项目、完成进度自动统计；删除项目不删除独立任务 |
| 学习笔记 | 个人笔记保存、更新、删除、SQLite 存储 |
| 专注空间 | 15/25/45 分钟番茄钟、手动补录、自动记录、个人时间轨迹 |
| 数据分析 | 最近七日时长图、任务状态占比、逾期统计 |
| 数据备份 | 一键导出当前登录用户的项目、任务、笔记和专注记录 JSON |

## 自动化测试

```bash
python -m unittest discover -s tests -v
```

测试采用临时 SQLite 文件与**真实本地 HTTP 服务器**，包括认证、跨用户授权隔离、增删改查、聚合统计、输入校验、CSRF Origin 拒绝、注入字符串等。无需任何第三方测试依赖。

## 部署配置

提供 `Dockerfile` 和 `render.yaml`，可在 Render 通过 GitHub 仓库部署：

1. 打开 [Render Dashboard](https://dashboard.render.com/) → **New → Blueprint**，授权本仓库 `ZhijianLuan-77/TTT-homework`；仓库根目录已提供 `render.yaml` Blueprint 文件。
2. 平台读取仓库根目录的 `render.yaml` 后将使用 `studyflow` 作为服务根目录、Docker 作为运行环境；也可在 **New → Web Service** 手动配置对应参数。实际生成地址以平台反馈为准。
3. 创建完成后检查 `/api/health` 和首页能访问，并新建独立测试账号。

**重要：** Render 免费实例的容器文件系统不保证持久保存；该项目默认 SQLite 写入容器内本地目录，重部署/实例重建可能丢失线上记录。生产持续存储需选择支持持久磁盘的付费服务，将 `DATA_DIR` 设置为挂载路径，或改造为平台托管数据库。**不能将免费部署当作可靠的永久数据库。** 在课堂录制中建议先用本地 SQLite 演示持久性和账号隔离，再展示实际部署地址（如已完成部署）。

旧站点保持不变：`https://zhijianluan-77.github.io/TTT-homework/` 或 `https://ttt-homework.pages.dev/` 需现场在浏览器验证实际可达。

## 数据与安全说明

各用户数据在 SQL 查询及 UPDATE/DELETE 中均以 `user_id` 限定。数据写入使用参数化 SQL。登录 session 只在 HttpOnly Cookie 中；密码不以明文存储；同源 JSON 接口对有 Origin 的修改请求做同源检查。教学系统未包含密码找回、邮件验证、限流、防爆破及后台运维能力；对公众开放前应补充这些防护。

## 文档与交付

见 `docs/PRD.md`、`docs/TECH_DESIGN.md`、`docs/TEST_REPORT.md`、`docs/演示与录屏脚本.md`。`data/` 与账号数据未纳入 GitHub。演示学生信息与学校班级学号应由实际提交者核实填写。