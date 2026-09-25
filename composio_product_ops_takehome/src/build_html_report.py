from __future__ import annotations

import csv
import html
import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(os.environ.get("COMPOSIO_OUTPUT_DIR", str(ROOT / "output" / "evidence-v8-full")))
RESULTS_JSON = OUTPUT_DIR / "results.json"
CHECKPOINT_JSON = OUTPUT_DIR / "checkpoint.json"
VERIFY_QUEUE_JSON = OUTPUT_DIR / "verification_queue.json"
REVIEW_JSON = OUTPUT_DIR / "verification_review.json"
SITE_FILE = ROOT / "site" / "index.html"


def load_rows() -> tuple[list[dict], int, bool]:
    with (ROOT / "data" / "apps.csv").open(newline="", encoding="utf-8") as f:
        total = sum(1 for _ in csv.DictReader(f))
    if RESULTS_JSON.exists():
        data = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
        return data.get("results", []), total, True
    if CHECKPOINT_JSON.exists():
        data = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        rows = sorted(data.get("results", {}).values(), key=lambda x: int(x["id"].split("-")[1]))
        return rows, total, False
    raise FileNotFoundError(f"No research results found under {OUTPUT_DIR}")


def counts(rows: list[dict], field: str) -> Counter:
    return Counter((r.get(field) or "Unknown") for r in rows)


def distribution_html(label: str, values: Counter, total: int) -> str:
    if not values:
        return f'<section class="dist"><h3>{html.escape(label)}</h3><p class="muted">No rows yet.</p></section>'
    max_count = max(values.values()) or 1
    items = []
    for name, count in values.most_common():
        width = round(100 * count / max_count)
        items.append(
            f'<div class="barrow"><span>{html.escape(name)}</span>'
            f'<span class="bar"><i style="width:{width}%"></i></span>'
            f'<b>{count}<small>/{total}</small></b></div>'
        )
    return f'<section class="dist"><h3>{html.escape(label)}</h3>{"".join(items)}</section>'


