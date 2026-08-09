# Windows 部署与运维

发布快照必须同时包含 `server.py` 与 `team_loop/` 包。仓库自带的 `deploy.ps1` 已处理该目录；手工复制部署时不能只复制入口文件。

约 100 人同时在线时，建议保留默认配置：`TEAM_LOOP_HTTP_MAX_WORKERS=64`、`TEAM_LOOP_HTTP_REQUEST_QUEUE_SIZE=256`、`TEAM_LOOP_SQLITE_BUSY_TIMEOUT_MS=15000`。数据库应位于本机 SSD，并通过 Nginx 复用客户端连接；不要把 SQLite 文件放在网络共享盘。

## 1. 环境要求

- Windows 10/11 或 Windows Server；
- Python 3.10+；
- 一个普通文件夹写入权限；
- 局域网访问时允许对应 TCP 端口入站。
- 公共域名访问时需要可达的公网入口、域名 DNS、Nginx Windows 版和 PEM 格式 TLS 证书。

项目运行不需要 pip、Node.js、数据库服务器或 IIS。

## 2. 首次部署

1. 将仓库放到固定目录，不要放在会自动清理的临时目录。
2. 确认命令行可以执行 `python --version`。
3. 双击 `start_server.bat`。
4. 浏览器访问 `http://127.0.0.1:8000/`。
5. 登录管理员账号后立即修改密码，并在系统管理中设置系统名称、团队名称和业务参数。

首次启动自动创建 `data/weekly_team.db`。部署目录必须允许运行账号写入 `data/`。

## 3. 局域网访问

直接局域网访问时，将正式服务显式监听到 `0.0.0.0:8000`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action StartProduction -HostAddress 0.0.0.0
```

然后在服务器电脑执行：

```powershell
ipconfig
```

找到当前局域网 IPv4 地址，其他设备访问：

```text
http://服务器IPv4:8000/
```

如果无法访问：

1. 先在服务器本机确认 `http://127.0.0.1:8000/` 可用；
2. 确认客户端和服务器处于可互访的网络；
3. 在 Windows 防火墙中允许 Python 或 TCP 8000 入站；
4. 确认没有其他程序占用端口。

不要把 8000/8001 端口直接暴露到公网。公共访问统一使用本文“公共域名与 Nginx”方案。

## 4. 环境与端口

| 环境 | 默认端口 | 数据库 | 用途 |
| --- | --- | --- | --- |
| development | 8000 | `data/weekly_team.db` 或自定义路径 | 本地开发热更新 |
| gray | 8001 | `data/deploy/gray/weekly_team_gray.db` | 正式数据快照上的功能验证 |
| production | 8000 | `data/weekly_team.db` | 团队正式使用 |

生产和灰度服务都运行发布快照，不监听源代码变化。

## 5. 灰度发布

双击 `deploy_gray.bat`，或执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Gray
```

脚本会：

1. 复制当前代码到带版本号的发布目录；
2. 停止旧灰度进程；
3. 使用 SQLite Backup API 创建正式库一致性快照；
4. 在灰度库执行数据库迁移；
5. 启动 8001 服务；
6. 检查 `/api/health` 并执行只读冒烟测试。

灰度产生的测试数据不会同步回正式库。

## 6. 提升正式版本

确认灰度后双击 `promote_production.bat`，或执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Promote
```

提升前脚本会再次验证灰度、备份正式数据库，然后迁移正式库并切换正式服务。启动或冒烟测试失败时会自动尝试恢复。

## 7. 回滚与状态

```powershell
# 查看进程、端口和版本
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Status

# 回滚上一正式版本
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Rollback

# 停止灰度
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action StopGray

# 停止正式
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action StopProduction
```

运行元数据和日志位于 `data/deploy/runtime/`，发布快照位于 `data/deploy/releases/`，正式库回滚快照位于 `data/deploy/backups/`。

## 8. 环境变量

| 变量 | 说明 |
| --- | --- |
| `TEAM_LOOP_DATA_DIR` | 数据目录，默认 `<项目>/data` |
| `TEAM_LOOP_DB_PATH` | SQLite 数据库完整路径 |
| `TEAM_LOOP_BACKUP_DIR` | 备份目录 |
| `TEAM_LOOP_ENV` | `development`、`gray` 或 `production` |
| `TEAM_LOOP_RELEASE` | 健康接口显示的发布版本 |
| `TEAM_LOOP_SSO_CLIENT_SECRET` | OAuth2 Client Secret，推荐使用环境变量而非写入数据库 |
| `TEAM_LOOP_SSO_HTTP_POOL_SIZE` | 每个身份平台 Origin 的最大复用连接数，默认 32 |
| `TEAM_LOOP_SSO_HTTP_TIMEOUT_SECONDS` | SSO 建连、响应和连接池等待超时，默认 12 秒 |
| `TEAM_LOOP_SSO_HTTP_IDLE_SECONDS` | SSO 空闲连接保留时间，默认 60 秒 |
| `TEAM_LOOP_SSO_DISCOVERY_CACHE_SECONDS` | OIDC Discovery 缓存时间，默认 300 秒，设为 0 可禁用 |
| `TEAM_LOOP_TRUST_PROXY` | 设为 `1` 后，仅信任来自本机代理的 `X-Forwarded-For/Proto`；Nginx 部署必须启用 |
| `TEAM_LOOP_REQUIRE_HTTPS` | 设为 `1` 后，拒绝没有可信 HTTPS 标记的登录及所有写请求；正式部署脚本自动启用 |

