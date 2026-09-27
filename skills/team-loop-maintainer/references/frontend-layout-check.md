# Frontend layout verification without browser automation

No browser-automation dependency is installed in this repository, and installing one (Chromium ≈500 MB) is not worth it for a single visual check. Windows machines normally already have Chrome or Edge, which can render, measure, and screenshot a page headlessly.

## Recipe

1. Write a throwaway harness under the repository root that links the real stylesheet and copies the real markup for the panel under test. Do not hand-write a simplified version — the bugs live in the real mix of classes.

```html
<link rel="stylesheet" href="static/style.css" />
...
<pre id="report"></pre>
<script>
  function run() {
    const box = document.querySelector(".norm-side");           // panel under test
    const cs = getComputedStyle(box);
    const r = box.getBoundingClientRect();
    const innerRight = r.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth);
    const bad = [];
    box.querySelectorAll("*").forEach((el) => {
      const er = el.getBoundingClientRect();
      if (!er.width && !er.height) return;
      const over = er.right - innerRight;
      const selfOver = el.scrollWidth - el.clientWidth;
      if (over > 0.5 || selfOver > 0.5) {
        bad.push(`${el.tagName}.${el.className} rightOver=${over.toFixed(1)} selfOver=${selfOver}`);
      }
    });
    document.body.innerHTML = `<pre>${bad.join("\n") || "CLEAN"}</pre>`;
  }
  window.addEventListener("load", () => setTimeout(run, 60));
</script>
```

2. Dump the measured DOM at several viewport widths — this is the part that catches breakpoint bugs:

```powershell
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
foreach ($w in 1920,1440,1280,1101,1100,980,820,620) {
  & $chrome --headless=new --disable-gpu --no-sandbox --virtual-time-budget=3500 `
    --window-size="$w,1000" --user-data-dir="$dir\p$w" --dump-dom "file:///<repo>/_harness.html" 2>$null |
    Out-File -Encoding utf8 "$dir\dom_$w.txt"
}
```

3. To look at it instead of reading numbers, skip the body replacement (guard it with a `?keep=1` query check) and screenshot. `--screenshot` needs a plain path, not a `file://` URL, and the path must not contain characters Chrome rejects — use forward slashes:

```powershell
& $chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars --virtual-time-budget=4000 `
  --window-size=1440,1300 --screenshot=D:/path/shot.png "file:///<repo>/_harness.html?keep=1"