def main() -> None:
    rows, total, complete = load_rows()
    unknown_fields = sum(
        1 for r in rows for field in ("auth", "access", "api", "mcp")
        if r.get(field, "Unknown") == "Unknown"
    )
    queue_count = 0
    if VERIFY_QUEUE_JSON.exists():
        try:
            queue_count = len(json.loads(VERIFY_QUEUE_JSON.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            queue_count = 0
    failed_search = sum(
        r.get("research_metadata", {}).get("search", {}).get("status") in {"failed", "partial_failure"}
        for r in rows
    )
    auth_dist = counts(rows, "auth")
    access_dist = counts(rows, "access")
    api_dist = counts(rows, "api")
    mcp_dist = counts(rows, "mcp")
    build_dist = counts(rows, "buildability")
    review = json.loads(REVIEW_JSON.read_text(encoding="utf-8")) if REVIEW_JSON.exists() else None
    gated = sum(access_dist.get(x, 0) for x in ("Gated", "Mixed"))
    self_serve = access_dist.get("Self-serve", 0)
    easy_wins = build_dist.get("High", 0)
    outreach = sum(
        1 for r in rows
        if r.get("access") in {"Gated", "Mixed"}
        or (r.get("access") == "Unknown" and (r.get("api") != "Unknown" or r.get("mcp") == "Available"))
    )
    blockers = Counter(
        r.get("blocker", "") for r in rows
        if r.get("blocker") and r.get("blocker") not in {"—", "None"}
    )
    top_blocker = blockers.most_common(1)[0] if blockers else None
    distributions = "".join(
        distribution_html(label, values, len(rows))
        for label, values in (("Authentication", auth_dist), ("Credential access", access_dist),
                              ("API surface", api_dist), ("MCP", mcp_dist), ("Buildability", build_dist))
    )
    category_rows = []
    for category in sorted({r.get("category", "Unknown") for r in rows}):
        members = [r for r in rows if r.get("category", "Unknown") == category]
        category_rows.append(
            "<tr><td>" + html.escape(category) + "</td>"
            + f"<td>{len(members)}</td><td>{sum(r.get('auth') != 'Unknown' for r in members)}</td>"
            + f"<td>{sum(r.get('access') == 'Self-serve' for r in members)}</td>"
            + f"<td>{sum(r.get('access') in {'Gated','Mixed'} for r in members)}</td>"
            + f"<td>{sum(r.get('api') != 'Unknown' for r in members)}</td>"
            + f"<td>{sum(r.get('mcp') == 'Available' for r in members)}</td>"
            + f"<td>{sum(r.get('buildability') == 'High' for r in members)}</td></tr>"
        )
    auth_leader = auth_dist.most_common(1)[0] if auth_dist else ("Unknown", 0)
    headline = (
        f"{auth_leader[0]} is the most common recorded auth value ({auth_leader[1]}/{len(rows)} rows). "
        f"{self_serve} rows are marked self-serve, {gated} gated or mixed, and {easy_wins} are high buildability."
        if rows else "Research is ready to run; no app records have been saved yet."
    )
    blocker_line = (
        f"Most frequent blocker label: {top_blocker[0]} ({top_blocker[1]} rows)."
        if top_blocker else "No blocker pattern has been recorded yet."
    )
    if review:
        review_rows = "".join(
            "<tr><td>" + html.escape(item["app"]) + "</td><td>"
            + html.escape(", ".join(f"{k}: {v}" for k, v in item["verified"].items() if v != "Unknown"))
            + "</td><td>" + html.escape(", ".join(
                item.get("sources", {}).get(k, "") for k, v in item["verified"].items()
                if v != "Unknown" and item.get("sources", {}).get(k)))
            + "</td></tr>" for item in review.get("apps", [])
        )
        review_section = (
            '<section class="panel"><h2>Earlier targeted review log</h2>'
            f'<p>{review.get("sample_size", 0)} apps have prior targeted review records. Earlier passes resolved '
            f'{review.get("unknowns_resolved_across_passes", 0)} Unknown fields and revised {review.get("other_changes", 0)} values. '
            'These are change counts, not accuracy hits; the separate manual browser pass below is the accuracy sample.</p>'
            '<p class="note">Historical review metadata and supporting official source links are shown here. Do not interpret the cumulative change totals as an accuracy estimate.</p>'
            '<div class="tablewrap"><table><thead><tr><th>App</th><th>Checked fields</th>'
            '<th>Official source URLs</th></tr></thead><tbody>' + review_rows + '</tbody></table></div></section>'
        )
        audit = review.get("human_audit", {})
        audit_rows = "".join(
            "<tr><td>" + html.escape(item["app"]) + "</td><td>"
            + html.escape(", ".join(item.get("fields", []))) + "</td><td>"
            + html.escape(item.get("result", "Checked")) + "</td><td>"
            + html.escape(item.get("note", "")) + "</td><td>"
            + html.escape(", ".join(item.get("sources", []))) + "</td></tr>"
            for item in audit.get("apps", [])
        )
        human_audit_section = (
            '<section class="panel"><h2>Manual browser verification</h2>'
            f'<p>{audit.get("apps_checked", 0)} apps and {audit.get("claims_checked", 0)} claims were checked against official documentation in this pass: '
            f'{audit.get("hits", 0)} matched on first check, {audit.get("misses", 0)} did not, and {audit.get("corrections", 0)} correction(s) were applied.</p>'
            f'<p class="note">{html.escape(audit.get("scope", ""))}</p>'
            '<div class="tablewrap"><table><thead><tr><th>App</th><th>Fields checked</th>'
            '<th>Result</th><th>Finding</th><th>Official docs opened</th></tr></thead><tbody>'
            + audit_rows + '</tbody></table></div></section>'
        ) if audit else ""
    else:
        review_section = '<section class="panel"><h2>Human cross-check sample</h2><p>No documented manual sample is present.</p></section>'
        human_audit_section = ""
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    status = "Full run" if complete and len(rows) >= total else "Partial snapshot"
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Composio Product Ops — 100-app API readiness audit</title>
<style>
:root{{--bg:#f4f6fa;--paper:#fff;--ink:#182338;--muted:#617089;--line:#dfe5ef;--blue:#315be8;--blue2:#e9efff;--green:#16734d;--amber:#9a5a00;--red:#a93636}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{max-width:1380px;margin:auto;padding:32px 22px 64px}}.hero{{padding:22px 0 26px}}.eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;font-weight:800;color:var(--blue)}}
h1{{font-size:clamp(32px,5vw,56px);letter-spacing:-.04em;line-height:1.04;margin:10px 0 14px}}h2{{font-size:24px;letter-spacing:-.02em;margin:0 0 12px}}h3{{font-size:16px;margin:0 0 14px}}p{{margin:8px 0}}.lede{{font-size:18px;max-width:850px;color:var(--muted)}}
.badge{{display:inline-flex;align-items:center;border-radius:99px;padding:5px 11px;background:var(--blue2);color:#2549c7;font-size:12px;font-weight:800}}.cards{{display:grid;grid-template-columns:repeat(5,minmax(120px,1fr));gap:12px;margin:20px 0 34px}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:16px;box-shadow:0 2px 8px #192b4d0a}}.card{{padding:17px}}.num{{font-size:30px;font-weight:850;letter-spacing:-.04em}}.muted{{color:var(--muted)}}.card .muted{{font-size:13px}}
section{{margin:30px 0}}.panel{{padding:22px}}.insight{{border-left:4px solid var(--blue);padding:2px 0 2px 16px;max-width:980px}}.distributions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.dist{{background:#f8faff;border:1px solid var(--line);border-radius:12px;padding:16px}}.barrow{{display:grid;grid-template-columns:minmax(105px,1.2fr) minmax(90px,2fr) 58px;align-items:center;gap:10px;font-size:13px;margin:9px 0}}.bar{{height:9px;background:#e3e9f5;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:var(--blue);border-radius:99px}}.barrow b{{text-align:right;font-variant-numeric:tabular-nums}}.barrow small{{font-weight:500;color:var(--muted)}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}input,select{{font:inherit;border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:white;color:var(--ink)}}input{{min-width:230px;flex:1}}.tablewrap{{overflow:auto;max-height:72vh;border:1px solid var(--line);border-radius:11px}}table{{border-collapse:collapse;width:100%;min-width:1120px;font-size:13px}}th,td{{padding:11px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{position:sticky;top:0;background:#f1f4fa;z-index:1;font-size:12px}}td:first-child{{font-weight:750}}.pill{{display:inline-block;border-radius:99px;background:#f0f3f9;padding:3px 8px;margin:1px 3px 2px 0;white-space:nowrap}}.unknown{{color:var(--muted)}}.yes{{color:var(--green);font-weight:700}}.links a{{display:inline-block;margin-right:6px;white-space:nowrap}}.evidenceitem{{border-top:1px solid var(--line);padding:7px 0;min-width:260px}}.evidenceitem p{{font-weight:400;color:var(--muted);max-width:420px;margin:4px 0;white-space:normal}}.note{{padding:12px 14px;background:#fff8e9;border:1px solid #f0ddad;border-radius:10px;color:#614817}}
footer{{padding:28px 0;color:var(--muted);font-size:13px}}@media(max-width:760px){{.cards{{grid-template-columns:repeat(2,1fr)}}.distributions{{grid-template-columns:1fr}}main{{padding:22px 14px}}}}
</style></head><body><main>
<header class="hero"><div class="eyebrow">Composio AI Product Ops · Product research</div><h1>100 apps, audited for agent readiness.</h1>
<p class="lede">An evidence-backed view of authentication, credential access, APIs, MCP support, and the remaining work to build each app into a reliable agent toolkit.</p><span class="badge">{status} · {len(rows)} of {total} apps</span></header>
<div class="cards"><div class="card"><div class="num">{total}</div><div class="muted">apps in research set</div></div><div class="card"><div class="num">{len(rows)}</div><div class="muted">records researched</div></div><div class="card"><div class="num">{unknown_fields}</div><div class="muted">unknown field values</div></div><div class="card"><div class="num">{failed_search}</div><div class="muted">rows with search failure/partial failure</div></div><div class="card"><div class="num">{queue_count}</div><div class="muted">items in verification queue</div></div></div>
<section class="panel"><h2>Patterns in the research</h2><p class="insight">{headline} {blocker_line}</p><p class="muted">Counts below use only the {len(rows)} records currently available. “Unknown” means the collected official evidence did not support a field value; it is not a negative claim.</p><div class="distributions">{distributions}</div><h3>Category comparison</h3><div class="tablewrap"><table><thead><tr><th>Category</th><th>Apps</th><th>Auth documented</th><th>Self-serve</th><th>Gated/mixed</th><th>API type documented</th><th>MCP available</th><th>High buildability</th></tr></thead><tbody>{"".join(category_rows)}</tbody></table></div></section>
<section class="panel"><h2>Research agent and reproducible run</h2><p>The Python agent reads the 100-app CSV, starts with seeded official documentation URLs, checks official domains, fetches pages, extracts claims only when evidence rules are met, and stores quotes, source links, search-provider errors, and verification queues. Direct-source fallbacks cover failed search-provider calls; the reconciliation pass adds reviewed official evidence without pretending those pages were fetched automatically.</p><p><strong>Human needed:</strong> source conflicts, account-role or plan gates, and fields the docs do not state (especially MCP support) require judgment. In the manual browser sample below, one auth claim was incomplete and corrected.</p><p><strong>Run the agent:</strong> from the project folder, run <code>./.venv/bin/python src/agent.py</code>. Then build this page with <code>COMPOSIO_OUTPUT_DIR=output/evidence-v8-full ./.venv/bin/python src/build_html_report.py</code>. See <a href="../README.md">README</a>, <a href="../src/agent.py">agent source</a>, and <a href="../src/reconcile_manual_review.py">review source</a>. Detailed field evidence is in <code>output/evidence-v8-full/results.json</code>.</p><p class="note">This is the local runnable deliverable. It has not been deployed to a public URL, and no remote repository URL is configured in this project.</p></section>
<section class="panel"><h2>App-by-app evidence</h2><p class="muted">Search by app or filter by category, access model, or MCP status. Source links open the pages used to support field claims.</p>
<div class="controls"><input id="q" type="search" placeholder="Search apps, categories, or descriptions"><select id="category"><option value="">All categories</option></select><select id="access"><option value="">All access models</option></select><select id="mcp"><option value="">All MCP statuses</option><option>Available</option><option>Unknown</option><option>Not found</option></select></div>
<div class="tablewrap"><table><thead><tr><th>App</th><th>Category &amp; one-line description</th><th>Auth methods</th><th>Credential access</th><th>API surface &amp; breadth</th><th>MCP</th><th>Buildability</th><th>Blocker</th><th>Evidence</th></tr></thead><tbody id="rows"><tr><td colspan="9">Loading…</td></tr></tbody></table></div></section>
{review_section}
{human_audit_section}
<section class="panel"><h2>Method and review limits</h2><p>The agent discovers official-domain pages, fetches documentation, extracts field claims with explicit rules, and records source URLs and text snippets. Search-provider failures are saved in each row’s metadata; official URLs and site links provide a fallback.</p><p>Positive MCP status requires app-specific MCP evidence. API type is reported only when documentation explicitly says REST, GraphQL, or SOAP. Breadth is not quantified unless the row has a separate breadth field; unknowns are not guessed. Free/trial, paid-plan, admin, or partner gates appear only when a source supports them.</p><p class="note"><strong>Human verification is still required.</strong> The verification queue identifies unknown and uncertain fields for review. The targeted sample is not a representative accuracy estimate.</p></section>
<footer>Generated from <code>{html.escape(str(OUTPUT_DIR.resolve().relative_to(ROOT)))}</code>. Source evidence and search metadata are retained in the accompanying JSON files.</footer>
</main><script>const DATA={data};
const field=(v)=>v||'Unknown';
const esc=(s)=>String(s??'');
function addOptions(id,key){{const sel=document.getElementById(id);[...new Set(DATA.map(r=>r[key]||'Unknown'))].sort().forEach(v=>{{const o=document.createElement('option');o.value=v;o.textContent=v;sel.appendChild(o)}})}}
addOptions('category','category');addOptions('access','access');
function render(){{const q=document.getElementById('q').value.toLowerCase(),cat=document.getElementById('category').value,acc=document.getElementById('access').value,mcp=document.getElementById('mcp').value;const body=document.getElementById('rows');body.replaceChildren();let shown=0;
for(const r of DATA){{if(cat&&r.category!==cat)continue;if(acc&&r.access!==acc)continue;if(mcp&&r.mcp!==mcp)continue;const blob=[r.app,r.category,r.description,r.auth,r.access,r.api,r.mcp,r.buildability,r.blocker].join(' ').toLowerCase();if(q&&!blob.includes(q))continue;shown++;const tr=document.createElement('tr');
const apiValue=field(r.api), breadth=r.api_breadth||(apiValue==='Unknown'?'Breadth unknown':'Breadth not separately quantified');const vals=[r.app,`${{r.category||'Unknown'}} · ${{r.description||'No description available'}}`,field(r.auth),field(r.access),`${{apiValue}} · ${{breadth}}`,field(r.mcp),field(r.buildability),r.blocker||'—'];for(let i=0;i<vals.length;i++){{const td=document.createElement('td');td.textContent=vals[i];if(vals[i]==='Unknown')td.className='unknown';if(i===5&&vals[i]==='Available')td.className='yes';tr.appendChild(td)}}
const td=document.createElement('td');td.className='links';const evidence=r.evidence||{{}};const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Quotes & sources';details.appendChild(summary);let hasEvidence=false;for(const key of ['auth','access','api','mcp']){{const ev=evidence[key]||{{}},line=document.createElement('div');line.className='evidenceitem';const label=document.createElement('b');label.textContent=key+': '+field(ev.value);line.appendChild(label);if(ev.source&&ev.source.startsWith('https://')){{const a=document.createElement('a');a.href=ev.source;a.target='_blank';a.rel='noopener noreferrer';a.textContent=' source';line.appendChild(a);hasEvidence=true}}const quote=document.createElement('p');quote.textContent=ev.quote||ev.rule||'No validated evidence';line.appendChild(quote);details.appendChild(line)}}if(hasEvidence)td.appendChild(details);else td.textContent='No validated source';tr.appendChild(td);body.appendChild(tr)}}
if(!shown){{const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=9;td.textContent='No apps match these filters.';tr.appendChild(td);body.appendChild(tr)}}}}
for(const id of ['q','category','access','mcp'])document.getElementById(id).addEventListener(id==='q'?'input':'change',render);render();</script></body></html>'''
    SITE_FILE.write_text(page, encoding="utf-8")
    print(f"Wrote {SITE_FILE} ({len(rows)}/{total} rows, {'complete' if complete else 'partial'})")


if __name__ == "__main__":
    main()
