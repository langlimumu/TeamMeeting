# Team Loop

Team Loop 是面向技术项目团队的轻量协作与周例会系统。后端使用模块化 Python 标准库服务和 SQLite，前端使用原生 HTML/CSS/JavaScript，适合在 Windows 单机或局域网环境快速部署。

## 主要能力

- 可配置多级组织树、层级独立路由、上级安排向下透传、跨团队协作可见范围与 SSO 群组自动归属
- 团队成员拖动排序、用户类型、模块操作权限、独立业务参与名单与批量账号管理
- 个人工作台和跨日继承的早例会事项，已完成事项保留至下一个工作日回顾
- 脑图式树形/并行流程模板、必做/可选节点、个人流程生成与依赖进度跟踪
- 会议沙盘、两级预设议题、开始时间、弹窗签到、纪要与可选 Thank You 邮件模板
- 白夜班月历排班、批量排班和工时统计
- 红黑榜细则、月度/年度积分看板、个人历史与黑榜可见性控制
- Thank You 多人感谢与月度/年度排名，候选人和看板严格限定当前团队层级
- 常用链接归档、搜索、标签、质量和访问量管理
- 论坛式团队讨论区：主题分类、搜索排序、楼中回复、快捷回应、本地完整 Emoji、作者编辑删除与回收恢复
- 全局搜索、年度归档、审计日志、备份校验与恢复
- 灰度发布、正式发布和数据库回滚
- 引导式企业 OAuth2/OIDC SSO 配置（授权码 + PKCE）、华为云 OneAccess 工号关联、连接池、自动建号、建议团队与管理员确认；未分类账号仅有访客只读权限
- Nginx HTTPS 反向代理、公共域名接入、可信代理真实 IP，以及生产登录和写操作的 HTTPS 强制校验

## 五分钟启动

1. 安装 Python 3.10 或更高版本。
2. 双击 `start_hot_server.bat` 启动开发模式，或双击 `start_server.bat` 启动正式模式。
3. 浏览器访问 `http://127.0.0.1:8000/`。
4. 首次登录后，由管理员在“用户管理”和“系统管理”中完成账号、权限与系统名称配置。

项目不依赖 pip 或 npm 安装。首次启动会自动创建并迁移 `data/weekly_team.db`。

后端默认启用 SQLite WAL、15 秒写锁等待和最多 64 个活动请求线程，按约 100 人同时在线的读多写少场景设计。数据库必须放在服务器本地磁盘，不能放在 SMB/NAS 共享目录。

## 文档入口

- [文档导航](docs/README.md)
- [使用手册](docs/USER_GUIDE.md)
- [Windows 部署与运维](docs/DEPLOYMENT.md)
- [二次开发指南](docs/DEVELOPMENT.md)
- [HTTP API 参考](docs/API.md)
- [数据库与备份](docs/DATABASE.md)
- [常见问题](docs/TROUBLESHOOTING.md)
- [本地业务知识库与 AI 问答接入](docs/KNOWLEDGE_BASE.md)
- [Team Loop 维护 Skill](skills/team-loop-maintainer/SKILL.md)

## 常用命令

```powershell
# 开发热更新
python scripts\dev_server.py --host 0.0.0.0 --port 8000

# 单次启动
python server.py --host 0.0.0.0 --port 8000

# 只执行数据库迁移
python server.py --migrate-only

# 部署灰度环境
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Gray

# 灰度提升为正式版本
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Promote

# 查看部署状态
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Status
```

正式环境默认使用 8000 端口，灰度环境默认使用 8001 端口。灰度数据库是正式数据库的一致性快照，灰度操作不会写回正式数据库。

公共域名部署使用 `scripts\nginx_proxy.ps1` 生成并管理 Nginx 配置。正式服务应监听 `127.0.0.1:8000`，由 Nginx 对外开放 80/443；完整命令、证书和 SSO 回调设置见 [Windows 部署与运维](docs/DEPLOYMENT.md#10-公共域名与-nginx)。

## 数据安全

业务数据库、备份、发布快照和运行日志都位于 `data/`，并由 `.gitignore` 排除。不要把真实数据库、导出的审计记录或包含员工信息的截图提交到 GitHub。