自定义数据盘示例：

```powershell
$env:TEAM_LOOP_DATA_DIR = 'D:\TeamLoopData'
python server.py --host 0.0.0.0 --port 8000
```

使用自定义变量时，启动服务的 Windows 账号必须拥有目录读写权限。

## 9. 企业 SSO 部署

1. 在企业身份平台创建 OAuth2/OIDC Web 应用，启用 Authorization Code 和 PKCE；
2. 将唯一回调地址登记为 `https://你的域名/api/sso/callback`；模块与组织页面不需要分别登记，系统会把原界面作为受控站内目标绑定到 SSO state；
3. 在 Team Loop“系统管理”中选择配置方式：优先填写 Issuer 自动发现；不支持 Discovery 时填写授权、Token、UserInfo 三个地址；
4. 填写 Client ID、回调地址、工号字段和姓名字段。OneAccess 常见 UserInfo 字段为 `userName`、`name` 和 `id`；系统也兼容 `employee_id`、`employeeNumber` 等字段；
5. 在“用户管理”中提前维护账号工号，可让首次 SSO 登录直接关联现有用户；否则系统自动创建“访客 / 待分类”只读账号，由管理员随后分配正式类型；
6. 通过服务器环境变量配置 `TEAM_LOOP_SSO_CLIENT_SECRET`，再启用企业 SSO 与首页自动登录；
7. 点击“保存 SSO 配置”，确认页面显示“已保存并启用”；随后运行“诊断已保存配置”。可临时粘贴 Postman 获取的 Access Token 验证 UserInfo 映射，Token 只用于当前请求，不会落库或写入日志；
7. 先在灰度环境完成已有工号关联、待分类自动建号、管理员归类、权限、失败回退和退出验证，再提升正式环境。

所有 SSO 配置都可用 `TEAM_LOOP_<配置键大写>` 环境变量覆盖。常用项包括 `TEAM_LOOP_SSO_MODE`、`TEAM_LOOP_SSO_ISSUER_URL`、`TEAM_LOOP_SSO_AUTHORIZATION_URL`、`TEAM_LOOP_SSO_TOKEN_URL`、`TEAM_LOOP_SSO_USERINFO_URL`、`TEAM_LOOP_SSO_CLIENT_ID`、`TEAM_LOOP_SSO_CLIENT_SECRET`、`TEAM_LOOP_SSO_REDIRECT_URI`、`TEAM_LOOP_SSO_USERNAME_CLAIM` 和 `TEAM_LOOP_SSO_AUTO_LOGIN`。管理员已知三个地址时，在系统配置中选择“手动 OAuth2”，依次填写“OAuth2 认证地址、Access Token 地址、UserInfo 地址”；界面文案变化不会改变这些环境变量键。

生产 SSO 必须通过 HTTPS 域名访问，反向代理需原样转发 Cookie 和 `/api/sso/*`。身份平台和 Team Loop 服务器时间应保持同步。项目优先使用系统安装的 Python 3.10+；若运行时缺少可用的 TLS/OpenSSL，OAuth2 HTTPS 请求将无法工作。

SSO 的 Discovery、Token 和 UserInfo 请求默认复用按身份平台域名隔离的连接池。连接池会读取 Windows/进程代理配置；HTTPS 身份平台可通过常见的 HTTP 企业代理建立 CONNECT 隧道，`NO_PROXY` 继续生效。约 100 人同时使用时建议先保留每个 Origin 32 条连接；只有身份平台响应稳定且监控确认池等待明显时才上调，最大值受限为 128。修改连接参数后运行 `python scripts\sso_pool_smoke_test.py`。

### 9.1 华为云 OneAccess / IDaaS

1. 在 OneAccess“资源 → 应用”中创建自建应用，认证集成选择 OIDC，并启用授权码模式；
2. Redirect URL 填写 `https://你的域名/api/sso/callback`，在授权管理中授权允许访问的用户；
3. 从“设置 → 服务配置 → OIDC”取得认证授权、Token 和 UserInfo 地址。若 OneAccess 没有提供可用 Issuer Discovery，在 Team Loop 中点击“应用华为云 OneAccess 预设”，再填写这三个地址；预设会使用 OneAccess 要求的 `scope=get_user_info`、工号字段 `userName` 和姓名字段 `name`；
4. 在 OneAccess“映射配置”中至少返回 `employee_id`、`name`、`groups`：`employee_id` 映射唯一工号，`name` 映射姓名，`groups` 映射组织或账号权限；Team Loop 对应字段分别填这三个属性名；
5. 已有账号按工号关联并保留管理员设置的团队；未命中账号自动创建为根组织下的“访客 / 待分类”，OneAccess 群组只形成建议团队；管理员在用户管理中确认用户类型和团队后生效。

