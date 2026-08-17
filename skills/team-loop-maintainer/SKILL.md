---
name: team-loop-maintainer
description: Maintain, extend, debug, test, document, and deploy the Team Loop Python/SQLite/vanilla-JavaScript application. Use for Team Loop feature work, UI fixes, permission changes, API or schema changes, backup/recovery work, Windows deployment, gray releases, production promotion, and repository documentation.
---

# Team Loop Maintainer

Work from the repository root. Preserve the dependency-free Python standard-library backend, vanilla frontend, SQLite data model, Windows deployment flow, and existing Chinese product language unless the user explicitly approves an architectural change.

## Start every task

1. Read `README.md` and the relevant file under `docs/`.
2. Read `references/project-map.md` for module ownership and high-risk boundaries.
3. Run `git status -sb`; preserve unrelated worktree changes.
4. Locate code with `rg` before editing.
5. Inspect both the frontend and backend path for any permissioned feature.

Use these references conditionally:

- Read `../../docs/USER_GUIDE.md` for user-visible behavior and terminology.
- Read `../../docs/DEVELOPMENT.md` before adding modules, routes, tables, permissions, forms, or dialogs.
- Read `../../docs/API.md` for endpoint conventions.
- Read `../../docs/DATABASE.md` for schema, migration, backup, or restore work.
- Read `../../docs/DEPLOYMENT.md` for service, gray, production, or rollback work.
- Read `references/release-checklist.md` before any commit, push, gray deployment, promotion, or rollback.

## Implement changes

### Product and UI

- Keep operational pages compact, scannable, and task-focused.
- Prefer modal editing for long forms, details, and destructive confirmation.
- Use event delegation for dynamically rendered controls.
- Escape every user-controlled value before injecting HTML.
- Preserve independent scrolling for long lists and stable calendar/table dimensions.
- Keep the sidebar organization switcher hierarchical and collapsible; expand only the selected path by default, keep deep trees internally scrollable, and verify desktop, medium, and mobile layouts.
- Verify Miro theme first, then check theme overrides and responsive breakpoints.
- Make each page reload its latest data when opened.

### Permissions

- Treat frontend visibility as presentation only.
- Enforce admin, ownership, module, and action permissions in the relevant `team_loop/handlers/` domain module.
- Register new modules in `MODULE_CATALOG`, initial permissions, `module_for_path()`, frontend `pages`, and loaders.
- Treat user types as administrator-defined data. Never branch business behavior on a display name or assume fixed internal/partner type keys.
- Keep module permissions separate from business participation scopes (`members`, `morning`, `rules`, `thanks`); enforce both in backend queries and writes.
- Keep organization visibility separate from user-type permissions. Resolve `/org/...` through `organization_context()`, treat `X-Team-Org-Path` as an untrusted selection, and scope every people-centered read and write on the server.
- Separate direct members, inherited ancestors, and broader route visibility. Only meetings and announcement topics inherit downward; morning items, shifts, attendance, red/black scores, and Thank You candidates/activity/rankings must use direct members of the selected organization.
- Treat meeting topic libraries, machines, and Team Moments as exact-team assets. Scope them with `organization_current_entity_filter()` and never inherit them across organization levels.
- Use descendant users only for explicit coordination actions such as assigning an owner to an upper-level meeting agenda or an administrator inspecting a member workbench. Do not reuse that scope for attendance, shifts, morning meetings, scores, or Thank You.
- Test admin view, admin user view, at least two custom user types, and the dynamic guest template when the change affects access.

### Backend and data

- Use parameterized SQL and one transaction for multi-step writes.
- Record significant writes with `write_audit()`.
- Prefer soft deletion and recycle-bin integration for business history.
- Add schema changes through idempotent `CREATE TABLE IF NOT EXISTS`, `ensure_column()`, and conditional updates in `init_db()`.
- Keep `server.py` as a compatibility entry point. Put configuration in `team_loop/config.py`, migrations in `team_loop/database.py`, shared helpers in `team_loop/common.py`, and business methods in the matching Handler Mixin.
- Preserve WAL, per-request connections, busy timeout, bounded HTTP workers, and the one-minute session-touch throttle when changing concurrency-sensitive code.
- Preserve the bounded per-origin SSO HTTP pool, same-origin redirect protection, and Discovery cache stampede guard. Run both SSO smoke tests after changing identity-provider networking.
- Keep completed morning items visible for exactly the next Monday-Friday workday as read-only review rows; do not create another persisted carryover row for completed work.
- Poll only the lightweight morning version endpoint. Auto-refresh the full list only when no editor is active; otherwise show a pending-update state. Validate morning ordering against the complete direct-member participant set and keep drag plus arrow controls.
- Never commit or manually overwrite files under `data/`.
- Never test destructive migrations against the production database.
- Generate large preview data only with `scripts/seed_scale_mock.py` after Gray deployment. Keep its gray-only path guard, SQLite backup, `[MOCK]` ownership markers, repeatable cleanup, single transaction, and post-write integrity checks intact.

### Cross-module behavior

