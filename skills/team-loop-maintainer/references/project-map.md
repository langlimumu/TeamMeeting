# Team Loop project map

## Primary ownership

| Concern | Primary location | Also inspect |
| --- | --- | --- |
| Tables and migrations | `team_loop/database.py:init_db` | seed functions, backup verification |
| HTTP and API routing | `team_loop/handlers/request.py` | composed `team_loop/handler.py` |
| Authentication, users and organizations | `team_loop/handlers/accounts.py` | SSO/database helpers, system settings |
| Collaboration domains | `team_loop/handlers/collaboration.py` | moments, forum, morning and processes |
| Operational domains | `team_loop/handlers/operations.py` | scores, meetings, links, shifts, duty rosters, norms and thanks |
| System operations | `team_loop/handlers/system.py` | recycle, archive, backups, settings and audit |
| Permissions | `team_loop/config.py`, `team_loop/permissions.py` | `static/app.js` access helpers and navigation |
| Team moments | `team_moments`, `team_moment_images`, protected image endpoint | `#moments`, card/timeline renderer and edit modal |
| Organization tree and route scope | `org_units`, `organization_context()` | SSO group mapping, people-centered module queries, sidebar organization switcher |
| Page markup and dialogs | `static/index.html` | render functions in `static/app.js` |
| State, rendering, interactions | `static/app.js` | related backend endpoint |
| Visual design and responsiveness | `static/style.css` | theme overrides near the bottom |
| Development reload | `scripts/dev_server.py` | `start_hot_server.bat` |
| Gray/production release | `deploy.ps1` | batch wrappers, smoke and snapshot scripts |
| Enterprise OAuth2/OIDC SSO | `team_loop/handlers/accounts.py`, `team_loop/sso_http.py`, system settings | Connection pooling, Discovery/manual endpoints, PKCE, employee-ID mapping, auto login fallback, provisioning and sessions |
| User and developer docs | `docs/` | `README.md`, this skill |

## Domain invariants