```

4. Read the PNG with the Read tool to eyeball it, then delete every harness/`_*` artifact. Chrome profile directories (`--user-data-dir`) pile up fast; remove the whole scratch directory.

## Testing frontend logic without a browser

`node --check static/app.js` only proves the file parses — it never executes a render function. For pure logic that lives in `app.js` (link/escape helpers, tree builders, formatters) you can run the **real function bodies** in Node without any browser:

1. Read `static/app.js` and slice out each function by brace-matching from `function name(` to the closing brace at depth 0, plus any `const` it closes over (e.g. `normLinkPattern`).
2. Assemble them into one `new Function("state", code)` with a stub `state`, and call them directly.

This catches the classes of bug a syntax check cannot: an `/g` regex whose `lastIndex` leaks between calls (call the same formatter twice with the same input and compare), an escape step that runs after link substitution instead of before, a protocol filter that accepts `javascript:` or `data:`, and tree-building that drops a child when its parent is missing from the payload or treats a self-referencing `parent_id` as both parent and child. Rendering into the DOM still needs the screenshot pass — but keep the two concerns separate and run this one first, it is a second and takes no browser.

## Known layout pitfalls in this codebase

- **Never put `display: flex` (or `grid`) on a `<td>` / `<th>`.** The browser wraps it in an anonymous table-cell, so the real box is the inner flex box and `border-bottom` draws at the wrong height — the row's underline stops matching its neighbours. Wrap the flex container in a `<div>` inside the cell and style that (`.user-actions-cell`).
- **A global `input, select, textarea` rule sets `width: 100%` and `min-height: 36px`.** Every checkbox needs its own container rule declaring `width`, `min-width`, `height` **and** `min-height` (with the `min-` variants spelled out, browsers disagree on which one wins). Descendant selectors must exclude checkboxes with `:not([type="checkbox"])`.
- **Fixed-width grid columns overflow instead of shrinking.** `.norm-layout` uses `minmax(0, 1fr) 340px`, so the side panel has 306 px of content width. A child whose `min-content` exceeds that (`.form-row.slim` needs 180 + 130 + button ≈ 372 px) widens the *implicit* grid column of the panel, which drags every sibling section out past the border. Guard narrow columns with an explicit `grid-template-columns: minmax(0, 1fr)`, add `min-width: 0` to the direct children, and stack wide forms inside them with a `min-width` media query that matches the layout breakpoint.
- **A bare element selector in a shared responsive rule leaks onto every other element with that tag.** The sidebar breakpoint rules under `@media (max-width: 1180px)` / `(max-width: 720px)` / `(max-width: 620px)` were written as `nav { … }` and `body[data-theme] nav { … }` while the intent was `.sidebar nav`. That was invisible while the sidebar nav was the only `<nav>` in the app; once the norms page added `<nav id="normDocNav">`, the document category nav silently inherited `grid-area: nav` — a **named grid line that does not exist**, so the browser synthesised phantom tracks and squeezed the document body to ~86 px at narrow widths. The tell is `getComputedStyle(el).gridColumnStart` returning `nav` instead of `auto`. All sidebar-intent `nav` rules are now scoped to `.sidebar nav`; keep them scoped, and prefer a class over a bare tag name in any rule shared across pages.
- **A harness that forgets `.page.active` measures nothing and reports a false CLEAN.** `.page { display: none }` and only `.page.active { display: grid }`, so lifting the real `<section id="norms" class="page">` markup into a harness without adding `active` gives every container `getBoundingClientRect().width === 0` while `getComputedStyle` still returns real values (display, colors, grid templates) — the numbers look plausible and every overflow check trivially passes. Symptom: several unrelated containers all report `w=0.0 CLEAN` in the same run. Always assert a non-zero width for at least one box under test before trusting a clean report, and prefer `w=` values in the output over a bare CLEAN. Two related traps in the same probe: `scrollWidth - clientWidth > 0` on an element with `text-overflow: ellipsis` is **expected**, not a bug (a truncated `.norm-nav-name` always trips it, so read `rightOver` — negative means no overflow past the container — rather than the self-overflow number alone); and `--screenshot` with no `?keep=1` captures the probe's own report text instead of the page, because the probe replaces `document.body`.
- **A two-level tree needs its narrow-width override written after the base rule, and `[hidden]` needs re-declaring.** The norms category nav indents sub-entries via `.norm-nav-children` (`border-left: 1px dashed`) and collapses via the `hidden` **attribute** under a base rule `.norm-nav-children[hidden] { display: none }`. The `≤1360px` breakpoint flattens the same container into the wrapping top bar (`display: flex`, no border) and, because there is no vertical hierarchy in a horizontal bar, also unfolds collapsed groups — which requires re-declaring `.norm-nav-children[hidden] { display: flex }` **after** the base rule, since both are `(0,2,0)` and source order decides. Same-specificity overrides that lose silently are the recurring failure mode of this file: `grep` the selector and confirm each override's source position, not just its existence.
- **A new `<button>`-shaped component in the norms nav needs the theme pair, the toggle included.** The collapse/expand arrow (`.norm-nav-toggle`) is a bare `<button>` with a class and no `.secondary`, so it lands squarely in the `body[data-theme="miro"] button` leak. Verify it the cheap way: put a classless control `<button>` in the harness and assert it comes back `rgb(91, 118, 254)` (miro) / `rgb(22, 119, 255)` (dingtalk) — that proves the harness can see the leak — then assert the new component's `backgroundColor` is `rgba(0, 0, 0, 0)` in both themes. Also check the default theme, where a bare `button` is primary blue by default and only the component class overrides it.
- **A theme-scoped `button` rule repaints every new button-shaped component.** `body[data-theme="miro"] button` / `body[data-theme="dingtalk"] button` set `background: var(--blue); color: #fff; border: 1px solid var(--blue)` to make real action buttons look primary. Their specificity is `(0,1,2)` — attribute selector plus two element selectors — which **beats a single-class component rule** like `.norm-nav-item` `(0,1,0)`. So the six category-nav `<button>`s rendered as solid indigo pills in those themes. Note `body[data-theme] .topbar > .toolbar > button` and the other theme button rules are container-scoped and harmless; only the bare `button` ones leak. Two fixes are in the codebase: the morning navigator avoided `<button>` altogether and used `<div>` entries, while the norms nav keeps native button semantics and adds the house-style variant pair. Prefer the pair, it keeps keyboard and screen-reader behaviour:
  ```css
  .norm-nav-item,
  body[data-theme] .norm-nav-item { … }        /* (0,2,1) > (0,1,2) */
  .norm-nav-item:hover,
  body[data-theme] .norm-nav-item:hover { … }  /* also needed: theme hover rules are (0,2,2) */
  ```
  Verify with `getComputedStyle` — `backgroundColor` should be `rgba(0, 0, 0, 0)` on an unselected entry. Keep a **control `<button>`** with no class in the harness: if it comes back `rgb(91, 118, 254)` (miro) or `rgb(22, 119, 255)` (dingtalk), the leak is live and the harness is measuring the right thing.
- **A specificity bump is never local — it also outranks the component's own media-query overrides.** `.norm-nav-item { width: 100% }` was overridden at `≤1360px` by a later `.norm-nav-item { width: auto }`: same specificity, so source order decided it. The moment the base rule became `body[data-theme] .norm-nav-item` `(0,2,1)`, that `(0,1,0)` media override silently stopped applying and the narrow layout fell back to a full-width stacked list instead of the wrapping top bar. Fixing the leak therefore requires pairing **every** override of the affected selector, media queries included (`grep` the selector and check each hit). And run the probe at a **narrow** width as well — a wide-only check cannot see this class of regression. A screenshot is the cheapest way to catch it: the stacked-vs-wrapped difference is obvious to the eye and invisible in a `bodyWidth == docWidth` measurement.
- **Action buttons inside a directory row must be siblings, and the row grid needs an `auto` third column.** The norms nav rows carry a name plus an optional `＋` / `×`. A `<button>` cannot contain another `<button>` (the parser closes the first one), so the row is a 3-column grid `20px minmax(0, 1fr) auto` — toggle, name button, then a `<div class="norm-nav-actions">` holding the action buttons as siblings of the name button, never inside it. Two follow-ons: the name column must be `minmax(0, 1fr)` or a long category name pushes the actions past the nav's right edge (use the probe's `rightOver` for this, the name's own `scrollWidth` trips on the ellipsis by design); and when the nav flattens to the narrow top bar the actions need to stay reachable, so check `toggleVisible` and the action buttons' `rightOver` at the narrow widths too. Verify the sibling structure with a script, not by eye: walk the row HTML and assert every `</button>` precedes the next `<button>` (a nesting bug renders fine in a wide screenshot and only breaks the click target). **Renaming swaps the name cell for an `<input>`, replacing the name `<button>` outright** — an `<input>` is interactive, so it cannot be nested inside a `<button>` any more than a second `<button>` can; it sits in the same `minmax(0, 1fr)` cell as a `.norm-nav-editing` span, which is why the first column can stay at 236 px. Inside that cell `width: 100%` resolves against the grid track, but in the **narrow top bar** the row becomes a flex container and `.norm-nav-editing`'s width is content-driven — `width: 100%` on the input then has no definite parent to resolve against and collapses to a sliver, so the media query gives the span an explicit `flex: 1 1 180px`. The create form is a modal (`#normCategoryModal`) used **only** for creating (both levels through a hidden `parent_id`); it is shown by removing the `hidden` attribute, so it also needs the `[hidden]`-vs-display source-order check called out above.
- **`file://` harnesses give you computed styles but not CSSOM rules.** `getComputedStyle` works fine from a file URL, so a paint/size probe needs no server. Dumping `document.styleSheets[i].cssRules` does **not**: it throws a `SecurityError` for a cross-origin sheet, so a file-URL harness cannot tell you which rule actually won. Serve the repo (`python -m http.server 8899 --bind 127.0.0.1`) and load `http://127.0.0.1:8899/_harness.html` whenever you need to dump matching rules. Two scratch habits that cost time if ignored: write probe output **inside the repo**, because this sandbox's `/tmp` does not survive between tool calls (a later parse step just sees "file missing"); and a `--user-data-dir` under the repo leaves a Chrome profile tree that floods `grep` — delete the whole directory when done.
- **When dumping matching rules, detect a grouping rule by `rule.selectorText === undefined`, not by `rule.cssRules`.** Modern Chrome gives plain `CSSStyleRule` objects a `cssRules` list as well (for CSS nesting), so a recursive walk written as `if (rule.cssRules) { recurse } else { collect }` recurses into an empty list on every style rule and silently reports zero matches — which looks like "no rule applies" and sends you chasing the wrong theory.
- **A badge placed with negative offsets is a clipping risk, not a style choice.** The norm illustration thumbnails carry a `×` remove button; written the usual way — `position: absolute; top: -6px; right: -6px` against a `position: relative` 72 px `<figure>` — it hangs 6 px outside every thumbnail, so the row silently widens by that much and the top-right one gets clipped once the panel's padding is smaller than the offset. It shows up as `scrollWidth > clientWidth` on the container, never as something visible in a wide screenshot. The cheap fix is to move the badge **inside** the frame (`top: 2px; right: 2px`); if it genuinely must overhang, the container needs at least that much padding. It is also a bare `<button>`, so it still needs the `X, body[data-theme] X` pair — for the sizing properties only, since the colours are supposed to come from the theme.
- **A `position: absolute` popover needs its anchor to be `position: relative`, and its hide rule must out-rank its own `display`.** The norms header search box renders hits in `.norm-search-results` (`position: absolute; z-index: 30; top: calc(100% + 6px)`), which only drops under the input because `.norm-search` is `position: relative` — without that the layer anchors to the nearest positioned ancestor or the viewport and drifts away from the field. The layer's own rule sets `display: grid`, so it is closed by toggling the `.hidden` class, and that works **only** because `.hidden` is `display: none !important` — a plain `.hidden { display: none }` at equal specificity declared *earlier* in the file would lose to this later rule and the popover would never shut. If you add another popover, either keep using the `!important` helper or re-declare the hide rule *after* the component. The input inside it is a bare `<input>`, so the global `input { width: 100%; min-height: 36px }` hits it: pair the selector (`X, body[data-theme] X`) and give it an explicit `min-height` so it sits in the toolbar. Finally, `.norm-article.is-highlighted` is **transient** (the jump timer strips it after ≈2 s), so a probe that measures late reports no highlight even when the jump itself worked — assert the scroll position, or widen the window.
- Static assets are served with `no-store, no-cache, must-revalidate, max-age=0`, so plain reloads are enough; Ctrl+F5 is not required.