- Keep users and member profiles consistent.
- Validate member ordering against the complete member set visible in the selected organization route, return that same scoped list, and retain arrow controls as the keyboard/touch fallback for drag sorting.
- Treat OAuth2/OIDC settings as secrets: keep manual authorization, access-token and UserInfo endpoints grouped for administrators but never expose them publicly; isolate Client ID/Secret fields from browser credential autofill, never expose Client Secret, preserve password fields when submitted blank, and never persist or audit diagnostic Access Tokens. Resolve configured claim paths case-insensitively, support common OneAccess `userName`/`name`/`id` claims and common response envelopes, use `get_user_info` for the OneAccess OAuth2 preset, use employee ID as the managed account link, preserve the provider plus `sub` (or provider user ID) as the stable identity, map the deepest configured SSO group only into `suggested_org_unit_id`, and auto-provision unknown identities only as root-organization `guest` accounts with `classification_pending=1` until an administrator assigns a type and team. Bind the current `/org/...` route and allowlisted `view` to the one-time SSO state, reject external return targets, and restore only pages the authenticated user may access. Never move an existing account or historical data during login.
- Migrate organization-owned history only through `scripts/migrate_org_data.py`: preview first, back up before apply, keep the row manifest, and validate rollback on gray data before production.
- Keep public-domain traffic behind a loopback Nginx upstream. Trust forwarded IP/protocol only when `TEAM_LOOP_TRUST_PROXY=1` and the direct peer is loopback; production must use `TEAM_LOOP_REQUIRE_HTTPS=1`, reject direct HTTP login and mutations, and issue Secure cookies for HTTPS proxy requests.
- Keep workbench and morning-meeting data synchronized.
- Keep the morning navigator visually neutral across themes: theme-wide button rules must not turn every member entry into a primary action, and only the selected member should receive the accent treatment.
- Keep process instances as immutable snapshots of template nodes and parent relations at creation time. Templates are forests: empty parents are parallel roots, siblings are branches, parents must precede children, and required nodes cannot depend on optional nodes. Treat the mind-map editor as a projection of ordered parent keys rather than persisting coordinates. Lock children until the parent is complete and recursively reset descendants when a parent is unchecked. Parent templates inherit downward read-only; every signed-in user with process view access may create a current-team template, creators manage their own templates, administrators manage all current-team templates, and required nodes drive automatic completion.
- Keep shared date filters initialized to the current month without page-specific overrides.
- Preserve the selected shift range across post-submit calendar refreshes; selecting a new calendar day may reset both range endpoints.
- Keep meeting state locks enforced by the server.
- Keep meeting creation controlled by `meetings.create`, while first-level topic categories and second-level preset maintenance remain administrator-only.
- Keep the forum-style team discussion area searchable and paginated; enforce author/admin edit, announcement, pin, soft-delete, and restore boundaries in the backend.
- Keep Team Moments isolated under the `moments` module and the exact selected organization. Store image bytes in `team_moment_images`, validate MIME signatures and limits, do not inherit ancestor moments, and expose every retained image through the four-tile gallery and keyboard/mobile lightbox. Version protected image URLs and return no-store headers so database restore or gray/production switching cannot reuse stale image IDs. Cover six-image create/read/update/delete/restore, exact-team scope, and cache headers with `scripts/team_moments_smoke_test.py` plus `scripts/organization_scope_smoke_test.py`.
- Keep local AI knowledge-base dependencies in a separate service boundary. Reuse Team Loop identity and organization claims, enforce vector-store payload filters before retrieval, require source citations, and follow `docs/KNOWLEDGE_BASE.md` before adding model or vector-database dependencies.
- Keep the full discussion Emoji picker and Chinese data local under `static/vendor/`; do not introduce a CDN dependency.
- Keep Thank You weekly limits and red/black independent scoring semantics.
- Enforce black-score summary/detail visibility in backend responses; frontend hiding alone is insufficient.
- Keep guest access read-only and entirely driven by the reserved `guest` permission template.
- Preserve persistent session revocation, login throttling, optimistic versions, and atomic shift-conflict checks when touching shared write paths.

## Validate

Run at minimum:

```powershell
python -m compileall -q server.py team_loop scripts
python scripts\process_flow_smoke_test.py
python scripts\organization_scope_smoke_test.py
python scripts\sso_smoke_test.py
python scripts\sso_pool_smoke_test.py
python scripts\morning_retention_smoke_test.py
python scripts\forum_smoke_test.py
python scripts\proxy_smoke_test.py
python scripts\concurrency_smoke_test.py
node --check static\app.js
git diff --check
```

Then test the affected API and UI states. For frontend work, inspect desktop and narrow layouts, long text, empty data, repeated clicks, error feedback, and role-restricted controls.

For database or deployment changes, deploy Gray and test against its isolated snapshot before production promotion:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Action Gray
python scripts\safety_feature_test.py --base-url http://127.0.0.1:8001 --database data\deploy\gray\weekly_team_gray.db
```

For 100-person list and density checks, run the scale seed only after the Gray snapshot is ready:

```powershell
python scripts\seed_scale_mock.py --dry-run
python scripts\seed_scale_mock.py
```

Never run the scale seed against production, promote its database, or commit its database and backup files.

Do not promote or push unless the user explicitly asks.

## Update documentation

Update documentation in the same change when behavior, commands, permissions, API contracts, schema, or deployment steps change:

- User behavior: `docs/USER_GUIDE.md`
- Architecture and extension rules: `docs/DEVELOPMENT.md`
- Endpoints: `docs/API.md`
- Tables, migration, backup: `docs/DATABASE.md`
- Deployment and operations: `docs/DEPLOYMENT.md`
- Common failures: `docs/TROUBLESHOOTING.md`

Keep `README.md` concise and use it as the entry point rather than duplicating all details.

## Release

When authorized to publish:

1. Confirm only intended files are modified.
2. Run the validation suite.
3. Stage explicit paths.
4. Commit with a concise behavior-oriented message.
5. Push the requested branch.
6. Report the commit, branch, validation, and environment status.

Do not include databases, backups, runtime logs, screenshots with real employee data, credentials, or gray test records.
