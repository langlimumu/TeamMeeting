# 常见问题

## 页面打不开

先检查：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Status
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果 8000 被占用：

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

不要直接结束不属于 Team Loop 的进程。开发时可临时改用其他端口。

## 局域网电脑或手机无法访问

- 确认服务器本机可以访问；
- 使用服务器局域网 IPv4，不要使用 `127.0.0.1`；
- 确认服务监听 `0.0.0.0`；
- 检查 Windows 防火墙和网络隔离；
- 某些公司 Wi-Fi 会禁止无线客户端访问有线局域网，需要网络管理员放通。

## 修改代码后页面没变化

- 开发模式确认使用 `start_hot_server.bat`；
- 正式/灰度环境不会读取工作区代码，必须重新执行 Gray 或 Promote；
- 浏览器执行强制刷新；
- 检查开发终端是否因语法错误反复重启；
- 运行 `node --check static\app.js` 和 `python -m compileall -q server.py team_loop scripts`。

## 并发访问出现 database is locked

1. 确认数据库位于服务器本地磁盘，不在 SMB/NAS/同步盘。
2. 执行 `python server.py --migrate-only`，再用 SQLite 检查 `PRAGMA journal_mode` 应为 `wal`。
3. 运行 `python scripts\concurrency_smoke_test.py`，确认 100 个混合请求可完成。
4. 查看是否有外部程序长期打开写事务，或管理员正在执行恢复、迁移等独占操作。
5. 可适度增加 `TEAM_LOOP_SQLITE_BUSY_TIMEOUT_MS`，但若持续大量写入，应迁移到 PostgreSQL，不能靠无限延长等待掩盖容量问题。

## 灰度发布提示数据库被占用