不要把 OneAccess ClientSecret 写入代码或提交 Git，使用服务器环境变量 `TEAM_LOOP_SSO_CLIENT_SECRET`。

### 9.2 历史组织数据平滑迁移

先预览旧组织中由已迁移用户创建的讨论和会议将去往哪里：

```powershell
python scripts\migrate_org_data.py `
  --database data\weekly_team.db `
  --source ess `
  --follow-current-users
```

确认预览后增加 `--apply`。脚本执行前自动生成数据库备份和逐行 JSON 清单。需要回滚时使用：

```powershell
python scripts\migrate_org_data.py `
  --database data\weekly_team.db `
  --rollback data\org_migrations\org_migration_YYYYMMDD-HHMMSS.json
```

如果确定要把旧组织的全部讨论、会议和有效用户统一迁往某个二级组织，可使用 `--source ess --target ess/mo --include-users --apply`。默认只允许迁往源组织的下级，跨分支必须显式添加 `--allow-cross-branch`。正式数据库应先停写或进入维护窗口；第一次务必在灰度数据库上演练。

## 10. 公共域名与 Nginx

### 10.1 网络和证书前置条件

1. 域名 A/AAAA 记录指向服务器公网地址或网关公网地址；
2. 如果服务器在路由器后面，将公网 TCP 80/443 映射到服务器，并在 Windows 防火墙放行 80/443；
3. 不对公网开放 8000/8001；生产与灰度后端只监听 `127.0.0.1`；
4. 下载并解压完整的 Nginx Windows 包，例如到 `C:\nginx`；
5. 准备 PEM 格式完整证书链和私钥。可以使用企业证书或 win-acme 申请 Let's Encrypt 证书；证书续期后执行 Nginx Reload。

仅有域名并不能让外网访问；服务器必须具备公网入口或由云负载均衡/网关把 80/443 转发到本机。

### 10.2 启动只监听本机的正式服务

部署只监听回环地址的正式服务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 `
  -Action StartProduction `
  -HostAddress 127.0.0.1
```

`deploy.ps1` 对正式进程自动设置 `TEAM_LOOP_TRUST_PROXY=1` 和 `TEAM_LOOP_REQUIRE_HTTPS=1`；灰度进程保持本机 HTTP，方便在 8001 端口验收。若绕过部署脚本自行注册 Windows 服务，必须显式设置这两个变量，并确保后端只监听回环地址。

### 10.3 生成并启动 Nginx 配置

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\nginx_proxy.ps1 `
  -Action Configure `
  -Domain meeting.example.com `
  -NginxRoot C:\nginx `
  -CertificatePath C:\certs\meeting.example.com-fullchain.pem `
  -CertificateKeyPath C:\certs\meeting.example.com-key.pem `
  -UpstreamPort 8000

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\nginx_proxy.ps1 `
  -Action Start `
  -NginxRoot C:\nginx
```

脚本会生成 `C:\nginx\conf\team-loop.conf`，先执行 `nginx -t` 校验，再启动隐藏窗口进程。配置默认执行：

- HTTP 80 自动跳转 HTTPS 443；
- HTTPS 代理到 `127.0.0.1:8000`；
- 转发 Host、真实 IP 和原始协议；
- 增加 HSTS、`nosniff` 和 Referrer-Policy；
- 上传体积上限 10 MB，代理读取超时 120 秒。

证书续期或修改配置后执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\nginx_proxy.ps1 -Action Reload -NginxRoot C:\nginx
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\nginx_proxy.ps1 -Action Status -NginxRoot C:\nginx
```

首次申请证书前可以追加 `-HttpOnly` 生成临时 HTTP 配置，但只用于 DNS/ACME 联调，不应用于正式登录。

### 10.4 SSO 与验证

在企业身份平台和 Team Loop 系统管理中，把回调地址同时设为：

```text
https://meeting.example.com/api/sso/callback
```

验证以下地址和行为：

```text
https://meeting.example.com/api/health
https://meeting.example.com/
```

- HTTP 会跳转到 HTTPS；
- `/api/health` 返回 `status: ok`；
- 本地账号和 SSO 登录返回的 `weekly_session` Cookie 带 `Secure`；
- 直接访问 `http://127.0.0.1:8000` 仍可读取健康检查，但登录和写操作返回 426；
- 用户会话和审计日志记录客户端真实 IP，而不是统一显示 `127.0.0.1`；
- SSO 登录后仍停留在公共域名，不跳回 8000 端口。

浏览器提交登录表单时，请求体中仍会包含密码字段，这是服务器校验密码所必需的；HTTPS 会加密包括 URL、请求头和请求体在内的传输内容，网络中无法看到明文密码。不要用前端哈希替代 TLS：固定哈希本身会成为可重放的登录凭据。

## 11. 运维建议

- 每日确认自动备份状态，至少每月执行一次恢复校验；
- 发布前通知用户避免同时写入；
- 定期下载一份备份到另一块磁盘或受控文件服务器；
- 不通过聊天工具发送正式数据库；
- 服务器休眠会停止访问，正式电脑应关闭自动睡眠；
- 端口冲突时优先调整测试端口，不随意终止未知进程。
