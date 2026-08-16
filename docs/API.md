# Team Loop HTTP API

## 1. 通用约定

- 基础地址：`http://<host>:<port>`；
- 数据格式：除静态文件外均使用 JSON；
- 日期格式：`YYYY-MM-DD`；
- 时间格式：本地时间 ISO 8601；
- 登录后由浏览器 Cookie 维持会话；
- 组织路由格式为 `/org/<根>/<子团队>/...`；前端 API 请求通过 `X-Team-Org-Path` 传递当前组织路径，服务端仍会按登录人的可访问范围二次校验；
- 错误响应：`{"error": "可读错误原因"}`；
- 未登录通常返回 401，无权限返回 403，资源不存在返回 404；并发编辑冲突返回 409。

公共域名由本机 Nginx 提供 HTTPS，后端基础地址保持 `http://127.0.0.1:8000`。生产部署默认启用 `TEAM_LOOP_TRUST_PROXY=1` 和 `TEAM_LOOP_REQUIRE_HTTPS=1`：后端仅接受回环代理传入的 `X-Forwarded-For` 与 `X-Forwarded-Proto`，拒绝未经 HTTPS 转发的登录及所有 POST/PATCH/DELETE 请求，HTTPS 会话 Cookie 增加 `Secure`。

示例：

```javascript
const response = await fetch("/api/morning-items?date=2026-07-12", {
  credentials: "same-origin",
});
const data = await response.json();
if (!response.ok) throw new Error(data.error || "请求失败");
```

不要在 URL 查询参数中传递账号或密码。

## 2. 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/login` | 登录，正文包含 `username`、`password` |
| GET | `/api/sso/login` | 发起 OAuth2/OIDC 授权码登录，生成一次性 state、nonce 和 PKCE 校验参数后跳转身份平台 |
| GET | `/api/sso/callback` | OAuth2/OIDC 回调，完成换令牌、按工号关联账号和会话签发后跳回首页 |
| POST | `/api/sso/diagnose` | 管理员检查已保存 SSO 配置；可提交一次性 `access_token` 验证 UserInfo 字段映射、账号匹配和建议团队，令牌不持久化 |
| POST | `/api/logout` | 退出并清除当前会话 |
| GET | `/api/me` | 当前用户、权限、模块目录和公开设置 |
| PATCH | `/api/me/password` | 修改当前用户密码 |
| GET | `/api/sessions` | 查询当前账号的登录设备和会话 |
| DELETE | `/api/sessions/{id}` | 撤销指定会话；可撤销当前设备 |
| GET | `/api/health` | 服务、环境、版本和数据库健康状态 |

登录示例：

```json
{
  "username": "employee-id",
  "password": "current-password"
}
```

SSO 回调成功后跳转到账号当前所属组织，例如 `/org/ess/mo/ws?sso=success`；失败时跳转到 `/?sso_error=<可读原因>`。开启自动登录后，前端仅在一次页面会话中自动发起一次 SSO；失败、主动退出、访客浏览或选择系统账号都会停止自动跳转。首次登录可自动建号，新账号返回 `classification_pending=1` 并使用 `guest` 只读权限。SSO 群组匹配结果只写入 `suggested_org_unit_id`，不会在登录过程中直接迁移已有账号或历史数据；管理员确认用户类型和团队后才正式生效。`/api/me` 只公开 SSO 是否可用、是否自动登录、是否强制 HTTPS 及按钮文案，不返回任何端点、Issuer、Client ID 或 Client Secret。

