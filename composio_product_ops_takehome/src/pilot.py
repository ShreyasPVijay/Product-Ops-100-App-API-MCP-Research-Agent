import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / 'data' / 'pilot_5.json'
out = ROOT / 'output'
out.mkdir(exist_ok=True)

records = json.loads(src.read_text())
required = ['app','auth_methods','access_model','api_surface','buildability','evidence_urls','confidence']
for r in records:
    missing = [k for k in required if not r.get(k)]
    if missing:
        raise ValueError(f"{r['app']}: missing {missing}")
    if not r['evidence_urls']:
        raise ValueError(f"{r['app']}: no evidence")
    if r['mcp_status'] == 'yes' and not any('mcp' in u.lower() for u in r['evidence_urls']):
        raise ValueError(f"{r['app']}: MCP positive without MCP-specific evidence")

# This is deliberately a pilot artifact: verification was performed against the
# official documentation listed per row. It is not presented as the 100-app run.
summary = {
    'sample_size': len(records),
    'verified_rows': sum(bool(r.get('verified')) for r in records),
    'verification_correct_rows': sum(r.get('verification_result') == 'correct_on_checked_fields' for r in records),
    'accuracy_on_checked_rows': round(sum(r.get('verification_result') == 'correct_on_checked_fields' for r in records) / len(records), 3),
    'note': 'Pilot verification only; do not extrapolate this percentage to the 100-app set.'
}
(out/'pilot_results.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
(out/'pilot_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
