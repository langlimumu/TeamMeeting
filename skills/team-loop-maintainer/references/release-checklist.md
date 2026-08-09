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
- Confirm the gray port and production port are distinct.

## Gray verification

- Check `/api/health` reports `environment=gray` and `database=ok`.
- Test success, invalid input, repeat action, and permission failure.
- Run `scripts/safety_feature_test.py` when sessions, permissions, participation scopes, optimistic writes, or shifts changed.
- Verify bulk account-type changes and confirm excluded users disappear only from current business lists while history remains.
- Verify organization `all/subtree/unit` scopes, bulk organization assignment, nested `/org/...` routes, scoped business writes, and blocked deletion of organizations with children or active users.
- Verify the sidebar organization tree expands and collapses by branch, defaults to the selected path, closes after selection/outside click, and does not overflow at desktop, medium, or mobile widths.
- Verify upper meetings and announcements appear read-only in descendants, ordinary discussions do not inherit, descendants can reply/react to inherited announcements, cross-team Thank You appears for both parties and common ancestors, and unrelated sibling teams cannot see it.
- If SSO organization mapping changed, verify deepest-group matching creates a suggestion only, existing-user organizations never change during login, new users stay at root, administrators can adopt suggestions individually and in bulk, and redirect uses the current formal organization route.
- If authentication changed, run `python scripts\sso_smoke_test.py`; confirm existing employee IDs link without duplicates, new identities are read-only pending accounts, administrator classification clears the pending state, local fallback remains available, auto login cannot loop, the original organization route and module survive SSO, external return targets are rejected, and no SSO secret or endpoint appears in `/api/me`.
- Run `python scripts\sso_pool_smoke_test.py`; verify concurrent requests stay within the configured per-origin connection limit and concurrent Discovery calls collapse to one provider request.
- Run `python scripts\morning_retention_smoke_test.py`; verify Friday completions remain visible on Monday and disappear on Tuesday while unfinished items continue carrying forward.
- Verify manual SSO mode clearly groups OAuth2 authorization, Access Token and UserInfo addresses, reports missing required fields without submitting, and keeps a blank Client Secret unchanged.
- If organization migration changed, run `python scripts\org_data_migration_test.py`; preview a gray database, confirm apply creates both backup and manifest, and verify manifest rollback restores every moved row.
- If proxy or cookie handling changed, run `python scripts\proxy_smoke_test.py`; confirm direct HTTP login returns 426, HTTPS forwarding produces Secure cookies, and the forwarded client IP is stored. Validate Nginx with `nginx -t` before reload.
- Verify a non-admin with `meetings.create` can create a timed meeting and select presets, but cannot maintain topic categories or preset definitions.
- Run `python scripts\process_flow_smoke_test.py`; verify inherited templates are read-only, members can generate and tick only their own flows, child nodes remain locked until their parent completes, parent resets cascade to descendants, required items drive completion, and template edits do not alter existing tree snapshots.
- Create a template from the mind map: add a child and a parallel line, select each graph node to edit it, save, reopen, and confirm the same parent relations render.
- In a nested organization route, drag a member card and confirm only that route's complete member set is submitted and the order persists after refresh; also test the arrow fallback.
- Verify attendance opens in a modal and meeting email generation works both with and without Thank You content.
- Verify the local full Emoji picker loads, searches, sends an arbitrary Emoji, and can remove the reaction without external network access.
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
- Re-run Gray once when deployment scripts or migrations changed; repeated deployment must work on Windows.

## Before commit and push

- Review `git diff --stat` and the full relevant diff.
- Update user, developer, API, database, or deployment docs as required.
- Stage explicit intended paths.
- Commit only after checks pass.
- Push only when the user explicitly requests it.

## Before production promotion

- Obtain explicit approval.
- Confirm users have stopped critical writes.
- Ensure Gray matches the intended commit.
- Confirm a current production backup exists.
- Run `Promote`, then health and smoke tests.
- Keep rollback metadata and report the deployed release ID.