## 3. 用户、成员与权限

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/users` | 查询或创建用户 |
| PATCH/DELETE | `/api/users/{id}` | 修改或软删除用户 |
| PATCH | `/api/users/bulk-type` | 将 `user_ids` 中的账号批量调整到指定 `user_type` |
| PATCH | `/api/users/bulk-org` | 将 `user_ids` 中的账号批量调整到指定 `org_unit_id` |
| PATCH | `/api/users/bulk-suggested-org` | 为 `user_ids` 中存在 SSO 团队建议的账号采用各自建议组织；没有建议的账号跳过 |
| DELETE | `/api/users/bulk-delete` | 软删除 `user_ids` 中的账号，撤销登录会话并逐条写入回收站；禁止包含当前登录账号 |
| GET | `/api/org-context` | 获取当前路由选择、可访问组织和可见组织范围 |
| GET/POST | `/api/org-units` | 管理员查询或创建组织层级 |
| PATCH/DELETE | `/api/org-units/{id}` | 修改或删除组织；存在子组织或有效用户时禁止删除 |
| GET/POST | `/api/user-types` | 查询或创建用户类型；创建时可指定 `copy_from` 复制权限 |
| POST | `/api/user-types/{code}/impact` | 预评估权限或参与名单变化及受影响账号 |
| PATCH | `/api/user-types/{code}/permissions` | 更新名称、说明、模块操作权限与独立业务参与名单；支持 `expected_version` |
| DELETE | `/api/user-types/{code}` | 删除没有有效用户的类型；访客模板及最后一个可分配类型不可删除 |
| GET/POST | `/api/members` | 查询成员或维护当前成员资料 |
| PATCH | `/api/members/{id}` | 更新成员资料 |
| PATCH | `/api/members/order` | 管理员提交当前组织路由全部可见成员 ID，调整成员卡片顺序 |

用户与成员是一一关联的业务实体。新增用户必须指定有效用户类型，不能指定 `guest`。单次批量操作最多处理 200 个有效账号；删除用户后历史记录保留，成员列表不再展示该用户。

`PATCH /api/members/order` 的 `member_ids` 必须恰好覆盖当前组织路由中有效且参与成员展示的全部成员，不能提交其他组织的成员或遗漏当前成员。服务端按组织上下文重新计算集合后再写入顺序，避免管理员在下级团队排序时误改其他团队。

用户同时归属一个组织层级。组织的 `visibility_mode` 支持：`all`（可切换全组织）、`subtree`（可切换本层及全部下级）、`unit`（只能切换本层）。成员页仍可按授权范围查看组织树；早例会、排班、签到、红黑榜和 Thank You 的人员名单与业务记录只取当前选中组织的直接成员，不自动混入下级、上级或兄弟团队。上级会议和公告额外向下级只读透传。管理员可以访问全部组织，但切换组织后业务名单仍按所选层级重新过滤。

用户类型的 `participation` 与模块权限互相独立，包含 `members`、`morning`、`rules`、`thanks` 四个布尔值。例如拥有红黑榜查看权限，并不代表账号必须进入积分名单。类型更新和早例会编辑使用版本号防止覆盖其他管理员或成员刚提交的修改。

## 4. 团队讨论区

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/team-posts` | 获取讨论主题列表或发表主题；支持分类、状态、关键词、排序和分页 |
| GET | `/api/team-posts/{id}` | 获取主题详情、回复树与回应统计，并记录浏览量 |
| PATCH | `/api/team-posts/{id}` | 作者编辑标题、正文、分类和状态；管理员还可置顶，公告分类仅管理员可用 |
| DELETE | `/api/team-posts/{id}` | 作者或管理员软删除主题并写入回收站 |
| POST | `/api/team-posts/{id}/replies` | 回复主题或指定父回复 |
| POST | `/api/team-posts/{id}/reactions` | 对主题添加或取消 Emoji 回应 |
| DELETE | `/api/team-replies/{id}` | 回复作者或管理员软删除回复 |
| POST | `/api/team-replies/{id}/reactions` | 对回复添加或取消 Emoji 回应 |

主题列表只返回未删除数据。上级组织的 `announcement` 主题向下级只读透传，下级成员可回复和回应，但不能编辑、删除或置顶原公告；普通主题不跨组织透传。主题删除后，其回复和回应随主题隐藏；管理员从回收站恢复主题时，原回复与回应一并恢复。所有分类、置顶和删除权限必须由服务端校验，不能依赖前端按钮是否可见。
| POST | `/api/team-replies/{id}/reactions` | 对楼中回复添加/取消回应 |
| DELETE | `/api/team-replies/{id}` | 删除自己的回复及子回复 |

服务端会校验消息和回复长度，不应依赖前端 `maxlength` 作为唯一限制。

