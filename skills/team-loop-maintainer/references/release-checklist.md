# Team Loop release checklist

## Before editing

- Read the relevant docs and inspect `git status -sb`.
- Identify user roles and affected modules.
- Decide whether the change needs schema migration, audit, recycle-bin, or backup behavior.

## Before gray

- Run Python compilation, JavaScript syntax, and `git diff --check`.
- Confirm the release snapshot contains both `server.py` and the `team_loop/` package.
- Verify no file under `data/` is staged.
- Confirm migrations are idempotent.
- If a schema change adds a column or replaces an index, prove the **old-database upgrade path** on a synthetic old-schema database first: create a temp DB using the pre-change DDL, run `init_db()` against it, then assert the new column exists, the intended index replaced the old one, and every pre-existing row survived with the new column left at its default. Opening the real production database is not an acceptable substitute — that path is what the gray `--migrate-only` pass exercises, and it must not be the first time it runs. Watch for `CREATE UNIQUE INDEX IF NOT EXISTS`: swapping a unique index to a different scope needs an explicit `DROP INDEX IF EXISTS` of the old name, otherwise `IF NOT EXISTS` silently keeps the old, wider constraint.
- Confirm the gray port and production port are distinct.

## Gray verification

- Check `/api/health` reports `environment=gray` and `database=ok`.
- The gray, promote and rollback gates all run `scripts\smoke_test.py` automatically. It reads `/api/me` and probes the read endpoint of every module the instance reports as guest-visible, which is editable data — so changing the guest permission template must never turn the gate red. Never put a hard-coded module list back into that script: a red gate has to mean the module gate and the template disagree, or the template grants no module at all.
- Test success, invalid input, repeat action, and permission failure.
- Run `scripts/safety_feature_test.py` when sessions, permissions, participation scopes, optimistic writes, or shifts changed.
- Verify bulk account-type changes and confirm excluded users disappear only from current business lists while history remains.
- Verify organization `all/subtree/unit` scopes, bulk organization assignment, nested `/org/...` routes, scoped business writes, and blocked deletion of organizations with children or active users.
- Verify the sidebar organization tree expands and collapses by branch, defaults to the selected path, closes after selection/outside click, and does not overflow at desktop, medium, or mobile widths.
- Verify upper meetings and announcements appear read-only in descendants and ordinary discussions do not inherit. Confirm morning, shift, attendance, red/black and Thank You lists contain only direct members of the selected organization, including for administrators with subtree access.
- If SSO organization mapping changed, verify deepest-group matching creates a suggestion only, existing-user organizations never change during login, new users stay at root, administrators can adopt suggestions individually and in bulk, and redirect uses the current formal organization route.
- If authentication changed, run `python scripts\sso_smoke_test.py`; confirm existing employee IDs link without duplicates, new identities are read-only pending accounts, administrator classification clears the pending state, local fallback remains available, auto login cannot loop, the original organization route and module survive SSO, external return targets are rejected, and no SSO secret or endpoint appears in `/api/me`.
- Run `python scripts\sso_pool_smoke_test.py`; verify concurrent requests stay within the configured per-origin connection limit and concurrent Discovery calls collapse to one provider request.
- Run `python scripts\morning_retention_smoke_test.py`; verify Friday completions remain visible on Monday and disappear on Tuesday while unfinished items continue carrying forward.
- Open morning meeting in two sessions: update in one, confirm the other detects the lightweight version and refreshes automatically when idle, but preserves active form input and shows a manual refresh state while editing. Verify right-side member navigation jumps correctly, drag ordering persists, and arrow controls work on touch/keyboard layouts.
- Verify manual SSO mode clearly groups OAuth2 authorization, Access Token and UserInfo addresses, reports missing required fields without submitting, and keeps a blank Client Secret unchanged.
- If organization migration changed, run `python scripts\org_data_migration_test.py`; preview a gray database, confirm apply creates both backup and manifest, and verify manifest rollback restores every moved row.
- If proxy or cookie handling changed, run `python scripts\proxy_smoke_test.py`; confirm direct HTTP login returns 426, HTTPS forwarding produces Secure cookies, and the forwarded client IP is stored. Validate Nginx with `nginx -t` before reload.
- Verify a non-admin with `meetings.create` can create a timed meeting and select presets, but cannot maintain topic categories or preset definitions.
- Run `python scripts\process_flow_smoke_test.py`; verify inherited templates are read-only, members can generate and tick only their own flows, child nodes remain locked until their parent completes, parent resets cascade to descendants, required items drive completion, and template edits do not alter existing tree snapshots.
- Create a template from the mind map: add a child and a parallel line, select each graph node to edit it, save, reopen, and confirm the same parent relations render.
- In a nested organization route, drag a member card and confirm only that route's complete member set is submitted and the order persists after refresh; also test the arrow fallback.
- Verify attendance opens in a modal and meeting email generation works both with and without Thank You content.
- Verify the local full Emoji picker loads, searches, sends an arbitrary Emoji, and can remove the reaction without external network access.
- Verify the team-norms page at desktop and narrow widths: a sub-shelf is indented under its parent and the expand/collapse arrow works, a parent document shows **only** its own clauses while the sub-shelf owns a separate document numbering from 1 again, an empty shelf still renders its own empty document, and a body containing `[文字](https://…)` renders as a clickable link that survives into the downloaded `.md`. Confirm that adding a third level is rejected, that a shelf with sub-shelves cannot be deleted, and that two different parents may each hold a same-named sub-shelf. **Shelf position is fixed in the UI**: the right-hand 规范分类 panel was removed, so there is no "change parent" and no "deactivate" control anywhere — confirm the norms page shows only the left shelf tree plus the 随手记 form. (The API still accepts `parent_id` / `active` for administrators; the UI simply never sends them.) Editing is **inline** now: every clause whose `can_edit` is true carries 「编辑」 in its own title row, and one whose `can_delete` is true also carries 「删除」 (both are author-plus-admin, so a member sees the pair only on their own clauses, an admin sees them on all), there is no 规范条目 list below the document any more, and clicking a shelf on the left switches the right-hand form's category by itself — including the case where the form is mid-edit, which must **not** follow navigation. Also confirm both buttons disappear in "preview as type" mode even for an admin. The form must have **no 生效/失效日期 and no 状态 controls** (two-state model: record it and it is live, delete it and it goes to the recycle bin); saving a clause must land you on its shelf with that clause flashed, which only works because `create_norm` / `update_norm` return `{norm_id, category_id}`. The header **search box** must find a clause by a word from its title / content / scope / source across all shelves and jump+highlight it on click, and clearing it or pressing Esc must close the results.
- Verify the norms-category **permission tiers** with three identities, because each has a different failure mode. (1) A normal member: the left nav shows 「＋ 一级目录」 and a `＋` on top-level rows, and a `×` only on shelves **they created** — check it is absent on a colleague's shelf and on the seeded categories, and that a hand-crafted `DELETE /api/norm-categories/{id}` on someone else's shelf returns 403, not 200. Renaming is a **double-click on the shelf name** (there is no rename button): on their own shelf it must turn the name into an input (Enter saves, `Escape` cancels, clicking elsewhere saves, and the hint line says so); on a colleague's or a seeded shelf the same double-click must only raise a toast and leave the name alone; and the rename must leave `parent_id` untouched. Sending `parent_id` or `active` in the PATCH must return **403** (refused, not silently ignored) — no UI path reaches it any more, so craft the request by hand; a name-only `PATCH` must keep the description the shelf already had. The same author-plus-admin rule now covers **clauses**, not just shelves: the 「删除」 on their own clause must succeed and land it in the recycle bin (restore brings it back), while a hand-crafted `DELETE /api/norms/{id}` on a colleague's clause must return **403** — this is the case that used to be module-level (admins only) and is deliberately no longer so, and because the route remaps clause deletion to the module `edit` action, a passing UI check here is not enough on its own. (2) A guest / unauthenticated visitor: reads the document (200) but sees **no** `＋` or `×`, double-clicking a shelf name only toasts, and a raw `POST /api/norm-categories` returns 401. (3) An administrator: may rename and delete on **every** shelf including the six seeded ones, and in "preview as user" mode both rights disappear again — that is a deliberate client-side guard (ownership cannot be derived from a *type*, and the preview is not mirrored server-side), not a change in `can_delete` / `can_rename`; `＋` should still follow the previewed type. Never accept a UI-only pass here — the whole point of shipping those flags from the server is that a button's absence and a 403 must always agree.
- Verify norm **illustrations** end to end, with three identities. A member uploads one from the form (and separately pastes a screenshot into the body field): a `[[img:12]]` marker must land at the caret and a thumbnail must appear below the form; once saved, the document must show the **image, not the marker**. Then remove the thumbnail's `×` and save — the image leaves the document but its **file must survive** (releasing is reversible: paste the marker back and the picture returns), which you can only confirm by looking at `data/uploads/norms/`, since the UI deliberately offers no "delete image" action. A guest who may read the document must be able to read its illustration (200), while `POST /api/norm-images` without a session must return **401**, a non-numeric id (`/api/norm-images/abc`) must return **404** (not 500), and a body referencing an unknown id must be refused on save with **400**. Check the image response carries `X-Content-Type-Options: nosniff` and a `Cache-Control` that is **not** `no-store` — that header is precisely why illustrations are not served through the static handler. Finally confirm the bytes land under `data/uploads/norms/` and **not** under `static/`: whatever sits in `static/` gets frozen into the next release snapshot, and `robocopy /MIR /XD data` deletes what it does not know about.
- Run `python scripts\forum_smoke_test.py`; verify author edits, nested replies, arbitrary Emoji, announcement/pin privilege rejection, soft deletion, recycle restore, and preserved replies.
- Run `python scripts\team_moments_smoke_test.py`; verify guest denial by default, six-image upload, versioned no-store protected image reads, editing, soft deletion, and recycle restore. In the UI confirm the fourth tile opens all thumbnails and arrow-key/mobile navigation works.
- Run `python scripts\concurrency_smoke_test.py`; verify 100 mixed requests finish without lock errors, WAL is active, all writes persist, and `quick_check` is `ok`.
- Toggle black-score summary and detail visibility independently; verify non-admin APIs and UI hide the configured data while administrators still see and can restore it.
- Verify the score page defaults to the current month, detail rows are newest-first and scroll, and a member click opens only that member's full history.
- Verify shared date filters default to the first day of the current month through today.
- Submit a multi-day shift batch and confirm the calendar refreshes while the selected end date remains unchanged; selecting a different day should reset the range.
- Test `1440x1000`, `1024x768`, `768x800`, and `390x844` viewports across every visible module.
- Confirm the document itself has no horizontal overflow; calendars, tables, flow trees, and mind maps may scroll only inside their own containers.
- Confirm mobile account controls expand correctly, the active navigation item scrolls into view, dialogs fit `100dvh`, and edge popovers remain inside the viewport.
- Verify gray writes do not appear in production.
- When using 100-person preview data, run `scripts/seed_scale_mock.py` only after Gray deployment; confirm exactly 100 active users, a clean foreign-key check and `quick_check=ok`, then verify dense member, morning, meeting, shift, score, Thank You, forum, process, link and moment views. Never promote that gray database.
- Re-run Gray once when deployment scripts or migrations changed; repeated deployment must work on Windows.

## Before commit and push

- Review `git diff --stat` and the full relevant diff.
- Update user, developer, API, database, or deployment docs as required.
- Read `git status --short` for stray files before staging. A 0-byte file named `python` once appeared at the repository root from a mistyped command, and `git add -A` would have committed it — always stage explicit intended paths.
- Fix `git diff --check` findings. `new blank line at EOF` is a real signal here: every module under `team_loop/` ends with **two** trailing blank lines, so restore that exact count (`data.rstrip(b"\r\n") + b"\r\n\r\n\r\n"`) instead of collapsing to a single newline, and leave files that already had a different count untouched to avoid churn. The working tree is CRLF — do not write mixed line endings.
- Commit only after checks pass.
- Push only when the user explicitly requests it.
- After pushing, confirm `git status --short --branch` is clean and `git rev-list --left-right --count origin/main...main` prints `0	0`.

## Before production promotion

- Obtain explicit approval.
- Confirm users have stopped critical writes.
- Ensure Gray matches the intended commit.
- Confirm a current production backup exists.
- Run `Promote`, then health and smoke tests.
- Keep rollback metadata and report the deployed release ID.