- A user owns one member profile; inactive users disappear from current member views while history remains.
- Member drag ordering accepts exactly the active participating members visible in the selected organization route; the server must not validate against or return the global member set.
- User management supports client-side account/name/employee-ID search, organization/type/auth filters, and transaction-safe bulk type, organization, or soft-delete operations. Bulk deletion must protect the current account, revoke sessions, and create one recycle record per user.
- Guest modules are selected through the reserved `guest` permission template; the frontend consumes `/api/me` and must not maintain a separate allowlist.
- User-type permissions include view/create/edit/delete; UI hiding never replaces server checks.
- User-type participation scopes independently control current team-member, morning, red/black, and Thank You candidate lists without deleting history.
- Organization visibility controls which users and organization-owned records are in scope; it is independent from module permissions and participation scopes. Client organization paths must always be intersected with the authenticated user's accessible organization IDs.
- Organization propagation separates the selected organization, broader visible routes, and ancestors. Morning, shifts, attendance, red/black, and Thank You use direct members of the selected organization; only meetings and announcement topics inherit from ancestors.
- User types are dynamic. Only `guest` is reserved; it is read-only and cannot be assigned to an account.
- Past morning-meeting dates are read-only; unfinished items inherit through a root chain.
- Completed or archived meetings lock agenda and minutes until an admin reopens them.
- Meeting creation follows the `meetings.create` operation permission; only administrators maintain first-level topic categories and second-level presets.
- Meeting presets are batch-added through `/api/meetings/{id}/agenda-options`, with an optional owner per selected item; `meetings.start_time` is `HH:MM` or empty.
- Process templates belong to an organization and inherit downward read-only. Templates are forests with parallel roots and tree branches, and the editor mind map is derived from ordered parent keys rather than stored coordinates. Creating an instance snapshots every node and parent relation; later template edits or deactivation must not mutate existing instances. Children require completed parents, parent resets cascade downward, and required nodes determine automatic completion.
- Team discussion is a forum-style topic list with categories, search, sorting, pagination, detail replies, soft deletion, and recycle restore. Authors manage their own topics; only administrators publish announcements or pin topics.
- Discussion Emoji picker code, locale, and Emoji data are local static assets and must work without public internet access.
- Public domains terminate TLS in local Nginx and proxy to a loopback Team Loop port. Forwarded IP/protocol are trusted only from loopback when explicitly enabled.
- Red and black scores remain separate; do not silently convert to a net score.
- Black-score summary and detail visibility are separate system settings; non-admin API responses must be filtered server-side while administrators retain full management access.
- A user may edit/delete only allowed Thank You records; weekly recipient limits come from settings.
- Link edits and deletes are available to users whose type grants the matching operation, with soft deletion and audit history.
- OAuth2 manual configuration groups the authorization, access-token and UserInfo endpoints with Client ID and callback guidance. Client Secret is write-only in the UI and may be supplied with `TEAM_LOOP_SSO_CLIENT_SECRET`; public settings expose only readiness, auto-login state and button text. Employee ID is the user-management link, external subject is the stable provider identity, and the deepest matching SSO group selects the organization route.
- Gray uses a production snapshot and never writes its test data back to production.
- Team norms are crowd-recorded and organization-scoped, and each category owns its **own document** instead of being a chapter of one big file: `GET /api/norms/document` returns a `documents` array with one entry per category (`category_id`, `name`, `title`, `article_count`, a single-element `chapters`, and its own `markdown`). Article numbers are **per document** (`1`, `2`, `3`, restarting in every document) with no category prefix, because a category's ordinal comes from `sort_order` and prefixing would renumber every document whenever categories are reordered; cross-document references name the document, e.g. 「见《研发流程规范》第 2 条」. Only `active` and unexpired norms enter a document; empty categories keep an empty document so the navigation mirrors the shelves and a freshly created category never disappears. There is deliberately **no versioning** — a document is a live projection of `norms`, so recording or editing renumbers it immediately. `norm_doc_versions` is still created but nothing reads or writes it: do not reintroduce a publish/preview flow without also reintroducing a frozen release view, because rendering live content under a version label was the original bug. Category deletion or deactivation is blocked while entries remain, and a norm may be edited by its author plus administrators.

## High-risk areas

- `server.py` is a compatibility entry point. Domain code belongs in `team_loop/`; route ordering in `handlers/request.py` can still shadow dynamic paths.
- SQLite supports concurrent reads through WAL but serializes writes. Keep databases on local disks, preserve bounded HTTP workers, and run the 100-request concurrency smoke test after connection or transaction changes.
- `static/app.js` renders HTML strings; missing `escapeHtml()` creates stored-XSS risk.
- Sessions are persisted as token hashes in SQLite; authentication changes must preserve expiry, revocation, device listing, and login throttling.
- User types and morning items use optimistic versions; stale writes must return 409 instead of overwriting newer data.
- Shift batches are atomic and must reject duplicates or daily-hour conflicts before inserting any row.
- SQLite files cannot be replaced while another Windows process holds them open.
- Theme-specific CSS appears after base CSS and can override new styles.
- Development hot reload on port 8000 may point at the main database; use Gray for destructive tests.
- A live instance only picks up part of an edit: `static/*` is re-read from disk on every request, but Python modules are imported once at process start, so a page can show a **new frontend with an old backend** (e.g. neutral navigation without sequence numbers, yet article numbers still coming from the stale `no`). Edits under `team_loop/` require restarting the process; "the fix is not visible" almost always means a process started before the edit, not a broken change.
- Before trusting a screenshot or reporting a bug, identify which release actually serves the port: `data/deploy/runtime/production.json` records `release`, `release_path`, `database`, `pid` and `started_at`, and the pid must match the process listening on that port. A `data/deploy/releases/<stamp>` snapshot is frozen at deploy time and can be days behind the working tree, and a deployment directory (`companytest/TeamMeeting-main`) carries its own `data/deploy` tree — a listener on `0.0.0.0:8000` may belong to a completely different copy of the project than the one being edited.