### 团队时刻

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/team-moments` | 查询当前组织与祖先组织的有效团队时刻；可传 `year`、`keyword` |
| POST | `/api/team-moments` | 发布团队时刻，`images` 最多 6 张 Base64 图片 |
| PATCH | `/api/team-moments/{id}` | 修改事迹并通过 `new_images`、`remove_image_ids` 调整图片 |
| DELETE | `/api/team-moments/{id}` | 软删除并进入回收站 |
| GET | `/api/team-moment-images/{id}` | 在模块与组织权限校验后返回图片二进制 |

团队时刻使用独立 `moments` 模块权限。图片只允许 JPG、PNG、WebP，单张解码后最大 5 MB；浏览器请求不能绕过服务端组织范围。

图片 URL 带有基于创建时间的版本参数，并返回禁止缓存响应头，避免灰度/正式数据库切换或恢复备份后复用相同图片 ID 时显示旧图。

## 5. 早例会与归档

`GET /api/morning-items?date=YYYY-MM-DD` 除当天事项外，还会返回上一个工作日完成且当天没有新记录的事项。该类记录带 `retained_from_previous_workday=true` 和 `retained_from_date`，仅用于早会回顾，不能在新日期修改；响应同时给出 `retained_completed_count`。工作日当前按周一至周五计算。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/morning-items` | 按日期查询或新增事项 |
| GET | `/api/morning-items/version` | 返回当天早例会轻量版本号，供前端轮询是否有他人更新 |
| PATCH | `/api/morning-items/order` | 管理员提交当前层级完整参会人员 ID，保存早例会显示顺序 |
| PATCH/DELETE | `/api/morning-items/{id}` | 更新或删除可编辑事项 |
| GET | `/api/morning-items/{id}/history` | 获取事项跨日进展 |
| GET | `/api/archive/years` | 获取可归档年份统计 |
| GET | `/api/archive/search` | 跨会议、对话和早例会搜索 |

历史日期只读。未完成事项由服务端按日继承，客户端不应自行复制。更新或删除时传入查询结果中的 `version` 作为 `expected_version`，收到 409 后应重新加载数据。前端每 12 秒查询轻量版本号；没有正在编辑时自动刷新，有未保存输入时只显示“有更新”并由用户手动刷新，避免覆盖输入。管理员排序必须恰好提交当前层级中纳入早例会的全部有效账号。

## 6. 流程中心

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/process-templates` | 查询可用模板；管理员在当前团队创建模板 |
| PATCH/DELETE | `/api/process-templates/{id}` | 管理员修改或停用当前团队模板 |
| GET/POST | `/api/process-instances` | 查询个人/团队流程，或从模板生成个人流程 |
| PATCH/DELETE | `/api/process-instances/{id}` | 修改名称、截止日期，或取消允许操作的个人流程 |
| PATCH | `/api/process-instance-items/{id}` | 勾选或取消单个流程节点 |

模板项通过请求字段 `key` 和 `parent_key` 建立父子关系：`parent_key` 为空表示并行起点，指向较早步骤表示其下游节点；同一父节点可以有多个子节点形成分支。父节点必须出现在子节点之前，且必做节点不能依赖可选节点。查询结果使用 `parent_item_id` 返回关系。

前端脑图编辑器只是上述有序父子关系的可视化投影：点击图中节点编辑属性，新增子步骤写入该节点的 `parent_key`，新增并行线写入空 `parent_key`。服务端仍以请求数组顺序与父子约束为准，不接收坐标作为业务事实。

模板查询会返回当前团队与祖先团队启用的模板；祖先模板标记为 `inherited=true`，在下级只读。生成个人流程时，服务端复制节点及其父子关系形成快照，之后修改或停用模板不会改变历史流程。

`GET /api/process-instances` 支持 `scope=mine|team` 和 `status=active|completed|all`。普通用户始终只能查询自己的流程；管理员可在当前组织范围查看团队流程。进度由必做节点计算。子节点只能在父节点完成后勾选；取消父节点会递归撤销已完成的下游节点，并通过 `reset_descendants` 返回撤销数量。

## 7. 会议沙盘

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/meetings` | 查询或创建单场会议；查询响应另含当前层级 `attendance_users`，创建受 `meetings.create` 权限控制 |
| PATCH | `/api/meetings/{id}` | 更新会议信息或阶段 |
| POST | `/api/meetings/bulk-generate` | 根据预设周期批量生成 |
| PATCH | `/api/meetings/{id}/topics` | 设置本场会议主题 |
| POST | `/api/meetings/{id}/copy-agenda` | 沿用最近会议议题 |
| GET | `/api/meeting-topics` | 议题类型与预设选项 |
| POST/DELETE | `/api/meeting-topic-types[/{id}]` | 管理员新增或停用一级议题分类 |
| POST | `/api/meeting-topic-options` | 管理员新增二级预设议题 |
| PATCH/DELETE | `/api/meeting-topic-options/{id}` | 管理员修改或停用二级预设议题 |
| POST | `/api/meetings/{id}/agenda-options` | 批量勾选二级预设议题并为每条指定 `owner_id` |
| POST | `/api/meetings/{id}/items` | 添加本场议题 |
| POST | `/api/meetings/{id}/items/reorder` | 提交完整议题 ID 顺序 |
| PATCH/DELETE | `/api/meeting-items/{id}` | 更新纪要或软删除议题 |
| POST | `/api/meeting-items/{id}/carry-forward` | 顺延到下一场可用会议 |
| POST | `/api/meetings/{id}/attendance` | 更新单人成员签到 |

