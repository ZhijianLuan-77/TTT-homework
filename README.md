# 汤甜甜 · AI编程实训课程作品集

本项目包含个人作品集首页、进阶待办、Markdown笔记、天气查询、倒计时和随机点名六个模块，以及软件规格、技术设计、软件测试、部署、操作手册五类工程文档。

**公开源码：** https://github.com/ZhijianLuan-77/TTT-homework

**Cloudflare Pages 部署地址：** https://ttt-homework.pages.dev/ （2026-10-16 Cloudflare 后台显示部署成功，需通过公开浏览器确认访问）。

**备用 GitHub Pages 目标地址：** https://zhijianluan-77.github.io/TTT-homework/ （如未开启，则不是当前正式交付网址）。

**运行：** `python start_server.py`（或Windows双击`启动项目.bat`）。

**测试：** `npm test` 与 `python tests/http_smoke.py`。已核验33项单元测试和6项HTTP资源检查。

课程报告和五类文档提供HTML线上阅读页面；PDF版本位于离线交付包。项目所有者：汤甜甜；代码托管账户经授权借用。此项目的界面及项目材料不含账户所有者本人的科研经历。

**实际课程考核保留事项：** AI零代码平台实操、Cursor实际操作记录、节点问卷及现场答辩、出勤仍需学生本人完成。

## 个人展示与本地内容管理（课程新增）

- 标准需求文档：[PRD.md](PRD.md)
- 技术设计文档：[TECH_DESIGN.md](TECH_DESIGN.md)
- AI开发约定：[AGENTS.md](AGENTS.md)
- 前台新增个人技能与学习博客展示；通过 [admin/](admin/) 打开内容管理页面，修改首页介绍、技能标签、五个项目介绍和博客。
- **限制说明：** 内容管理使用浏览器 `localStorage`，更新只保存于当前浏览器；它属于静态网站的演示型管理功能，不是带身份认证、数据库和跨设备同步的远程后台。
- 新增 `tests/site-content.test.mjs` 对数据校验与本地保存行为提供自动化测试。

### Cloudflare Pages 部署（已创建）

在平台授权 GitHub 仓库 `ZhijianLuan-77/TTT-homework`，选用静态 HTML 项目（Other/None），不需要安装依赖或设置 build 命令，发布目录为仓库根目录。部署后应实际打开网站首页和 `/admin/` 验证，并将平台分配的可访问域名提交给老师。

## 新增课堂工具

倒计时：设置小时、分钟、秒或选择快捷时长，支持开始、暂停、继续、重置及可选到时提示音。

随机点名：根据课程截图预置30位同学的姓名，支持编辑名单、每轮无重复抽取、记录及重新抽取。名单与记录保存在当前浏览器，须在使用前核对截图识别姓名。

新增9项单元测试，累计33项。

## GitHub About

本项目的仓库介绍应为“汤甜甜的生成式大模型辅助编程实训作品集，包含待办事项、Markdown笔记、天气查询、倒计时、随机点名及工程文档。”


## 期末综合考核：StudyFlow 全栈项目（2026-10-20）

本仓库新增独立项目 [`studyflow/`](studyflow/) —— StudyFlow 全栈学习项目管理系统，包含原生 JavaScript 前端、Python REST API、SQLite 数据库、用户登录、任务看板、项目管理、笔记、专注计时、学习数据统计、8 组集成测试，以及独立 PRD/技术设计/测试报告与录屏脚本。

**本地启动：** `cd studyflow && python server.py`，浏览器打开 `http://127.0.0.1:8001/` 并创建账号。**运行测试：** `cd studyflow && python -m unittest discover -s tests -v`。仓库根目录 `render.yaml` 与 `studyflow/Dockerfile` 提供 Render 部署配置，公开云端地址需完成实际平台部署后验证。新增代码没有替换仓库根目录原有的课程作品集网站。
