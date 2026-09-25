# Composio Product Ops — 100-App API & MCP Research Agent.

Research Report : https://product-ops-research.netlify.app

An automated research pipeline built for the Product Ops

The system researches **100 SaaS, developer, commerce, communication, finance, and AI applications** and determines whether each app can realistically be integrated into an AI workflow.

For every application, the pipeline investigates:

- Authentication methods
- API access model
- Public REST / GraphQL / SOAP surface
- MCP availability
- Self-serve vs gated access
- Integration buildability
- Official documentation evidence

The key design principle is **evidence over inference**: when the available documentation does not provide sufficiently explicit evidence, the system returns `Unknown` instead of guessing.

---

## What This Project Does

The pipeline takes a list of 100 applications and automatically:

```text
100 Apps
   ↓
Official-domain discovery
   ↓
Documentation search
   ↓
Official page fetching
   ↓
Field-specific evidence extraction
   ↓
Evidence validation
   ↓
Buildability classification
   ↓
Verification queue
   ↓
Pattern analysis
```

The result is a structured research dataset that can be reviewed, verified, and used to identify integration patterns across the 100 applications.

---

## Research Fields

Each application is evaluated on the following fields:

| Field | What is measured |
|---|---|
| App | Application being researched |
| Category | Product category |
| Description | Short description of the application |
| Auth | Documented authentication methods |
| Access | Self-serve, gated, mixed, or unknown |
| API | REST, GraphQL, SOAP, or unknown |
| MCP | MCP availability when explicitly documented |
| Buildability | High, Conditional, or Unknown |
| Evidence | Supporting official documentation |


### MCP

MCP requires product-specific evidence.

The system does not classify an application as MCP-enabled simply because an unrelated page contains the term "MCP".

Evidence must explicitly connect MCP to the application.

If that evidence is unavailable:

```text
MCP: Unknown
```

### Access

The system distinguishes API/developer access from general sales or pricing language.

For example, a generic:

```text
Contact sales
```

does not automatically mean that API access is gated.

The system looks for evidence specifically related to API/developer access, credentials, approval, or application requirements.

### Unknown by Design

`Unknown` is an intentional result.

It means:

> The automated researcher could not find sufficiently strong evidence to make the classification safely.

This prevents the research dataset from becoming artificially confident.

---

## Buildability

Buildability is derived from the validated research fields.

### High

Generally requires:

- Documented authentication
- A validated API or MCP surface
- Self-serve access

### Conditional

Used when an integration surface exists but access is:

- Gated
- Mixed
- Not sufficiently verified as self-serve

### Unknown

Used when there is insufficient evidence to establish the integration path confidently.

The system therefore avoids treating every API mention as automatically "buildable."

---

## Automated Research

The project uses:

- Python
- DuckDuckGo search
- `requests`
- BeautifulSoup
- Official-domain filtering
- Deterministic evidence extraction
- JSON-based structured output

The primary research pipeline does **not require a paid LLM API**.

This was an intentional design choice so that the research process can run without depending on paid model credits.

---

## Verification Workflow

The research process is designed as:

```text
Automated First Pass
        ↓
Evidence Extraction
        ↓
Field-Level Validation
        ↓
Uncertain Results
        ↓
Verification Queue
        ↓
Human Review
        ↓
Final Research Dataset
```

The automated pass produces a verification queue containing applications whose fields require additional checking.

This allows human effort to be focused on uncertain cases rather than manually researching all 100 applications from scratch.

---

## Output Files

After running the pipeline, the `output/` directory contains:

### `results.json`

Detailed structured research results.

Contains:

- Application metadata
- Research fields
- Evidence source
- Evidence quote
- Validation rule
- Evidence type
- Research metadata

### `results.txt`

Human-readable matrix containing the required output format.

Example:

```text
id="app-001"
Salesforce
Category: CRM/Sales
Description: Customer relationship management and sales platform
Auth: OAuth 2.0
Access: Self-serve
API: Public REST API
MCP: Available
Buildability: High
Evidence: Official documentation
```

### `patterns.json`

Aggregated findings across the 100 applications, including distributions for:

- Authentication
- Access
- API type
- MCP
- Buildability
- Category-level patterns

### `verification_queue.json`

Applications and fields requiring additional human verification.

### `verification_summary.json`

Summary of the automated research process and verification workflow.

---

## Project Structure

```text
composio_product_ops_takehome/
│
├── data/
│   └── apps.csv
│
├── src/
│   └── agent.py
│
├── site/
│   └── index.html
│
├── output/
│   ├── results.json
│   ├── results.txt
│   ├── patterns.json
│   ├── verification_queue.json
│   └── verification_summary.json
│
├── .gitignore
├── .env.example
├── README.md
└── requirements.txt
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/composio-product-ops-takehome.git
cd composio-product-ops-takehome
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run the Research Agent

```bash
python src/agent.py
```

The application list is loaded from:

```text
data/apps.csv
```

Results are written to:

```text
output/
```

The agent also maintains a checkpoint so an interrupted research run can continue without unnecessarily repeating completed applications.

---

## Checkpointing

The pipeline stores progress in:

```text
output/checkpoint.json
```

The checkpoint includes the research ruleset version.

If the ruleset changes, old checkpoint results are not automatically reused.

This prevents results produced by an older evidence policy from silently contaminating a newer run.

---

## Design Decisions

### 1. Prefer Unknown over Guessing

A wrong positive classification can make an integration appear easier than it really is.

Therefore:

```text
Weak evidence → Unknown
```

rather than:

```text
Weak evidence → guessed answer
```

### 2. Official Sources First

The researcher filters discovered pages against known official domains for each application.

### 3. Field-Level Validation

Authentication, API, MCP, and access are evaluated independently.

A page proving API availability does not automatically prove:

- OAuth
- self-serve access
- MCP
- or buildability

### 4. Evidence Remains Attached to the Result

The detailed JSON output retains the source and evidence used for each classification.

### 5. Human Verification Is Explicit

Automation is used to reduce repetitive research work, not to hide uncertainty.

The verification queue identifies where human review is still useful.

---

## Scope

The research dataset covers 100 applications across:

1. CRM / Sales
2. Support / Helpdesk
3. Communication
4. Marketing / Ads / Email / Social
5. Ecommerce
6. Data / SEO / Scraping
7. Developer / Infrastructure / Data
8. Productivity / Project Management
9. Finance / Fintech
10. AI / Research / Media

The application list is maintained in:

```text
data/apps.csv
```

---