最新部署脚本会先停止旧灰度进程再替换快照。若仍失败，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action StopGray
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Gray
```

并检查是否有外部 SQLite 工具打开 `weekly_team_gray.db`。

## 登录后页面权限不正确

1. 管理员检查用户所属“用户类型”；
2. 检查该类型的模块及查看/新增/修改/删除权限；
3. 用户退出后重新登录；

## 企业 SSO 登录失败

- 页面填写过配置但 SSO 仍不可用：先查看 SSO 区底部是否显示“已保存并启用”。“配置完整”只代表当前表单已填齐，不代表已经写入数据库；灰度环境重新部署时会从正式库重新创建，灰度里单独填写的配置不会自动进入正式库；
- Postman 能获取 UserInfo，但系统不能建号：在“系统管理 → 诊断已保存配置”粘贴同一个临时 Access Token，查看实际采用的工号字段。OneAccess 通常返回 `userName`、`name`、`id`，系统已自动兼容，也可在高级映射中显式填写；
- OneAccess 授权页或 Token 接口提示 Scope 错误：OneAccess OAuth2 的授权范围固定为 `get_user_info`，点击配置区的“OneAccess 预设”或手工修改 Scope；
- Client ID/Secret 莫名变成系统登录账号：旧版可能被浏览器密码管理器自动填充；新版已隔离登录凭据自动填充。请重新填写真实 Client ID/Secret 并保存；
- 登录页没有 SSO 按钮：自动发现模式检查 Issuer 与 Client ID；手动模式检查授权、Token、UserInfo 三个地址与 Client ID；
- 提示回调不一致：企业身份平台登记值必须与“OAuth2 回调地址”逐字一致；
- 提示无法连接身份平台：检查服务器 DNS、代理、防火墙、HTTPS 证书和系统时间；
- 高峰期提示 `SSO connection pool is busy`：先检查身份平台 Token/UserInfo 延迟和服务端出口网络，再按实际容量适度增加 `TEAM_LOOP_SSO_HTTP_POOL_SIZE`；不要直接设置为无限连接；
- 登录后回到系统账号页：页面会在 SSO 失败后主动停止循环跳转，先查看页面错误提示和服务日志，修复后点击“企业 SSO 登录”重试；
- 提示工号缺失或关联冲突：核对“SSO 工号字段”和 UserInfo 返回值，并在“用户管理”确认工号唯一；
- 提示 Access Token 或 UserInfo 请求失败：错误会标明失败阶段、HTTP 状态和身份平台返回的安全错误说明；依次检查 Client Secret、Scope、回调地址、服务器 DNS/代理和出口防火墙；
- 首次 SSO 登录后只有只读权限：这是待分类保护；管理员在“用户管理”筛选“访客 / 待分类”，为账号单个或批量分配正式类型；
- OneAccess 群组已经变化但账号团队没变：这是平滑保护；用户管理中会显示“SSO 建议团队”，由管理员确认后生效，登录本身不会自动搬迁账号和历史数据；
- 调整团队后看不到旧讨论或会议：先在灰度数据库运行 `python scripts\migrate_org_data.py --database <db> --source <旧组织> --follow-current-users` 预览，再使用 `--apply`；不要直接手改生产数据库；
- 其他电脑可打开页面但不能 SSO：不要使用局域网 HTTP 地址作为正式回调，应通过 HTTPS 域名和反向代理访问；
- Windows 运行时出现 TLS/OpenSSL 错误：改用系统安装的 Python 3.10+ 启动，并确认 `python -c "import ssl; print(ssl.OPENSSL_VERSION)"` 正常。
4. 管理员切换到用户视图进行复现；
5. 确认前端和后端都已注册新模块权限。

## 下级团队看不到上级安排或看到了无关数据

- 只有会议和“团队公告”会从上级向下级透传，普通讨论、早例会、排班和积分不会透传；
- 确认当前侧栏团队路径正确，上级记录确实创建在祖先组织；
- 透传记录应显示“上级安排/上级团队”，并且下级只能查看；
- 早例会、排班、签到、积分和 Thank You 只显示侧栏当前选中团队的直接成员；如果出现上下级人员混入，检查接口是否误用了子树过滤而不是 `organization_current_user_filter()`；
- 修改组织范围后运行 `python scripts\organization_scope_smoke_test.py`，检查是否有自定义查询绕过统一组织过滤。

## Outlook 邮件没有套用模板

系统通过 `mailto:` 唤起默认邮件客户端，并将 HTML 纪要复制到剪贴板。新版 Outlook 对 `mailto:` 正文和 HTML 支持有限，因此推荐：

1. 点击“生成会议邮件”；
2. 等待 Outlook 新邮件窗口打开；
3. 在正文区域粘贴剪贴板内容；
4. 检查收件人和内容后手动发送。

如果不能唤起 Outlook，请在 Windows“默认应用”中为 MAILTO 协议选择 Outlook。

## 表情显示为方框或问号

快捷回应优先使用 `static/vendor/` 中的本地资源。检查静态资源是否完整、浏览器是否使用旧缓存，以及数据库中早期损坏文本是否本身已被保存为问号。已损坏的历史文本无法仅靠字体恢复。

## 备份恢复失败

- 先执行备份校验；
- 确认备份位于系统允许的备份目录；
- 确认运行账号对数据库和备份目录有写权限；
- 查看 `data/deploy/runtime/` 或启动终端日志；
- 不要在恢复期间用 SQLite 工具打开数据库。

## 数据误删

先到系统管理的回收站恢复。用户、链接、会议议题和团队回复等主要对象采用软删除。只有管理员执行“永久删除”后才不能从回收站恢复，此时需要从数据库备份恢复。

## 公共域名与 Nginx

- 域名无法访问：确认 DNS 已生效、公网入口存在、网关端口映射正确，并且 Windows 防火墙只放行 80/443；
- Nginx 返回 `502 Bad Gateway`：先在服务器本机打开 `http://127.0.0.1:8000/api/health`，再确认 Nginx `UpstreamPort` 与正式端口一致；
- Nginx 启动后立即退出：执行 `scripts\nginx_proxy.ps1 -Action Reload` 或直接运行 `nginx.exe -t`，查看 `logs/team-loop-error.log`；
- 浏览器提示证书不可信：必须使用与公共域名匹配的完整证书链，不能把自签名证书用于普通用户访问；
- SSO 回调后跳转失败：身份平台和系统配置中的回调必须完全等于 `https://域名/api/sso/callback`；
- SSO 登录后总是回到首页：确认浏览器发起的是 `/api/sso/login?return_to=...`，数据库 `sso_login_states` 已迁移出 `return_to` 字段，并且静态资源版本已刷新；原组织或模块无权限时回落属于正常保护；
- 会话 IP 全是 `127.0.0.1`：确认 Team Loop 进程启动前设置了 `TEAM_LOOP_TRUST_PROXY=1`，并确认后端仅监听 `127.0.0.1`；
- 登录 Cookie 没有 `Secure`：检查 Nginx 是否发送 `X-Forwarded-Proto https`，以及 Team Loop 是否启用了可信代理；
- 登录或保存返回 HTTP 426：当前请求没有经过可信 HTTPS 代理；请使用正式 HTTPS 域名，不要直接访问生产后端端口；
- HTTPS 出现重定向循环：不要在其他上游代理中把 HTTPS 请求错误标记为 HTTP，检查每一层 `X-Forwarded-Proto`。
