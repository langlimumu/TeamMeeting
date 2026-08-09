# Team Loop project map

## Primary ownership

| Concern | Primary location | Also inspect |
| --- | --- | --- |
| Tables and migrations | `team_loop/database.py:init_db` | seed functions, backup verification |
| HTTP and API routing | `team_loop/handlers/request.py` | composed `team_loop/handler.py` |
| Authentication, users and organizations | `team_loop/handlers/accounts.py` | SSO/database helpers, system settings |
| Collaboration domains | `team_loop/handlers/collaboration.py` | moments, forum, morning and processes |
| Operational domains | `team_loop/handlers/operations.py` | scores, meetings, links, shifts and thanks |
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
- Organization propagation uses three distinct sets: direct `visible_ids` for normal reads/writes, ancestor IDs for read-only meetings and announcement topics, and same-root collaboration IDs for cross-team Thank You candidates. Thank You activity follows sender/receiver visibility; ranking follows receiver ownership only.
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
