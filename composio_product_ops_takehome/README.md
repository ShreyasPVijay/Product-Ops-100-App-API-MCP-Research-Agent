# Composio Product Ops Research Agent

Researches the 100 apps in `data/apps.csv` and writes evidence-backed results, a verification queue, pattern summaries, and the searchable HTML report. Search-provider failures are recorded; seeded official documentation URLs provide a fallback. Unsupported claims stay `Unknown`.

## Run

Requires Python 3.10+. From the project folder:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python src/agent.py
```

To rebuild the case-study page from the reviewed full results:

```bash
COMPOSIO_OUTPUT_DIR=output/evidence-v8-full python src/build_html_report.py
```

Open `site/index.html`. Research outputs and field-level source evidence are in `output/` (`results.json`, `results.txt`, `patterns.json`, and `verification_queue.json`). The browser verification sample and its correction log are in `output/evidence-v8-full/verification_review.json`.

## Main files

- `src/agent.py` — discovery, fetching, evidence extraction, checkpointing, and analysis.
- `src/reconcile_manual_review.py` — applies documented official-source review corrections.
- `src/build_html_report.py` — generates the self-contained report page.
- `data/apps.csv` — research set.