会议阶段值：`draft`、`scheduled`、`in_progress`、`completed`、`archived`。后两种状态锁定议题和纪要。查询会议时会包含祖先组织会议并返回 `inherited=true` 与 `org_unit_name`；所有会议写接口仍要求当前路由直接拥有该会议组织访问权。

创建和更新会议可传 `start_time`，格式为 24 小时制 `HH:MM`。会议纪要邮件是否附带 Thank You 由前端生成时选择，不改变会议数据。

会议签到名单和议题责任人都只接受当前选中组织层级的直属成员；预设议题原责任人不在当前层级时会留空，需重新指定。

议题常用字段：

```json
{
  "type_id": 1,
  "title": "TOPTB 温控复盘",
  "detail": "讨论背景",
  "owner_id": 3,
  "duration_minutes": 15,
  "expected_output": "确认处理方案",
  "materials": "趋势图和报警日志"
}
```

## 8. 排班、红黑榜和 Thank You

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/machines` | 查询或新增机台 |
| DELETE | `/api/machines/{id}` | 删除机台及其排班 |
| GET/POST | `/api/shifts` | 查询或批量新增排班；查询响应另含当前层级 `users` |
| DELETE | `/api/shifts/{id}` | 删除单条排班 |
| GET | `/api/dashboards/shifts` | 工时统计 |
| GET/POST | `/api/rules` | 红黑榜细则 |
| GET/POST | `/api/scores` | 积分明细 |
| PATCH | `/api/scores/{id}` | 管理员编辑当天积分 |
| GET | `/api/dashboards/red-black` | 月度、年度积分看板 |
| GET/POST | `/api/thank-you` | 查询或送出感谢 |
| PATCH/DELETE | `/api/thank-you/{id}` | 修改或删除允许操作的感谢 |
| GET | `/api/dashboards/thank-you` | 月度/年度 Thank You 排名 |

批量排班会先校验整批数据；同一用户同日重复班次或累计工时超过系统配置时整批返回 409，不进行部分写入。排班、签到、红黑榜和 Thank You 的查询与写入都会在服务端校验相关账号属于当前选中组织的直接成员，并继续校验对应业务参与开关。

`GET /api/thank-you` 的候选人只返回当前层级中纳入 Thank You 名单的账号。感谢记录只有发送人和接收人都属于当前层级时才在动态与排名中出现；切换到上级或兄弟团队不会汇总下级感谢。

`GET /api/scores` 支持 `from`、`to` 和 `user_id`。`red_black_show_black_points` 与 `red_black_show_black_details` 为管理员维护的布尔系统配置；普通用户的年度汇总和明细会在服务端按配置裁剪，管理员始终获得完整数据。

## 9. 链接、提醒和系统管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/links` | 查询或归档链接 |
| PATCH/DELETE | `/api/links/{id}` | 修改或软删除链接 |
| GET/POST | `/api/link-categories` | 链接分类 |
| GET | `/api/reminders` | 当前用户提醒 |
| PATCH | `/api/reminders/read` | 标记提醒已读 |
| GET | `/api/recycle-bin` | 回收站 |
| POST | `/api/recycle-bin/{id}/restore` | 恢复软删除记录 |
| DELETE | `/api/recycle-bin/{id}` | 永久删除回收记录 |
| GET/PATCH | `/api/settings` | 查询或更新系统配置 |
| GET | `/api/audit-logs` | 审计日志 |
| GET/POST | `/api/backups` | 查询、下载信息或创建备份 |
| POST | `/api/backups/verify` | 校验备份完整性 |
| POST | `/api/backups/restore` | 恢复指定备份 |

## 10. 扩展 API 的检查项

新增接口时同时确认：

1. 路由是否映射到正确模块；
2. 服务端是否校验管理员、所有者或操作权限；
3. 输入类型、长度、枚举和日期是否合法；
4. SQL 是否使用参数绑定；
5. 写操作是否进入事务并记录审计日志；
6. 错误是否为用户可理解的中文；
7. 是否需要软删除、回收站和恢复能力；
8. 是否需要更新本文件及冒烟测试。
