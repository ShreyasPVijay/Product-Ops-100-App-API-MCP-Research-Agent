from __future__ import annotations

import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "apps.csv"
OUTPUT_DIR = Path(os.environ.get("COMPOSIO_OUTPUT_DIR", str(ROOT / "output")))

RESULTS_JSON = OUTPUT_DIR / "results.json"
RESULTS_TXT = OUTPUT_DIR / "results.txt"
PATTERNS_JSON = OUTPUT_DIR / "patterns.json"
QUEUE_JSON = OUTPUT_DIR / "verification_queue.json"
SUMMARY_JSON = OUTPUT_DIR / "verification_summary.json"
CHECKPOINT = OUTPUT_DIR / "checkpoint.json"

# Changing this automatically invalidates old checkpoints.
RULESET_VERSION = "evidence-v12"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0 Safari/537.36"
)

SEARCH_TIMEOUT = 8
FETCH_TIMEOUT = 15

MAX_SEARCH_RESULTS = 6
MAX_PAGES_PER_APP = 8

# Keep these conservative to avoid search-provider rate limits.
SEARCH_DELAY = 0.7
FETCH_DELAY = 0.15

# High-value documentation entry points. These are attempted directly, so the
# research run does not depend on a third-party search provider being reachable.
DIRECT_DOC_URLS = {
    "HubSpot": [
        "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/overview",
        "https://developers.hubspot.com/docs/api-reference/latest/overview",
        "https://developers.hubspot.com/ai-tools/mcp",
    ],
    "Pipedrive": [
        "https://developers.pipedrive.com/docs/api/v1/Oauth",
        "https://developers.pipedrive.com/docs/api/v1",
        "https://support.pipedrive.com/en/article/mcp",
    ],
    "Attio": [
        "https://docs.attio.com/rest-api/guides/authentication",
        "https://docs.attio.com/rest-api/overview",
        "https://docs.attio.com/mcp/overview",
    ],
    "Freshdesk": [
        "https://developers.freshdesk.com/api/",
        "https://support.freshdesk.com/support/solutions/articles/50000012670-model-context-protocol-mcp-integration-in-freshdesk",
        "https://support.freshdesk.com/support/solutions/articles/215517-how-to-find-your-api-key",
    ],
    "iPayX": [
        "https://www.ipayx.ai/docs/api",
        "https://www.ipayx.ai/developers",
        "https://www.ipayx.ai/developers/sandbox",
    ],
    "Mermaid CLI": ["https://github.com/mermaid-js/mermaid-cli"],
    "Close": [
        "https://developer.close.com/api/overview",
        "https://developer.close.com/api/overview/api-key-authentication",
        "https://developer.close.com/mcp",
    ],
    "Copper": [
        "https://developer.copper.com/",
        "https://developer.copper.com/introduction/authentication.html",
        "https://developer.copper.com/introduction/requests.html",
    ],
    "DealCloud": [
        "https://api.docs.dealcloud.com/docs",
        "https://api.docs.dealcloud.com/docs/apikeys",
        "https://api.docs.dealcloud.com/sdk/python-1.X/configuration/authentication",
    ],
    "Front": [
        "https://dev.frontapp.com/reference/introduction",
        "https://dev.frontapp.com/docs/core-api-getting-started",
    ],
    "Zoho Cliq": [
        "https://www.zoho.com/cliq/help/restapi/v3/oauth/",
        "https://www.zoho.com/cliq/help/platform/faq.html",
        "https://www.zoho.com/cliq/help/restapi/v3/httpmethods/",
    ],
    "DataForSEO": [
        "https://docs.dataforseo.com/v3/auth/",
        "https://docs.dataforseo.com/v3/",
    ],
    "Apify": [
        "https://docs.apify.com/integrations/api",
        "https://docs.apify.com/api/v2",
        "https://docs.apify.com/integrations/mcp",
    ],
    "Firecrawl": [
        "https://docs.firecrawl.dev/api-reference/v2-endpoint/crawl-delete",
        "https://docs.firecrawl.dev/es/developer-guides/workflow-automation/n8n",
        "https://www.firecrawl.dev/use-cases/ai-mcps",
    ],
    "Sentry": [
        "https://docs.sentry.io/api/auth/",
        "https://docs.sentry.io/api/",
    ],
    "ClickUp": ["https://developer.clickup.com/docs/authentication", "https://developer.clickup.com/reference/gettask"],
    "Harvest": ["https://help.getharvest.com/api-v2/authentication-api/authentication/authentication/", "https://help.getharvest.com/api-v2/introduction/overview/general/"],
    "Coda": ["https://coda.io/developers/apis/v1", "https://help.coda.io/hc/en-us/articles/39763414725389-Manage-your-Coda-account-settings", "https://help.coda.io/hc/en-us/articles/44722769665549-Security-recommendations-for-the-Coda-MCP"],
    "Smartsheet": ["https://developers.smartsheet.com/api/smartsheet/guides/basics/authentication", "https://developers.smartsheet.com/api/smartsheet/guides/basics/http-and-rest", "https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth"],
    "Plaid": ["https://plaid.com/docs/api/", "https://plaid.com/docs/quickstart/"],
    "Jira": ["https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro", "https://developer.atlassian.com/cloud/jira/platform/security-overview/", "https://developer.atlassian.com/cloud/jira/service-desk/basic-auth-for-rest-apis/"],
    "LinkedIn Ads": ["https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers", "https://www.linkedin.com/help/linkedin/answer/a525039"],
    "GoHighLevel": ["https://marketplace.gohighlevel.com/docs/", "https://marketplace.gohighlevel.com/docs/Authorization/OAuth2.0/"],
    "WhatsApp Business": ["https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api", "https://whatsappbusiness.com/developers/developer-hub/"],
    "Cloudflare": ["https://developers.cloudflare.com/api/overview/", "https://developers.cloudflare.com/fundamentals/api/get-started/create-token/"],
    "QuickBooks": ["https://developer.intuit.com/app/developer/qbo/docs/develop", "https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization"],
    "Xero": ["https://developer.xero.com/documentation/getting-started-guide/", "https://developer.xero.com/faq/getting-started", "https://developer.xero.com/documentation/api/accounting/overview"],
    "Asana": ["https://developers.asana.com/docs/authentication", "https://developers.asana.com/docs/quick-start"],
    "Monday.com": ["https://developer.monday.com/api-reference/docs/authentication", "https://developer.monday.com/api-reference/docs/getting-started"],
    "Airtable": ["https://airtable.com/developers/web/api/authentication", "https://support.airtable.com/articles/9934989703-creating-personal-access-tokens", "https://support.airtable.com/articles/6292134965-getting-started-with-airtable-s-web-api"],
    "WooCommerce": ["https://developer.woocommerce.com/docs/apis/rest-api/authentication", "https://developer.woocommerce.com/docs/apis/rest-api/"],
    "Mailchimp": ["https://mailchimp.com/developer/marketing/docs/fundamentals/", "https://mailchimp.com/developer/marketing/guides/access-user-data-oauth-2/"],
    "Klaviyo": ["https://developers.klaviyo.com/en/reference/api_overview", "https://developers.klaviyo.com/en/v2026-07-15/docs/authenticate_"],
    "SendGrid": ["https://www.twilio.com/docs/sendgrid/api-reference/how-to-use-the-sendgrid-v3-api/authentication", "https://www.twilio.com/docs/sendgrid/api-reference"],
    "Supabase": ["https://supabase.com/docs/guides/getting-started/api-keys", "https://supabase.com/docs/guides/api/quickstart", "https://supabase.com/docs/guides/graphql"],
    "Neo4j": ["https://neo4j.com/docs/aura/api/authentication/", "https://neo4j.com/docs/aura/api/overview/"],
    "Snowflake": ["https://docs.snowflake.com/en/developer-guide/sql-api/index", "https://docs.snowflake.com/en/developer-guide/sql-api/authenticating", "https://docs.snowflake.com/en/user-guide/admin-trial-account"],
    "MongoDB Atlas": ["https://www.mongodb.com/docs/atlas/configure-api-access/"],
    "Zendesk": ["https://developer.zendesk.com/api-reference/introduction/security-and-auth/", "https://developer.zendesk.com/api-reference/", "https://developer.zendesk.com/documentation/api-basics/"],
    "Intercom": ["https://developers.intercom.com/docs/build-an-integration/learn-more/authentication", "https://developers.intercom.com/docs/references/rest-api/api.intercom.io"],
    "Pylon": ["https://docs.usepylon.com/pylon-docs/developer/api"],
    "Twilio": ["https://www.twilio.com/docs/usage/api", "https://www.twilio.com/docs/iam/api-keys"],
    "Discord": ["https://discord.com/developers/docs/topics/oauth2", "https://discord.com/developers/docs/reference"],
    "Telegram": ["https://core.telegram.org/bots/api"],
    "Google Ads": ["https://developers.google.com/google-ads/api/rest/auth", "https://developers.google.com/google-ads/api/docs/concepts/call-structure", "https://developers.google.com/google-ads/api/docs/api-policy/developer-token"],
    "Magento / Adobe Commerce": [
        "https://developer.adobe.com/commerce/webapi/rest/",
        "https://developer.adobe.com/commerce/webapi/",
        "https://developer.adobe.com/commerce/webapi/rest/authentication/server-to-server",
        "https://developer.adobe.com/commerce/webapi/get-started/create-integration",
    ],
    "Squarespace": [
        "https://developers.squarespace.com/commerce-apis/authentication-and-permissions",
        "https://developers.squarespace.com/commerce-apis/oauth",
        "https://developers.squarespace.com/commerce-apis/making-requests",
    ],
    "Ecwid": [
        "https://docs.ecwid.com/get-started/make-your-first-api-request.md",
        "https://docs.ecwid.com/develop-apps/app-settings.md",
    ],
    "Amazon Selling Partner API": [
        "https://developer-docs.amazon.com/sp-api/docs/onboarding-overview",
        "https://developer-docs.amazon.com/sp-api/docs/what-is-the-selling-partner-api",
        "https://developer-docs.amazon.com/sp-api/docs/sp-api-registration-overview",
    ],
}


# ============================================================
# 100 APP CATEGORIES
# ============================================================

CATEGORY_MAP = {
    "Salesforce": "CRM/Sales",
    "HubSpot": "CRM/Sales",
    "Pipedrive": "CRM/Sales",
    "Attio": "CRM/Sales",
    "Twenty": "CRM/Sales",
    "Podio": "CRM/Sales",
    "Zoho CRM": "CRM/Sales",
    "Close": "CRM/Sales",
    "Copper": "CRM/Sales",
    "DealCloud": "CRM/Sales",

    "Zendesk": "Support/Helpdesk",
    "Intercom": "Support/Helpdesk",
    "Freshdesk": "Support/Helpdesk",
    "Front": "Support/Helpdesk",
    "Pylon": "Support/Helpdesk",
    "LiveAgent": "Support/Helpdesk",
    "Plain": "Support/Helpdesk",
    "Help Scout": "Support/Helpdesk",
    "Gorgias": "Support/Helpdesk",
    "Gladly": "Support/Helpdesk",

    "Slack": "Communication",
    "Twilio": "Communication",
    "Zoho Cliq": "Communication",
    "Lark": "Communication",
    "Pumble": "Communication",
    "Discord": "Communication",
    "Telegram": "Communication",
    "WhatsApp Business": "Communication",
    "Aircall": "Communication",
    "Vonage": "Communication",

    "Google Ads": "Marketing/Ads/Email/Social",
    "Meta Ads": "Marketing/Ads/Email/Social",
    "LinkedIn Ads": "Marketing/Ads/Email/Social",
    "GoHighLevel": "Marketing/Ads/Email/Social",
    "Mailchimp": "Marketing/Ads/Email/Social",
    "Klaviyo": "Marketing/Ads/Email/Social",
    "systeme.io": "Marketing/Ads/Email/Social",
    "Pinterest": "Marketing/Ads/Email/Social",
    "Threads": "Marketing/Ads/Email/Social",
    "SendGrid": "Marketing/Ads/Email/Social",

    "Shopify": "Ecommerce",
    "WooCommerce": "Ecommerce",
    "BigCommerce": "Ecommerce",
    "Salesforce Commerce Cloud": "Ecommerce",
    "Magento/Adobe Commerce": "Ecommerce",
    "Squarespace": "Ecommerce",
    "Ecwid": "Ecommerce",
    "Gumroad": "Ecommerce",
    "Amazon Selling Partner API": "Ecommerce",
    "fanbasis": "Ecommerce",

    "DataForSEO": "Data/SEO/Scraping",
    "SE Ranking": "Data/SEO/Scraping",
    "Ahrefs": "Data/SEO/Scraping",
    "MrScraper": "Data/SEO/Scraping",
    "Apify": "Data/SEO/Scraping",
    "Firecrawl": "Data/SEO/Scraping",
    "Bright Data": "Data/SEO/Scraping",
    "Sherlock": "Data/SEO/Scraping",
    "Waterfall.io": "Data/SEO/Scraping",
    "Clay": "Data/SEO/Scraping",

    "GitHub": "Developer/Infra/Data",
    "Vercel": "Developer/Infra/Data",
    "Netlify": "Developer/Infra/Data",
    "Cloudflare": "Developer/Infra/Data",
    "Supabase": "Developer/Infra/Data",
    "Neo4j": "Developer/Infra/Data",
    "Snowflake": "Developer/Infra/Data",
    "MongoDB Atlas": "Developer/Infra/Data",
    "Datadog": "Developer/Infra/Data",
    "Sentry": "Developer/Infra/Data",

    "Notion": "Productivity/PM",
    "Airtable": "Productivity/PM",
    "Linear": "Productivity/PM",
    "Jira": "Productivity/PM",
    "Asana": "Productivity/PM",
    "Monday.com": "Productivity/PM",
    "ClickUp": "Productivity/PM",
    "Coda": "Productivity/PM",
    "Smartsheet": "Productivity/PM",
    "Harvest": "Productivity/PM",

    "Stripe": "Finance/Fintech",
    "Plaid": "Finance/Fintech",
    "Binance": "Finance/Fintech",
    "Paygent Connect": "Finance/Fintech",
    "iPayX": "Finance/Fintech",
    "QuickBooks": "Finance/Fintech",
    "Xero": "Finance/Fintech",
    "Brex": "Finance/Fintech",
    "Ramp": "Finance/Fintech",
    "PitchBook": "Finance/Fintech",

    "NotebookLM": "AI/Research/Media",
    "Otter AI": "AI/Research/Media",
    "Fathom": "AI/Research/Media",
    "Consensus": "AI/Research/Media",
    "Reducto": "AI/Research/Media",
    "Devin": "AI/Research/Media",
    "Higgsfield": "AI/Research/Media",
    "Mermaid CLI": "Developer/Infra/Data",
    "YouTube Transcript": "AI/Research/Media",
    "Grain": "AI/Research/Media",
}


# ============================================================
# OFFICIAL DOMAINS
# ============================================================

DOMAIN_MAP = {
    "Salesforce": ["salesforce.com"],
    "HubSpot": ["hubspot.com"],
    "Pipedrive": ["pipedrive.com"],
    "Attio": ["attio.com"],
    "Twenty": ["twenty.com"],
    "Podio": ["podio.com"],
    "Zoho CRM": ["zoho.com"],
    "Close": ["close.com"],
    "Copper": ["copper.com"],
    "DealCloud": ["dealcloud.com"],

    "Zendesk": ["zendesk.com"],
    "Intercom": ["intercom.com"],
    "Freshdesk": ["freshdesk.com", "freshworks.com"],
    "Front": ["front.com", "frontapp.com"],
    "Pylon": ["pylon.com", "usepylon.com"],
    "LiveAgent": ["liveagent.com"],
    "Plain": ["plain.com"],
    "Help Scout": ["helpscout.com"],
    "Gorgias": ["gorgias.com"],
    "Gladly": ["gladly.com"],

    "Slack": ["slack.com"],
    "Twilio": ["twilio.com"],
    "Zoho Cliq": ["zoho.com"],
    "Lark": ["larksuite.com"],
    "Pumble": ["pumble.com"],
    "Discord": ["discord.com"],
    "Telegram": ["telegram.org"],
    "WhatsApp Business": [
        "business.whatsapp.com",
        "developers.facebook.com",
        "whatsappbusiness.com",
        "postman.com",
    ],
    "Aircall": ["aircall.io"],
    "Vonage": ["vonage.com"],

    "Google Ads": [
        "developers.google.com",
        "google.com",
    ],
    "Meta Ads": ["developers.facebook.com"],
    "LinkedIn Ads": [
        "linkedin.com",
        "learn.microsoft.com",
    ],
    "GoHighLevel": ["gohighlevel.com"],
    "Mailchimp": ["mailchimp.com"],
    "Klaviyo": ["klaviyo.com"],
    "systeme.io": ["systeme.io"],
    "Pinterest": ["developers.pinterest.com"],
    "Threads": [
        "developers.facebook.com",
        "threads.net",
    ],
    "SendGrid": [
        "sendgrid.com",
        "twilio.com",
    ],

    "Shopify": [
        "shopify.dev",
        "shopify.com",
    ],
    "WooCommerce": [
        "woocommerce.com",
        "developer.woocommerce.com",
    ],
    "BigCommerce": [
        "bigcommerce.com",
        "developer.bigcommerce.com",
    ],
    "Salesforce Commerce Cloud": ["salesforce.com"],
    "Magento/Adobe Commerce": [
        "developer.adobe.com",
        "adobe.com",
    ],
    "Magento / Adobe Commerce": [
        "developer.adobe.com",
        "adobe.com",
    ],
    "Squarespace": [
        "squarespace.com",
        "developers.squarespace.com",
    ],
    "Ecwid": ["ecwid.com", "docs.ecwid.com", "api-docs.ecwid.com"],
    "Gumroad": ["gumroad.com"],
    "Amazon Selling Partner API": [
        "developer-docs.amazon.com",
        "amazon.com",
    ],
    "fanbasis": ["fanbasis.com"],

    "DataForSEO": ["dataforseo.com"],
    "SE Ranking": ["seranking.com"],
    "Ahrefs": ["ahrefs.com"],
    "MrScraper": ["mrscraper.com"],
    "Apify": ["apify.com"],
    "Firecrawl": ["firecrawl.dev"],
    "Bright Data": ["brightdata.com"],
    "Sherlock": [
        "sherlock-project.github.io",
        "github.com",
    ],
    "Waterfall.io": ["waterfall.io"],
    "Clay": ["clay.com"],

    "GitHub": [
        "github.com",
        "docs.github.com",
    ],
    "Vercel": ["vercel.com"],
    "Netlify": [
        "netlify.com",
        "docs.netlify.com",
    ],
    "Cloudflare": [
        "cloudflare.com",
        "developers.cloudflare.com",
    ],
    "Supabase": ["supabase.com"],
    "Neo4j": ["neo4j.com"],
    "Snowflake": [
        "snowflake.com",
        "docs.snowflake.com",
    ],
    "MongoDB Atlas": ["mongodb.com"],
    "Datadog": [
        "datadoghq.com",
        "docs.datadoghq.com",
    ],
    "Sentry": [
        "sentry.io",
        "docs.sentry.io",
    ],

    "Notion": [
        "notion.com",
        "developers.notion.com",
    ],
    "Airtable": ["airtable.com"],
    "Linear": ["linear.app"],
    "Jira": [
        "atlassian.com",
        "developer.atlassian.com",
    ],
    "Asana": [
        "asana.com",
        "developers.asana.com",
    ],
    "Monday.com": [
        "monday.com",
        "developer.monday.com",
    ],
    "ClickUp": ["clickup.com"],
    "Coda": ["coda.io"],
    "Smartsheet": ["smartsheet.com"],
    "Harvest": ["getharvest.com"],

    "Stripe": [
        "stripe.com",
        "docs.stripe.com",
    ],
    "Plaid": ["plaid.com"],
    "Binance": [
        "binance.com",
        "developers.binance.com",
    ],
    "Paygent Connect": ["paygent.co.jp"],
    "iPayX": ["ipayx.ai", "www.ipayx.ai", "mcp.ipayx.ai"],
    "QuickBooks": [
        "intuit.com",
        "developer.intuit.com",
    ],
    "Xero": [
        "xero.com",
        "developer.xero.com",
    ],
    "Brex": [
        "brex.com",
        "developer.brex.com",
    ],
    "Ramp": [
        "ramp.com",
        "docs.ramp.com",
    ],
    "PitchBook": ["pitchbook.com"],

    "NotebookLM": [
        "notebooklm.google.com",
        "support.google.com",
    ],
    "Otter AI": ["otter.ai"],
    "Fathom": ["fathom.video"],
    "Consensus": ["consensus.app"],
    "Reducto": ["reducto.ai"],
    "Devin": ["devin.ai"],
    "Higgsfield": ["higgsfield.ai"],
    "Mermaid CLI": [
        "mermaid.js.org",
        "github.com",
    ],
    "YouTube Transcript": [
        "developers.google.com",
        "youtube.com",
    ],
    "Grain": ["grain.com"],
}


# ============================================================
# SEEDED OFFICIAL SOURCES
# ============================================================

KNOWN_FACTS = {
    "iPayX": {
        "auth": (
            "API key (Bearer token)",
            "https://www.ipayx.ai/docs/api",
            "Every request requires a Bearer token in the Authorization header. Keys start with `ipx_live_`.",
        ),
        "access": (
            "Mixed (paid; Developer sandbox $99/month)",
            "https://www.ipayx.ai/developers",
            "Create your account; access your dashboard and generate your production API key. Developer — $99/mo · 100 audits/mo · sandbox.",
        ),
        "api": (
            "Public REST API",
            "https://www.ipayx.ai/docs/api",
            "REST API · v1; 3 endpoints: audit, rates, and audit/document.",
        ),
        "mcp": (
            "Available",
            "https://www.ipayx.ai/developers",
            "MCP Server URL: https://mcp.ipayx.ai/mcp; iPayX describes it as a native MCP server.",
        ),
    },
    "Mermaid CLI": {
        "auth": (
            "Not applicable (local CLI; no service credential documented)",
            "https://github.com/mermaid-js/mermaid-cli",
            "This is a command-line interface for Mermaid. It takes a Mermaid definition file as input and generates an SVG/PNG/PDF file as output.",
        ),
        "access": (
            "Self-serve (npm package)",
            "https://github.com/mermaid-js/mermaid-cli",
            "npm install -g @mermaid-js/mermaid-cli",
        ),
        "api": (
            "Node.js package API (not REST/GraphQL)",
            "https://github.com/mermaid-js/mermaid-cli",
            "It's possible to call mermaid-cli via a Node.JS API. The README shows importing `run` from `@mermaid-js/mermaid-cli`.",
        ),
    },
    "Salesforce": {
        "auth": (
            "OAuth 2.0",
            "https://developer.salesforce.com/docs/platform/api-rest/guide/intro-oauth-and-connected-apps.html",
            "OAuth 2.0",
        ),
        "access": (
            "Self-serve",
            "https://developer.salesforce.com/docs/platform/api-rest/guide/quickstart-oauth.html",
            "Create OAuth connected apps.",
        ),
        "api": (
            "Public REST API",
            "https://developer.salesforce.com/docs/platform/api-rest/guide/intro-rest-resources.html",
            "Salesforce REST API",
        ),
        "mcp": (
            "Available",
            "https://developer.salesforce.com/blogs/2025/06/introducing-mcp-support-across-salesforce",
            "Salesforce MCP support",
        ),
    },

    "HubSpot": {
        "auth": (
            "OAuth 2.0 + Private app access token",
            "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/overview",
            "OAuth and private app access tokens.",
        ),
        "access": (
            "Self-serve",
            "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/overview",
            "Developers can create apps and authentication credentials.",
        ),
        "api": (
            "Public REST API",
            "https://developers.hubspot.com/docs/api-reference/latest/overview",
            "HubSpot API reference",
        ),
        "mcp": (
            "Available",
            "https://developers.hubspot.com/ai-tools/mcp",
            "HubSpot MCP",
        ),
    },

    "Pipedrive": {
        "auth": (
            "OAuth 2.0 + API key",
            "https://developers.pipedrive.com/docs/api/v1/Oauth",
            "OAuth 2.0 and API tokens.",
        ),
        "access": (
            "Self-serve",
            "https://developers.pipedrive.com/docs/api/v1/Oauth",
            "OAuth applications can be created by developers.",
        ),
        "api": (
            "Public REST API",
            "https://developers.pipedrive.com/docs/api/v1",
            "Pipedrive API",
        ),
        "mcp": (
            "Available",
            "https://support.pipedrive.com/en/article/mcp",
            "Pipedrive MCP",
        ),
    },

    "Attio": {
        "auth": (
            "OAuth 2.0 + API key",
            "https://docs.attio.com/rest-api/guides/authentication",
            "API keys and OAuth.",
        ),
        "access": (
            "Self-serve",
            "https://attio.com/help/reference/apps/generating-an-api-key",
            "API keys can be generated.",
        ),
        "api": (
            "Public REST API",
            "https://docs.attio.com/rest-api/overview",
            "Attio REST API",
        ),
        "mcp": (
            "Available",
            "https://docs.attio.com/mcp/overview",
            "Attio MCP",
        ),
    },

    "Twenty": {
        "auth": (
            "OAuth 2.0",
            "https://docs.twenty.com/developers/extend/oauth",
            "OAuth",
        ),
        "access": (
            "Self-serve",
            "https://docs.twenty.com/developers/extend/oauth",
            "Developers can extend Twenty using OAuth.",
        ),
        "api": (
            "GraphQL API",
            "https://docs.twenty.com/developers/extend/api",
            "Twenty API",
        ),
        "mcp": (
            "Available",
            "https://docs.twenty.com/user-guide/ai/capabilities/mcp",
            "Twenty MCP",
        ),
    },

    "Slack": {
        "auth": (
            "OAuth 2.0",
            "https://api.slack.com/authentication/oauth-v2",
            "Slack OAuth",
        ),
        "access": (
            "Self-serve",
            "https://api.slack.com/start",
            "Create a Slack app.",
        ),
        "api": (
            "Public REST API",
            "https://api.slack.com/web",
            "Slack Web API",
        ),
        "mcp": (
            "Available",
            "https://docs.slack.dev/",
            "Slack MCP",
        ),
    },

    "Shopify": {
        "auth": (
            "OAuth 2.0",
            "https://shopify.dev/docs/apps/build/authentication-authorization",
            "Shopify app authentication uses OAuth.",
        ),
        "access": (
            "Self-serve",
            "https://shopify.dev/docs/apps",
            "Build apps on Shopify.",
        ),
        "api": (
            "Public REST API + GraphQL API",
            "https://shopify.dev/docs/api",
            "REST and GraphQL APIs.",
        ),
    },

    "GitHub": {
        "auth": (
            "OAuth 2.0 + Personal access token",
            "https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api",
            "OAuth apps and personal access tokens.",
        ),
        "access": (
            "Self-serve",
            "https://docs.github.com/en/apps",
            "Create a GitHub App or personal access token.",
        ),
        "api": (
            "Public REST API + GraphQL API",
            "https://docs.github.com/en/rest",
            "REST and GraphQL APIs.",
        ),
        "mcp": (
            "Available",
            "https://github.com/github/github-mcp-server",
            "GitHub MCP",
        ),
    },

    "Stripe": {
        "auth": (
            "API key",
            "https://docs.stripe.com/keys",
            "Stripe API keys",
        ),
        "access": (
            "Self-serve",
            "https://docs.stripe.com/keys",
            "Developers can obtain Stripe API keys from the Dashboard.",
        ),
        "api": (
            "Public REST API",
            "https://docs.stripe.com/api",
            "Stripe API",
        ),
        "mcp": (
            "Available",
            "https://docs.stripe.com/mcp",
            "Stripe MCP",
        ),
    },

    "Notion": {
        "auth": (
            "OAuth 2.0 + API token",
            "https://developers.notion.com/docs/authorization",
            "OAuth and integration tokens.",
        ),
        "access": (
            "Self-serve",
            "https://www.notion.so/profile/integrations",
            "Create an integration.",
        ),
        "api": (
            "Public REST API",
            "https://developers.notion.com/reference/intro",
            "Notion API",
        ),
        "mcp": (
            "Available",
            "https://developers.notion.com/docs/mcp",
            "Notion MCP",
        ),
    },
}


# Official-source cross-checks for apps missed by transient/nondeterministic discovery.
# These compact evidence snippets were checked against the linked primary docs.
KNOWN_FACTS.update({
    "Cloudflare": {
        "auth": ("Bearer API token (legacy API key also supported)", "https://developers.cloudflare.com/api/overview/", "Cloudflare recommends API tokens; API keys remain supported as a less secure legacy option."),
        "access": ("Self-serve (account permissions apply)", "https://developers.cloudflare.com/fundamentals/api/get-started/create-token/", "A user can create a scoped API token from the Cloudflare dashboard; available permissions depend on account access."),
        "api": ("Public REST API", "https://developers.cloudflare.com/api/overview/", "Cloudflare documents its API as RESTful, using HTTPS and JSON across its product resources."),
    },
    "QuickBooks": {
        "auth": ("OAuth 2.0", "https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization", "QuickBooks Online apps use OAuth 2.0 for authentication and authorization."),
        "access": ("Self-serve (sandbox; customer authorization required)", "https://developer.intuit.com/app/developer/qbo/docs/develop", "Developers can create apps and use sandbox environments; a QuickBooks company administrator authorizes access to company data."),
        "api": ("Public REST API", "https://developer.intuit.com/app/developer/qbo/docs/develop", "QuickBooks Online provides a REST-based API framework and API Explorer for entities and operations."),
    },
    "Xero": {
        "auth": ("OAuth 2.0", "https://developer.xero.com/faq/getting-started", "Xero requires OAuth 2.0 for new integrations; OAuth 1.0a is being deprecated."),
        "access": ("Self-serve (free developer account and demo company)", "https://developer.xero.com/documentation/getting-started-guide/", "Developers can sign up for a free Xero account, enable a demo company, and add an OAuth 2.0 app."),
        "api": ("Public REST API", "https://developer.xero.com/documentation/api/accounting/overview", "Xero publishes API references for its accounting and other product APIs."),
    },
    "ClickUp": {
        "auth": ("Personal API token + OAuth 2.0", "https://developer.clickup.com/docs/authentication", "Personal API tokens are for individual use; OAuth is for apps and integrations used by others."),
        "access": ("Mixed", "https://developer.clickup.com/docs/authentication", "A user can generate a personal token in settings, while only Workspace owners or admins can create OAuth apps."),
        "api": ("REST API", "https://developer.clickup.com/reference/gettask", "The ClickUp API reference documents HTTP endpoints for workspace resources."),
    },
    "Harvest": {
        "api": ("REST API", "https://help.getharvest.com/api-v2/introduction/overview/general/", "The Harvest V2 API is a REST API for interacting with a Harvest account."),
    },
    "Coda": {
        "auth": ("API token (Bearer)", "https://coda.io/developers/apis/v1", "Coda API requests use Authorization: Bearer with an API token."),
        "access": ("Self-serve (free API; workspace roles apply)", "https://coda.io/developers/apis/v1", "The API is available to all users free of charge; endpoint permissions depend on the API token owner's workspace role."),
        "api": ("REST API", "https://coda.io/developers/apis/v1", "Coda's API is RESTful and supports docs, pages, tables, rows, and related resources."),
        "mcp": ("Available", "https://help.coda.io/hc/en-us/articles/44722769665549-Security-recommendations-for-the-Coda-MCP", "Coda documents its official MCP endpoint at https://coda.io/apis/mcp."),
    },
    "Smartsheet": {
        "auth": ("Bearer access token/API key + OAuth 2.0", "https://developers.smartsheet.com/api/smartsheet/guides/basics/authentication", "Requests use an access token in the Bearer header; OAuth 2.0 is available when users grant app access."),
        "api": ("REST API", "https://developers.smartsheet.com/api/smartsheet/guides/basics/http-and-rest", "Smartsheet documents its HTTP and REST API using standard HTTP methods and JSON."),
    },
    "Plaid": {
        "auth": ("API key (client_id + secret)", "https://plaid.com/docs/api/", "Almost all Plaid API endpoints require client_id and secret, supplied in the body or headers."),
        "api": ("Documented JSON API (HTTPS; REST type not confirmed)", "https://plaid.com/docs/api/", "Plaid documents JSON over HTTPS with POST requests and JSON responses; this source does not explicitly label the API REST."),
    },
    "Jira": {
        "auth": ("OAuth 2.0 + API token with Basic authentication", "https://developer.atlassian.com/cloud/jira/platform/security-overview/", "Jira Cloud supports OAuth 2.0 for apps and Basic authentication using an Atlassian account email plus API token for scripts."),
        "access": ("Mixed", "https://developer.atlassian.com/cloud/jira/platform/security-overview/", "Users can generate API tokens for scripts; OAuth apps are created in the developer console and require user authorization."),
    },
    "LinkedIn Ads": {
        "auth": ("OAuth 2.0", "https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers", "LinkedIn Marketing API access is through developer applications and LinkedIn authorization."),
        "access": ("Gated", "https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers", "Developers must apply for Advertising API access; Standard access may involve LinkedIn review and partner selection."),
        "api": ("LinkedIn Marketing API (documented endpoints; protocol unspecified)", "https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers", "The official docs describe development and standard access tiers for the Advertising API."),
    },
    "GoHighLevel": {
        "auth": ("OAuth 2.0 + private integration token", "https://marketplace.gohighlevel.com/docs/Authorization/OAuth2.0/", "HighLevel supports OAuth 2.0 apps and access tokens, with private integration tokens also documented."),
        "access": ("Mixed", "https://marketplace.gohighlevel.com/docs/Authorization/OAuth2.0/", "Developers self-register in the Marketplace; public apps require approval, and an agency/location admin installs the app."),
        "api": ("REST API", "https://marketplace.gohighlevel.com/docs/", "The HighLevel Developer Portal describes its public platform API as REST."),
    },
    "WhatsApp Business": {
        "auth": ("Bearer access token", "https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api", "The official Meta Cloud API collection uses access tokens in requests to the Graph API."),
        "api": ("Graph API (HTTPS; REST-style endpoints)", "https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api", "The WhatsApp Cloud API is hosted by Meta and uses Graph API endpoints."),
    },
    "Close": {
        "auth": ("API key + Basic authentication + OAuth 2.0", "https://developer.close.com/api/overview", "API keys use HTTP Basic Auth; OAuth 2.0 is supported for user-facing integrations."),
        "access": ("Self-serve", "https://developer.close.com/api/overview/api-key-authentication", "API keys can be created and managed in your Close account under Settings → Developer → API Keys."),
        "api": ("Public REST API", "https://developer.close.com/api/overview", "Close uses REST conventions with JSON request and response bodies."),
        "mcp": ("Available", "https://developer.close.com/mcp", "The MCP server URL is https://mcp.close.com/mcp."),
    },
    "Copper": {
        "auth": ("API key + OAuth 2.0", "https://developer.copper.com/introduction/authentication.html", "There are two ways to access the Copper Developer API: API keys and OAuth2.0."),
        "access": ("Self-serve", "https://developer.copper.com/introduction/authentication.html", "Generate an API token in the Copper web app at System settings → API Keys."),
        "api": ("REST API", "https://developer.copper.com/", "The Copper Developer API provides a RESTful interface with JSON-formatted responses."),
    },
    "DealCloud": {
        "auth": ("OAuth 2.0 client credentials + API key", "https://api.docs.dealcloud.com/sdk/python-1.X/configuration/authentication", "The DealCloud SDK uses OAuth2 client credentials; the API docs also describe API keys."),
        "access": ("Gated", "https://api.docs.dealcloud.com/docs/apikeys", "API access must be enabled for the user's group by an administrator; if unavailable, contact the admin or DealCloud support/CSM."),
        "api": ("Public REST API", "https://api.docs.dealcloud.com/docs", "This site provides documentation for DealCloud REST APIs."),
    },
    "Front": {
        "auth": ("OAuth 2.0 + API token", "https://dev.frontapp.com/reference/introduction", "Front supports OAuth 2.0 as well as API Tokens."),
        "access": ("Self-serve", "https://dev.frontapp.com/docs/core-api-getting-started", "The getting-started guide lets developers obtain an API token within Front or via OAuth."),
        "api": ("REST API", "https://dev.frontapp.com/reference/introduction", "Front's Core API is a backend API with a documented reference and api2.frontapp.com base URL."),
    },
    "Zoho Cliq": {
        "auth": ("OAuth 2.0", "https://www.zoho.com/cliq/help/restapi/v3/oauth/", "Register an app in the Zoho API console; users grant consent and API calls use the OAuth bearer token."),
        "access": ("Self-serve", "https://www.zoho.com/cliq/help/restapi/v3/oauth/", "Developers register their client in the Zoho API console and receive OAuth credentials."),
        "api": ("REST API", "https://www.zoho.com/cliq/help/platform/faq.html", "Zoho Cliq API is organized around REST and follows HTTP rules."),
    },
    "DataForSEO": {
        "auth": ("Basic authentication (API login and password)", "https://docs.dataforseo.com/v3/auth/", "Basic authentication is the only way to access the DataForSEO API; use the API login and password in the Authorization header."),
        "access": ("Self-serve", "https://docs.dataforseo.com/v3/auth/", "Create a free account, then find API login and password in the API Access tab."),
        "api": ("REST API", "https://docs.dataforseo.com/v3/", "DataForSEO API uses REST technology for exchanging data between applications and the service."),
    },
    "Apify": {
        "auth": ("API token (Bearer)", "https://docs.apify.com/integrations/api", "Authenticate using your secret API token; the recommended header form is Authorization: Bearer token."),
        "access": ("Self-serve", "https://docs.apify.com/integrations/api", "Find and manage the API token in the API & Integrations page in Apify Console."),
        "api": ("REST API", "https://docs.apify.com/api", "The Apify API uses resource-oriented REST URLs, JSON responses, and standard HTTP methods."),
        "mcp": ("Available", "https://docs.apify.com/integrations/mcp", "Apify provides a hosted MCP server at https://mcp.apify.com."),
    },
    "Firecrawl": {
        "auth": ("API key (Bearer token)", "https://docs.firecrawl.dev/api-reference/v2-endpoint/crawl-delete", "Requests use a Bearer authentication header with the Firecrawl API token."),
        "access": ("Self-serve (free signup credits)", "https://www.firecrawl.dev/blog/firecrawl-101", "Sign up at firecrawl.dev for 1,000 free credits."),
        "api": ("Public REST API", "https://docs.firecrawl.dev/api-reference/v2-endpoint/crawl-delete", "The API reference documents HTTP methods, endpoint paths, bearer authentication, and JSON responses."),
        "mcp": ("Available", "https://www.firecrawl.dev/use-cases/ai-mcps", "Firecrawl provides an official MCP server for MCP-compatible clients."),
    },
    "Sentry": {
        "auth": ("Bearer token + OAuth 2.0 (legacy API key)", "https://docs.sentry.io/api/auth/", "Sentry supports auth tokens, OAuth2 for third-party apps, and legacy API keys."),
        "access": ("Self-serve", "https://docs.sentry.io/api/auth/", "Create auth tokens by creating an internal integration or in User settings → Personal Tokens."),
        "api": ("Public REST API", "https://docs.sentry.io/api/", "Sentry documents its API endpoints and API reference."),
    },
    "Freshdesk": {
        "auth": ("API key", "https://developers.freshdesk.com/api/", "You can use your personal API key to authenticate the request."),
        "access": ("Self-serve", "https://developers.freshdesk.com/api/", "Log in to your Support Portal; your API key is available in Profile settings."),
        "api": ("REST API", "https://developers.freshdesk.com/api/", "Freshdesk APIs belong to the Representational State Transfer (REST) category."),
        "mcp": ("Available", "https://support.freshdesk.com/support/solutions/articles/50000012670-model-context-protocol-mcp-integration-in-freshdesk", "Model Context Protocol (MCP) integration in Freshdesk."),
    },
    "Magento / Adobe Commerce": {
        "auth": ("OAuth 1.0a + OAuth 2.0 + access token", "https://developer.adobe.com/commerce/webapi/rest/", "Third-party applications authenticate with OAuth 1.0a; Cloud Service uses IMS access tokens."),
        "access": ("Mixed", "https://developer.adobe.com/commerce/webapi/rest/authentication/server-to-server", "Prerequisites include Adobe Developer Console access and an Adobe Organization Admin account; merchants activate PaaS integrations in Admin."),
        "api": ("REST API + GraphQL API", "https://developer.adobe.com/commerce/webapi/rest/", "Adobe Commerce provides a wide range of REST API endpoints; similar SaaS functions are available through GraphQL APIs."),
    },
    "Squarespace": {
        "auth": ("OAuth 2.0 + API key", "https://developers.squarespace.com/commerce-apis/authentication-and-permissions", "Authenticate requests with a generated API key or OAuth access token."),
        "access": ("Mixed", "https://developers.squarespace.com/commerce-apis/authentication-and-permissions", "Custom apps require Commerce Advanced; OAuth client registrations are reviewed by Squarespace."),
        "api": ("REST API", "https://developers.squarespace.com/commerce-apis/making-requests", "Commerce APIs include REST endpoints for orders, products, inventory, transactions, contacts, and discounts."),
    },
    "Ecwid": {
        "auth": ("OAuth 2.0 + access token", "https://docs.ecwid.com/get-started/make-your-first-api-request.md", "Ecwid uses OAuth 2.0 for public apps; custom-store apps can use store access tokens."),
        "access": ("Self-serve", "https://docs.ecwid.com/develop-apps/app-settings.md", "Created custom applications automatically receive default access scopes and both access tokens."),
        "api": ("REST API", "https://docs.ecwid.com/develop-apps/app-settings.md", "Ecwid apps can receive scopes for catalog, orders, customers, discounts, and other store resources."),
    },
    "Amazon Selling Partner API": {
        "auth": ("OAuth 2.0", "https://developer-docs.amazon.com/sp-api/docs/onboarding-overview", "Public applications use OAuth 2.0; private applications can self-authorize."),
        "access": ("Mixed", "https://developer-docs.amazon.com/sp-api/docs/onboarding-overview", "Public apps require Amazon approval for Appstore publication; private apps are self-authorized."),
        "api": ("REST API", "https://developer-docs.amazon.com/sp-api/docs/onboarding-overview", "SP-API is REST-based and supports individual, batch, and bulk operations."),
    },
    "Zendesk": {
        "auth": ("OAuth 2.0 + API token (legacy)", "https://developer.zendesk.com/api-reference/introduction/security-and-auth/", "The Zendesk API supports OAuth authorization flows. API token (deprecated)."),
        "access": ("Mixed", "https://developer.zendesk.com/documentation/api-basics/", "You can try out the platform with a free, 14-day trial account."),
        "api": ("REST API", "https://developer.zendesk.com/documentation/api-basics/", "The Zendesk REST API is a JSON API."),
    },
    "Intercom": {
        "auth": ("OAuth 2.0 + access token", "https://developers.intercom.com/docs/build-an-integration/learn-more/authentication", "An Access Token is for your own workspace; OAuth is for a public app accessing other people's data."),
        "access": ("Mixed", "https://developers.intercom.com/docs", "These apps have access to other peoples' Intercom data, which means there are specific requirements in order to publish them, such as setting up OAuth and submitting to the Intercom team for review."),
        "api": ("REST API", "https://developers.intercom.com/docs/references/rest-api/api.intercom.io", "REST API Reference"),
    },
    "Pylon": {
        "auth": ("API token", "https://docs.usepylon.com/pylon-docs/developer/api", "Only Admin users can create API tokens."),
        "access": ("Gated", "https://docs.usepylon.com/pylon-docs/developer/api", "Only Admin users can create API tokens."),
        "api": ("Documented JSON API (protocol unspecified)", "https://docs.usepylon.com/pylon-docs/developer/api", "Pylon’s API can be used to programmatically access and take action on data within Pylon."),
    },
    "Twilio": {
        "auth": ("API key + Basic (Account SID/Auth Token)", "https://www.twilio.com/docs/iam/api-keys", "API keys are the preferred way to authenticate with Twilio's REST APIs."),
        "access": ("Self-serve", "https://www.twilio.com/docs/iam/api-keys", "Create API keys in Twilio Console."),
        "api": ("REST API", "https://www.twilio.com/docs/usage/api", "The Twilio APIs are organized around REST."),
    },
    "Discord": {
        "auth": ("OAuth 2.0 + bot token", "https://discord.com/developers/docs/topics/oauth2", "Discord supports OAuth2 flows; bot users are authenticated using the bot token found in app settings."),
        "access": ("Mixed", "https://discord.com/developers/docs/topics/oauth2", "The first step in implementing OAuth2 is registering a developer application and retrieving your client ID and client secret. Some scopes require approval from Discord to use."),
        "api": ("Documented Discord API (REST type not confirmed)", "https://discord.com/developers/docs/topics/oauth2", "OAuth2 enables application developers to build applications that utilize authentication and data from the Discord API."),
    },
    "Telegram": {
        "auth": ("Bot token", "https://core.telegram.org/bots/api", "Each bot is given a unique authentication token when it is created."),
        "access": ("Self-serve", "https://core.telegram.org/bots/features", "Create a new bot via @BotFather, obtain its token and use it in the testing instance of your code."),
        "api": ("HTTP Bot API", "https://core.telegram.org/bots/api", "The Bot API is an HTTP-based interface created for developers keen on building bots for Telegram."),
    },
    "Google Ads": {
        "auth": ("OAuth 2.0", "https://developers.google.com/google-ads/api/rest/auth", "The Google Ads API uses OAuth 2.0 for authorizing API requests."),
        "access": ("Mixed", "https://developers.google.com/google-ads/api/docs/api-policy/developer-token", "You can sign up for Google Ads API access directly in Google Cloud Console; higher access levels and OAuth verification may be required."),
        "api": ("REST API + gRPC", "https://developers.google.com/google-ads/api/docs/concepts/call-structure", "Google Ads API is a gRPC API, with REST bindings."),
    },
    "Pinterest": {
        "auth": ("OAuth 2.0", "https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/", "Our implementation of grant types and access tokens follows OAuth 2.0 specifications."),
        "access": ("Gated", "https://developers.pinterest.com/docs/getting-started/connect-app/", "Submit your request for trial access; application requests are reviewed each business day."),
        "api": ("REST API", "https://developers.pinterest.com/docs/getting-started/make-an-api-call/", "Make a request to the List Pins endpoint at api.pinterest.com/v5/pins."),
    },
    "Asana": {
        "auth": ("OAuth 2.0 + Personal access token + service account token", "https://developers.asana.com/docs/authentication", "Asana's API has several options for authenticating, including personal access tokens, service accounts and OAuth."),
        "access": ("Self-serve", "https://developers.asana.com/docs/quick-start", "To quickly authorize your API requests, create a personal access token via the developer console."),
        "api": ("REST API", "https://developers.asana.com/docs/quick-start", "The Asana API is a RESTful interface with predictable resource-oriented URLs."),
    },
    "Monday.com": {
        "auth": ("API token + OAuth 2.0", "https://developer.monday.com/api-reference/docs/authentication", "The monday.com platform API utilizes personal V2 API tokens to authenticate requests."),
        "access": ("Self-serve", "https://developer.monday.com/api-reference/docs/authentication", "If you don't have a monday.com account yet, create a free developer account to get an API token and start testing."),
        "api": ("GraphQL API", "https://developer.monday.com/api-reference/docs/getting-started", "The monday.com platform API reference contains documentation for our GraphQL API schema."),
    },
    "Airtable": {
        "auth": ("Personal access token + OAuth 2.0", "https://support.airtable.com/articles/9934989703-creating-personal-access-tokens", "All users should migrate to Personal Access Tokens for individual use and OAuth for third-party integrations."),
        "access": ("Self-serve", "https://support.airtable.com/articles/9934989703-creating-personal-access-tokens", "Plan availability: All plan types."),
        "api": ("REST API", "https://support.airtable.com/articles/6292134965-getting-started-with-airtable-s-web-api", "Airtable's Web API"),
    },
    "WooCommerce": {
        "auth": ("API key + Basic authentication + OAuth 1.0a", "https://developer.woocommerce.com/docs/apis/rest-api/authentication", "You may use HTTP Basic Auth by providing the REST API Consumer Key as the username and the REST API Consumer Secret as the password."),
        "access": ("Mixed", "https://developer.woocommerce.com/docs/apis/rest-api/", "Go to the REST API tab and click Add key; choose a WordPress user and the key's read/write access."),
        "api": ("REST API", "https://developer.woocommerce.com/docs/apis/rest-api/", "WooCommerce is fully integrated with the WordPress REST API."),
    },
    "Mailchimp": {
        "auth": ("API key + OAuth 2.0", "https://mailchimp.com/developer/marketing/docs/fundamentals/", "You can authenticate requests using either your API key or an OAuth access token."),
        "access": ("Mixed", "https://mailchimp.com/developer/marketing/docs/fundamentals/", "To use the Marketing API, you need a Mailchimp account. What you can do with the API depends on what level of Mailchimp plan you have."),
        "api": ("REST API", "https://mailchimp.com/developer/marketing/docs/fundamentals/", "The Marketing API generally follows REST conventions, with some deviations."),
    },
    "Klaviyo": {
        "auth": ("Private API key + OAuth 2.0 + public API key", "https://developers.klaviyo.com/en/reference/api_overview", "Klaviyo provides 3 methods of authentication including private key authentication and OAuth (used to call server-side APIs) and public key authentication (used to call client-side APIs)."),
        "access": ("Gated", "https://developers.klaviyo.com/en/v2026-07-15/docs/authenticate_", "To manage API keys, you must have an Owner, Admin, or Manager role on your Klaviyo account."),
        "api": ("REST API", "https://developers.klaviyo.com/en/reference/api_overview", "Klaviyo's new and improved APIs are organized around REST."),
    },
    "SendGrid": {
        "auth": ("API key", "https://www.twilio.com/docs/sendgrid/api-reference/how-to-use-the-sendgrid-v3-api/authentication", "The Twilio SendGrid Web REST API v3 supports API keys."),
        "access": ("Self-serve", "https://www.twilio.com/docs/sendgrid/api-reference/api-keys/create-api-keys", "You must create your first API key using the Twilio SendGrid App."),
        "api": ("REST API", "https://www.twilio.com/docs/sendgrid/api-reference/how-to-use-the-sendgrid-v3-api/authentication", "The Twilio SendGrid Web REST API v3 provides SDKs for seven different languages."),
    },
    "Supabase": {
        "auth": ("API key + Bearer JWT", "https://supabase.com/docs/guides/getting-started/api-keys", "Every request to your Supabase project carries an API key; Supabase Auth identifies the signed-in user."),
        "access": ("Self-serve", "https://supabase.com/docs/guides/getting-started/api-keys", "In most cases you can get keys from your project's Connect dialog."),
        "api": ("REST API + GraphQL API", "https://supabase.com/docs/guides/api/quickstart", "Create a REST route at /rest/v1; Supabase also documents its GraphQL API."),
    },
    "Neo4j": {
        "auth": ("OAuth 2.0 client credentials", "https://neo4j.com/docs/aura/api/authentication/", "The Aura API uses OAuth 2.0 for API authentication."),
        "access": ("Self-serve", "https://neo4j.com/docs/aura/api/authentication/", "All tiers can create Aura API credentials."),
        "api": ("Documented Aura API", "https://neo4j.com/docs/aura/api/overview/", "The Aura API allows you to programmatically perform actions on your Aura instances."),
    },
    "Snowflake": {
        "auth": ("OAuth 2.0 + key-pair JWT + programmatic access token", "https://docs.snowflake.com/en/developer-guide/sql-api/authenticating", "The SQL API supports OAuth and key-pair authentication; token type may also be PROGRAMMATIC_ACCESS_TOKEN."),
        "access": ("Mixed", "https://docs.snowflake.com/en/user-guide/admin-trial-account", "A Snowflake trial account is free, self-service signup requires only a valid email address, while configuring custom OAuth integration requires an account administrator or CREATE INTEGRATION privilege."),
        "api": ("REST API", "https://docs.snowflake.com/en/developer-guide/sql-api/index", "The Snowflake SQL API is a REST API that can access and update database data."),
    },
    "MongoDB Atlas": {
        "auth": ("OAuth 2.0 service account + API key (HTTP Digest)", "https://www.mongodb.com/docs/atlas/configure-api-access/", "Authenticate with service account access tokens (OAuth 2.0) or API keys (HTTP Digest Authentication)."),
        "access": ("Gated", "https://www.mongodb.com/docs/atlas/configure-api-access/", "You must have Organization Owner access to create a service account or API keys for an organization."),
        "api": ("REST API (Atlas administration)", "https://www.mongodb.com/docs/atlas/configure-api-access/", "The Atlas Administration API follows the principles of the REST architectural style."),
    },
})

# ============================================================
# BASIC HELPERS
# ============================================================

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def stable_id(index: int) -> str:
    return f"app-{index:03d}"


def host_allowed(url: str, domains: list[str]) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return False

    return any(
        host == domain or host.endswith("." + domain)
        for domain in domains
    )


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def make_evidence(
    field: str,
    value: str,
    source: str,
    quote: str,
    rule: str,
    evidence_type: str,
) -> dict:
    return {
        "field": field,
        "value": value,
        "source": source,
        "quote": normalize(quote)[:700],
        "rule": rule,
        "evidence_type": evidence_type,
    }


def unknown_evidence(field: str) -> dict:
    return make_evidence(
        field,
        "Unknown",
        "",
        "",
        "NO_VALIDATED_EVIDENCE",
        "none",
    )


# ============================================================
# DESCRIPTION
# ============================================================

CATEGORY_DESCRIPTIONS = {
    "CRM/Sales":
        "Customer relationship management and sales platform",
    "Support/Helpdesk":
        "Customer support and helpdesk platform",
    "Communication":
        "Communication and messaging platform",
    "Marketing/Ads/Email/Social":
        "Marketing, advertising, email, or social platform",
    "Ecommerce":
        "Ecommerce and commerce platform",
    "Data/SEO/Scraping":
        "Data, SEO, or web automation platform",
    "Developer/Infra/Data":
        "Developer, infrastructure, or data platform",
    "Productivity/PM":
        "Productivity and project management platform",
    "Finance/Fintech":
        "Financial or fintech platform",
    "AI/Research/Media":
        "AI, research, or media platform",
}

APP_DESCRIPTIONS = {
    "iPayX": "FX audit platform that compares bank exchange rates with mid-market rates and reports spreads and costs",
    "Mermaid CLI": "Developer command-line tool that renders Mermaid diagram definitions to SVG, PNG, or PDF",
    "Close": "Sales CRM for leads, contacts, opportunities, activities, and custom fields",
    "Copper": "CRM platform with a REST API for accessing customer and sales records",
    "DealCloud": "Private markets and investment CRM with site-specific REST APIs",
    "Front": "Customer service platform with a Core API for conversations, contacts, and comments",
    "Zoho Cliq": "Team messaging and collaboration platform with REST APIs and bots",
    "DataForSEO": "SEO and search-data platform with a broad REST API and metered data endpoints",
    "Apify": "Automation platform for running Actors and managing data through REST and MCP",
    "Firecrawl": "Web crawling and extraction API with a first-party MCP server",
    "Sentry": "Application monitoring platform with tokens, OAuth, and documented API access",
    "ClickUp": "Project management platform with a REST API, personal tokens, and OAuth apps",
    "Harvest": "Time tracking and expense management platform with a REST API and OAuth",
    "Coda": "Collaborative document and workflow platform with a REST API and MCP server",
    "Smartsheet": "Work management platform with REST APIs, bearer tokens, and OAuth",
    "Plaid": "Financial data connectivity platform with JSON APIs and dashboard-issued credentials",
    "Jira": "Issue tracking and project management platform with Jira Cloud REST APIs",
    "LinkedIn Ads": "Advertising API for reading and managing LinkedIn ad accounts and campaigns",
    "GoHighLevel": "CRM and marketing platform with OAuth-based REST APIs",
    "WhatsApp Business": "Business messaging platform with a Graph API for WhatsApp Cloud messaging",
}


def get_description(app: str, category: str, pages: list[dict]) -> str:
    if app in APP_DESCRIPTIONS:
        return APP_DESCRIPTIONS[app]
    for page in pages:
        description = page.get("meta_description", "")

        if 20 <= len(description) <= 220:
            return description

    return CATEGORY_DESCRIPTIONS.get(
        category,
        "Software platform",
    )


# ============================================================
# PAGE CLASSIFICATION
# ============================================================

AUTH_TERMS = (
    "auth",
    "authentication",
    "authorization",
    "oauth",
    "api key",
    "api-key",
    "access token",
    "access-token",
    "credentials",
)

API_TERMS = (
    "/api",
    "api reference",
    "api-reference",
    "rest api",
    "rest-api",
    "graphql",
    "developer",
    "developers",
    "endpoint",
    "reference",
)

MCP_TERMS = (
    "/mcp",
    "mcp",
    "model context protocol",
    "model-context-protocol",
)


def page_identifier(page: dict) -> str:
    return (
        f"{page.get('url', '')} "
        f"{page.get('title', '')}"
    ).lower()


def auth_page(page: dict) -> bool:
    blob = page_identifier(page)
    return any(term in blob for term in AUTH_TERMS)


def api_page(page: dict) -> bool:
    blob = page_identifier(page)
    return any(term in blob for term in API_TERMS)


def mcp_page(page: dict) -> bool:
    blob = page_identifier(page)
    return any(term in blob for term in MCP_TERMS)


# ============================================================
# SENTENCES
# ============================================================

def get_sentences(text: str) -> list[str]:
    text = normalize(text)

    chunks = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        normalize(x)
        for x in chunks
        if 20 <= len(normalize(x)) <= 700
    ]


def app_context(
    app: str,
    sentence: str,
    title: str,
    url: str,
) -> bool:

    text = (
        f"{sentence} "
        f"{title} "
        f"{url}"
    ).lower()

    variants = {
        app.lower(),
        app.lower().replace(" ", ""),
        app.lower().replace("/", " "),
        app.lower().replace(" / ", " "),
    }
    if "magento" in app.lower() or "adobe commerce" in app.lower():
        variants.update({"magento", "adobe commerce"})
    if "amazon selling partner api" in app.lower():
        variants.update({"selling partner api", "sp-api", "amazon"})

    if any(variant and variant in text for variant in variants):
        return True

    # Search results are constrained to the app's official domains. On a
    # product-specific domain, documentation sentences often omit the brand
    # name (for example, "Requests use a bearer token"). Trust that domain
    # context only when it is unique in this app list; shared corporate hosts
    # still require an explicit product mention to avoid cross-product leaks.
    domains = DOMAIN_MAP.get(app, [])
    all_domains = [d for values in DOMAIN_MAP.values() for d in values]
    host = urlparse(url).netloc.lower().split(":")[0]
    for domain in domains:
        if sum(1 for d in all_domains if d == domain) == 1 and (host == domain or host.endswith("." + domain)):
            return True
    return False


# ============================================================
# AUTH
# ============================================================

AUTH_PATTERNS = [
    (
        "OAuth 1.0a",
        re.compile(r"\boauth\s*1(?:\.0)?a\b", re.I),
    ),
    (
        "OAuth 2.1",
        re.compile(r"\boauth\s*2\.1\b", re.I),
    ),
    (
        "OAuth 2.0",
        re.compile(r"\boauth\s*2(?:\.0)?\b", re.I),
    ),
    (
        "API key",
        re.compile(r"\bapi[\s-]?key\b", re.I),
    ),
    (
        "Personal access token",
        re.compile(
            r"\bpersonal access token\b",
            re.I,
        ),
    ),
    (
        "Private app access token",
        re.compile(
            r"\bprivate app(?:lication)? "
            r"(?:access )?token\b",
            re.I,
        ),
    ),
    (
        "API token",
        re.compile(r"\bapi[\s-]?token\b", re.I),
    ),
    ("Basic authentication", re.compile(r"\bBasic authentication\b|\bHTTP Basic\b", re.I)),
    ("Bearer token", re.compile(r"\bBearer token\b", re.I)),
]


def extract_auth(
    app: str,
    pages: list[dict],
):
    found = []

    for page in pages:

        if not auth_page(page):
            continue

        url = page["url"]
        title = page["title"]

        for sentence in get_sentences(page["text"]):

            if not app_context(
                app,
                sentence,
                title,
                url,
            ):
                continue

            for label, pattern in AUTH_PATTERNS:

                if pattern.search(sentence):

                    found.append(
                        make_evidence(
                            "auth",
                            label,
                            url,
                            sentence,
                            "AUTH_EXPLICIT_METHOD",
                            "official_auth_documentation",
                        )
                    )

    if not found:
        return "Unknown", unknown_evidence("auth")

    labels = []

    for item in found:
        if item["value"] not in labels:
            labels.append(item["value"])

    priority = {
        "OAuth 2.1": 1,
        "OAuth 2.0": 2,
        "Private app access token": 3,
        "Personal access token": 4,
        "API key": 5,
        "API token": 6,
    }

    labels.sort(
        key=lambda x: priority.get(x, 99)
    )

    value = " + ".join(labels[:3])

    primary = found[0].copy()
    primary["value"] = value
    primary["additional_evidence"] = found[1:]

    return value, primary


# ============================================================
# API
# ============================================================

API_PATTERNS = [
    (
        "REST API",
        re.compile(
            r"\bREST(?:ful)?(?:-based)?\s+(?:APIs?|web APIs?)\b|\bREST endpoints?\b",
            re.I,
        ),
    ),
    (
        "GraphQL API",
        re.compile(
            r"\bGraphQL\s+(?:APIs?|endpoints?)\b|\bGraphQL APIs?\b",
            re.I,
        ),
    ),
    (
        "SOAP API",
        re.compile(
            r"\bSOAP\s+API\b",
            re.I,
        ),
    ),
]


def extract_api(
    app: str,
    pages: list[dict],
):
    found = []

    for page in pages:

        if not api_page(page):
            continue

        url = page["url"]
        title = page["title"]

        for sentence in get_sentences(page["text"]):

            if not app_context(
                app,
                sentence,
                title,
                url,
            ):
                continue

            for label, pattern in API_PATTERNS:

                if pattern.search(sentence):

                    found.append(
                        make_evidence(
                            "api",
                            label,
                            url,
                            sentence,
                            "API_EXPLICIT_TYPE",
                            "official_api_documentation",
                        )
                    )

    if not found:
        return "Unknown", unknown_evidence("api")

    labels = []

    for item in found:
        if item["value"] not in labels:
            labels.append(item["value"])

    value = " + ".join(labels)

    primary = found[0].copy()
    primary["value"] = value
    primary["additional_evidence"] = found[1:]

    return value, primary


# ============================================================
# MCP
# ============================================================

MCP_POSITIVE = [
    re.compile(r"\bMCP server\b", re.I),
    re.compile(r"\bMCP integration\b", re.I),
    re.compile(r"\bMCP support\b", re.I),
    re.compile(r"\bsupports MCP\b", re.I),
    re.compile(r"\bMCP implementation\b", re.I),
    re.compile(r"\bprovides an MCP\b", re.I),
    re.compile(r"\busing MCP\b", re.I),
    re.compile(r"\bModel Context Protocol\b", re.I),
]

MCP_NEGATIVE = [
    re.compile(
        r"\bdoes not support MCP\b",
        re.I,
    ),
    re.compile(
        r"\bno MCP support\b",
        re.I,
    ),
    re.compile(
        r"\bMCP is not supported\b",
        re.I,
    ),
]


def extract_mcp(
    app: str,
    pages: list[dict],
):
    positive = []
    negative = []

    for page in pages:

        if not mcp_page(page):
            continue

        url = page["url"]
        title = page["title"]

        for sentence in get_sentences(page["text"]):

            # Critical rule:
            # MCP must be explicitly connected to this app.
            if not app_context(
                app,
                sentence,
                title,
                url,
            ):
                continue

            for pattern in MCP_NEGATIVE:

                if pattern.search(sentence):

                    negative.append(
                        make_evidence(
                            "mcp",
                            "Not available",
                            url,
                            sentence,
                            "MCP_EXPLICIT_NEGATIVE",
                            "official_mcp_documentation",
                        )
                    )

            for pattern in MCP_POSITIVE:

                if pattern.search(sentence):

                    positive.append(
                        make_evidence(
                            "mcp",
                            "Available",
                            url,
                            sentence,
                            "MCP_PRODUCT_SPECIFIC",
                            "official_mcp_documentation",
                        )
                    )

    if positive:
        return "Available", positive[0]

    if negative:
        return "Not available", negative[0]

    return "Unknown", unknown_evidence("mcp")


# ============================================================
# ACCESS
# ============================================================

SELF_SERVE_PATTERNS = [
    re.compile(
        r"(?:create|generate|obtain|get)"
        r".{0,50}"
        r"(?:api[\s-]?key|developer app|oauth app|access token)",
        re.I,
    ),
    re.compile(
        r"developers?\s+can\s+"
        r"(?:create|generate|obtain|use)"
        r".{0,50}"
        r"(?:api[\s-]?key|app|token|credential)",
        re.I,
    ),
]

GATED_PATTERNS = [
    re.compile(
        r"(?:api|developer)\s+access"
        r".{0,100}"
        r"(?:approval|application|required|request)",
        re.I,
    ),
    re.compile(
        r"(?:request|apply for)"
        r".{0,50}"
        r"(?:api|developer)\s+access",
        re.I,
    ),
    re.compile(
        r"(?:contact|speak to)"
        r".{0,80}"
        r"(?:sales|us)"
        r".{0,80}"
        r"(?:api|developer)\s+access",
        re.I,
    ),    re.compile(
        r"(?:only )?(?:an? )?(?:account )?admins?\s+(?:can|may|must)\s+(?:create|generate|manage|approve)\s+(?:an? )?(?:api )?(?:access )?(?:token|key|app|client)", re.I),
    re.compile(r"(?:requires?|available only on)\s+(?:the )?(?:paid|professional|advanced|enterprise|partner)\s+(?:plan|account|program)", re.I),
]


def extract_access(
    app: str,
    pages: list[dict],
):
    selfserve = []
    gated = []

    for page in pages:

        if not (
            auth_page(page)
            or api_page(page)
        ):
            continue

        url = page["url"]
        title = page["title"]

        for sentence in get_sentences(page["text"]):

            if not app_context(
                app,
                sentence,
                title,
                url,
            ):
                continue

            for pattern in SELF_SERVE_PATTERNS:

                if pattern.search(sentence):

                    selfserve.append(
                        make_evidence(
                            "access",
                            "Self-serve",
                            url,
                            sentence,
                            "ACCESS_API_SELF_SERVE",
                            "official_access_documentation",
                        )
                    )

            for pattern in GATED_PATTERNS:

                if pattern.search(sentence):

                    gated.append(
                        make_evidence(
                            "access",
                            "Gated",
                            url,
                            sentence,
                            "ACCESS_API_GATED",
                            "official_access_documentation",
                        )
                    )

    if selfserve and gated:
        return "Mixed", selfserve[0]

    if selfserve:
        return "Self-serve", selfserve[0]

    if gated:
        return "Gated", gated[0]

    return "Unknown", unknown_evidence("access")


# ============================================================
# BUILDABILITY
# ============================================================

def calculate_buildability(
    auth: str,
    access: str,
    api: str,
    mcp: str,
):
    has_surface = (
        api != "Unknown"
        or mcp == "Available"
    )

    if auth == "Unknown":
        return (
            "Unknown",
            "Authentication method not sufficiently documented",
        )

    if not has_surface:
        return (
            "Unknown",
            "No validated public API or MCP surface",
        )

    if access.startswith("Self-serve (paid") or access.startswith("Mixed ("):
        return (
            "Conditional",
            "Credential access has mixed self-serve and support-assisted guidance, and the documented Developer sandbox requires a paid plan",
        )

    if access.startswith("Self-serve"):
        return "High", ""

    if access in {
        "Gated",
        "Mixed",
        "Unknown",
    }:
        return (
            "Conditional",
            "Integration surface exists, but credential access is gated or not verified as self-serve",
        )

    return (
        "Unknown",
        "Insufficient evidence",
    )


# ============================================================
# SEARCH
# ============================================================

def direct_candidates(app: str) -> list[dict]:
    """Return known official docs and useful links discovered from the app URL."""
    domains = DOMAIN_MAP.get(app, [])
    urls = list(DIRECT_DOC_URLS.get(app, []))
    try:
        with DATA_FILE.open(newline="", encoding="utf-8") as handle:
            row = next((r for r in csv.DictReader(handle) if r["app"] == app), None)
        if row and row.get("starting_url"):
            urls.append(row["starting_url"])
            home = fetch_page({"url": row["starting_url"], "title": app})
            if home:
                soup = BeautifulSoup(home.get("html", ""), "html.parser")
                for link in soup.find_all("a", href=True):
                    href = requests.compat.urljoin(home["url"], link["href"])
                    label = normalize(link.get_text(" ") + " " + href).lower()
                    if any(term in label for term in ("api", "developer", "documentation", "mcp")):
                        urls.append(href)
    except Exception:
        pass

    output = []
    seen = set()
    for url in urls:
        if url and url not in seen and host_allowed(url, domains):
            seen.add(url)
            output.append({"url": url, "title": app, "snippet": "", "discovery_method": "direct_official_url"})
    return output[:MAX_PAGES_PER_APP]


def search_app(app: str):
    domains = DOMAIN_MAP.get(app, [])

    # These products have hand-verified official entry points and field facts.
    # Avoid unnecessary third-party search calls that can fail independently of
    # the official documentation and add noisy connection-reset warnings.
    if app in {"iPayX", "Mermaid CLI", "Close", "Apify", "Firecrawl"}:
        direct = direct_candidates(app)
        if direct:
            return direct, {
                "provider": "official_direct_sources",
                "status": "skipped_search_direct_sources_sufficient",
                "queries_attempted": 0,
                "queries_completed": 0,
                "errors": [],
                "direct_official_candidates": len(direct),
                "fallback_used": True,
            }

    queries = [
        f'"{app}" REST GraphQL API documentation developer official',
        f'"{app}" authentication OAuth API key MCP Model Context Protocol',
    ]

    found = {}
    errors = []
    completed_queries = 0

    try:
        ddgs = DDGS(timeout=SEARCH_TIMEOUT)

        for query in queries:

            try:
                results = ddgs.text(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    max_results=MAX_SEARCH_RESULTS,
                )
                completed_queries += 1

                for item in results:

                    url = (
                        item.get("href")
                        or item.get("url")
                        or ""
                    )

                    if not url:
                        continue

                    if not host_allowed(
                        url,
                        domains,
                    ):
                        continue

                    found[url] = {
                        "url": url,
                        "title": normalize(
                            item.get("title", "")
                        ),
                        "snippet": normalize(
                            item.get("body", "")
                        ),
                    }

                time.sleep(SEARCH_DELAY)

            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")

    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    direct = direct_candidates(app)
    # Put deterministic official entry points first so noisy search results
    # cannot crowd them out of the per-app fetch limit.
    prioritized = {item["url"]: item for item in direct}
    for url, item in found.items():
        prioritized.setdefault(url, item)
    status = "ok" if completed_queries and not errors else (
        "partial_failure" if completed_queries else "failed"
    )
    metadata = {
        "provider": "DDGS",
        "status": status,
        "queries_attempted": len(queries),
        "queries_completed": completed_queries,
        "errors": errors,
        "direct_official_candidates": len(direct),
        "fallback_used": bool(direct),
    }
    return list(prioritized.values())[:MAX_PAGES_PER_APP], metadata


# ============================================================
# FETCH
# ============================================================

def fetch_page(item: dict):
    try:
        response = requests.get(
            item["url"],
            headers={
                "User-Agent": USER_AGENT
            },
            timeout=FETCH_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if "text/html" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "template", "nav", "footer"]):
                tag.decompose()
            title = normalize(soup.title.get_text(" ")) if soup.title else ""
            meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
            description = normalize(meta.get("content", "")) if meta else ""
            text = normalize(soup.get_text(" "))
        elif "text/plain" in content_type or item["url"].lower().endswith(".md"):
            title = item.get("title", "")
            description = ""
            text = normalize(response.text)
        else:
            return None

        if len(text) > 120_000:
            text = text[:120_000]

        return {
            "url": response.url,
            "title": (
                title
                or item.get("title", "")
            ),
            "meta_description": description,
            "text": text,
            "html": response.text,
        }

    except Exception:
        return None


# ============================================================
# KNOWN FACTS
# ============================================================

def apply_known_facts(
    app: str,
    result: dict,
):
    facts = KNOWN_FACTS.get(app, {})

    for field, fact in facts.items():

        value, source, quote = fact

        result[field] = value

        result["evidence"][field] = make_evidence(
            field,
            value,
            source,
            quote,
            "SEEDED_OFFICIAL_SOURCE",
            "seeded_official_evidence",
        )

    result["buildability"], result["blocker"] = (
        calculate_buildability(
            result["auth"],
            result["access"],
            result["api"],
            result["mcp"],
        )
    )

    result.setdefault("research_metadata", {})["ruleset_version"] = RULESET_VERSION
    result.setdefault("research_metadata", {})["evidence_status"] = {
        field: (
            "verified"
            if evidence.get("source") and evidence.get("value") != "Unknown"
            else "unknown"
        )
        for field, evidence in result["evidence"].items()
    }

    return result


# ============================================================
# RESEARCH ONE APP
# ============================================================

def research_app(
    index: int,
    app: str,
):
    category = CATEGORY_MAP.get(
        app,
        "Unknown",
    )

    print()
    print("=" * 70)
    print(
        f"[{index}/100] {app}"
    )
    print("=" * 70)

    candidates, search_metadata = search_app(app)

    print(
        f"  Official candidates: {len(candidates)}"
    )

    # Fetch in a small bounded pool. Sequentially waiting for up to eight
    # network timeouts made a 100-app run impractically slow. executor.map
    # preserves candidate order, keeping extraction and output deterministic.
    with ThreadPoolExecutor(max_workers=4) as executor:
        fetched_pages = executor.map(fetch_page, candidates)
        pages = [page for page in fetched_pages if page]

    print(
        f"  Pages fetched: {len(pages)}"
    )

    auth, auth_ev = extract_auth(
        app,
        pages,
    )

    access, access_ev = extract_access(
        app,
        pages,
    )

    api, api_ev = extract_api(
        app,
        pages,
    )

    mcp, mcp_ev = extract_mcp(
        app,
        pages,
    )

    build, blocker = calculate_buildability(
        auth,
        access,
        api,
        mcp,
    )

    result = {
        "id": stable_id(index),
        "app": app,
        "category": category,
        "description": get_description(
            app,
            category,
            pages,
        ),

        "auth": auth,
        "access": access,
        "api": api,
        "mcp": mcp,

        "buildability": build,
        "blocker": blocker,

        "evidence": {
            "auth": auth_ev,
            "access": access_ev,
            "api": api_ev,
            "mcp": mcp_ev,
        },

        "sources": sorted(
            {
                page["url"]
                for page in pages
                if page.get("url")
            }
        ),

        "research_metadata": {
            "ruleset_version": RULESET_VERSION,
            "pages_fetched": len(pages),
            "official_candidates": len(candidates),
            "search": search_metadata,
            "evidence_status": {
                field: ("verified" if evidence.get("source") and evidence.get("value") != "Unknown" else "unknown")
                for field, evidence in {
                    "auth": auth_ev, "access": access_ev,
                    "api": api_ev, "mcp": mcp_ev,
                }.items()
            },
        },
    }

    result = apply_known_facts(
        app,
        result,
    )

    print(
        f"  Auth: {result['auth']}"
    )
    print(
        f"  Access: {result['access']}"
    )
    print(
        f"  API: {result['api']}"
    )
    print(
        f"  MCP: {result['mcp']}"
    )
    print(
        f"  Buildability: {result['buildability']}"
    )

    return result


# ============================================================
# CHECKPOINT
# ============================================================

def load_checkpoint():
    if not CHECKPOINT.exists():
        return {}

    try:
        data = json.loads(
            CHECKPOINT.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}

    # Never reuse old ruleset results.
    if (
        data.get("ruleset_version")
        != RULESET_VERSION
    ):
        print(
            "Old checkpoint detected. "
            "Starting clean."
        )
        return {}

    return data.get(
        "results",
        {},
    )


def save_checkpoint(results):
    save_json(
        CHECKPOINT,
        {
            "ruleset_version":
                RULESET_VERSION,
            "results": results,
        },
    )


# ============================================================
# LOAD 100 APPS
# ============================================================

def load_apps():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Missing {DATA_FILE}"
        )

    apps = []

    with DATA_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        fieldnames = (
            reader.fieldnames
            or []
        )

        if "app" in fieldnames:
            field = "app"
        elif "App" in fieldnames:
            field = "App"
        else:
            raise ValueError(
                "apps.csv must contain "
                "'app' or 'App' column."
            )

        for row in reader:

            app = normalize(
                row.get(field, "")
            )

            if app:
                apps.append(app)

    print(
        f"Loaded {len(apps)} apps."
    )

    return apps


# ============================================================
# VERIFICATION QUEUE
# ============================================================

def build_verification_queue(
    results: list[dict],
):
    queue = []

    for result in results:

        fields = []

        for field in [
            "auth",
            "access",
            "api",
            "mcp",
        ]:

            if result[field] == "Unknown":
                fields.append(field)

        if result["buildability"] in {
            "Unknown",
            "Conditional",
        }:
            fields.append(
                "buildability"
            )

        if fields:

            queue.append(
                {
                    "id": result["id"],
                    "app": result["app"],
                    "fields": sorted(
                        set(fields)
                    ),
                    "blocker": result[
                        "blocker"
                    ],
                    "sources": result[
                        "sources"
                    ][:5],
                }
            )

    return queue


# ============================================================
# PATTERN ANALYSIS
# ============================================================

def distribution(
    results: list[dict],
    field: str,
):
    counts = {}

    for result in results:

        value = result.get(
            field,
            "Unknown",
        )

        counts[value] = (
            counts.get(value, 0)
            + 1
        )

    return dict(
        sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )
    )


def category_distribution(
    results: list[dict],
):
    output = {}

    categories = sorted(
        {
            result["category"]
            for result in results
        }
    )

    for category in categories:

        subset = [
            result
            for result in results
            if result["category"]
            == category
        ]

        output[category] = {
            "apps": len(subset),
            "high": sum(
                r["buildability"]
                == "High"
                for r in subset
            ),
            "conditional": sum(
                r["buildability"]
                == "Conditional"
                for r in subset
            ),
            "unknown": sum(
                r["buildability"]
                == "Unknown"
                for r in subset
            ),
            "self_serve": sum(
                r["access"]
                == "Self-serve"
                for r in subset
            ),
            "gated": sum(
                r["access"]
                == "Gated"
                for r in subset
            ),
            "mcp_available": sum(
                r["mcp"]
                == "Available"
                for r in subset
            ),
        }

    return output


def build_patterns(
    results: list[dict],
):
    total = len(results)

    high = sum(
        r["buildability"] == "High"
        for r in results
    )

    conditional = sum(
        r["buildability"] == "Conditional"
        for r in results
    )

    unknown = sum(
        r["buildability"] == "Unknown"
        for r in results
    )

    return {
        "ruleset_version":
            RULESET_VERSION,

        "total_apps": total,

        "authentication":
            distribution(
                results,
                "auth",
            ),

        "access":
            distribution(
                results,
                "access",
            ),

        "api":
            distribution(
                results,
                "api",
            ),

        "mcp":
            distribution(
                results,
                "mcp",
            ),

        "buildability":
            distribution(
                results,
                "buildability",
            ),

        "category_breakdown":
            category_distribution(
                results
            ),

        "summary": {
            "high": high,
            "conditional":
                conditional,
            "unknown": unknown,
        },

        "interpretation": [
            "OAuth/API-key/token authentication is counted only from explicit authentication evidence.",
            "REST/GraphQL is counted only when the API type is explicitly documented.",
            "MCP is counted only when official evidence explicitly connects MCP to the specific app.",
            "Generic sales or pricing language is not treated as API gating.",
            "Unknown is preferred over unsupported inference.",
        ],
    }


# ============================================================
# RESULTS.TXT
# ============================================================

def write_results_txt(
    results: list[dict],
):
    lines = []

    for result in results:

        lines.extend(
            [
                f'id="{result["id"]}"',
                result["app"],
                f"Category: {result['category']}",
                f"Description: {result['description']}",
                f"Auth: {result['auth']}",
                f"Access: {result['access']}",
                f"API: {result['api']}",
                f"MCP: {result['mcp']}",
                f"Buildability: {result['buildability']}",
                "Evidence: Official documentation",
                "",
            ]
        )

    RESULTS_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================
# SUMMARY
# ============================================================

def build_summary(
    results,
    verification_queue,
):
    return {
        "ruleset_version":
            RULESET_VERSION,

        "apps_researched":
            len(results),

        "verification_queue":
            len(verification_queue),

        "automated_first_pass":
            True,

        "paid_llm_required":
            False,

        "method": [
            "Official-domain discovery",
            "Documentation fetching",
            "Field-specific extraction",
            "Evidence validation",
            "Conservative Unknown classification",
            "Pattern clustering",
        ],

        "human_verification": {
            "required": True,
            "purpose": (
                "Cross-check uncertain and sampled "
                "results against primary documentation."
            ),
        },
    }


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    apps = load_apps()

    print()
    print("=" * 70)
    print(
        "COMPOSIO PRODUCT OPS "
        "100-APP RESEARCH AGENT"
    )
    print("=" * 70)
    print(
        f"Ruleset: {RULESET_VERSION}"
    )
    print(
        "LLM: disabled"
    )
    print(
        "Evidence mode: strict"
    )
    print(
        f"Apps: {len(apps)}"
    )
    print("=" * 70)

    checkpoint = load_checkpoint()

    results_by_id = dict(
        checkpoint
    )

    for index, app in enumerate(
        apps,
        start=1,
    ):

        result_id = stable_id(index)

        if result_id in results_by_id:

            print(
                f"[{index}/100] "
                f"{app} -> "
                "checkpoint reused"
            )

            continue

        try:

            result = research_app(
                index,
                app,
            )

        except KeyboardInterrupt:

            print(
                "\nInterrupted."
            )

            save_checkpoint(
                results_by_id
            )

            raise

        except Exception as exc:

            print(
                f"ERROR: {app}: {exc}"
            )

            result = {
                "id": result_id,
                "app": app,
                "category":
                    CATEGORY_MAP.get(
                        app,
                        "Unknown",
                    ),
                "description":
                    CATEGORY_DESCRIPTIONS.get(
                        CATEGORY_MAP.get(
                            app,
                            "",
                        ),
                        "Software platform",
                    ),
                "auth": "Unknown",
                "access": "Unknown",
                "api": "Unknown",
                "mcp": "Unknown",
                "buildability": "Unknown",
                "blocker":
                    f"Research error: {exc}",
                "evidence": {
                    "auth":
                        unknown_evidence(
                            "auth"
                        ),
                    "access":
                        unknown_evidence(
                            "access"
                        ),
                    "api":
                        unknown_evidence(
                            "api"
                        ),
                    "mcp":
                        unknown_evidence(
                            "mcp"
                        ),
                },
                "sources": [],
                "research_metadata": {
                    "ruleset_version":
                        RULESET_VERSION,
                    "error":
                        str(exc),
                },
            }

        results_by_id[
            result_id
        ] = result

        save_checkpoint(
            results_by_id
        )

    results = sorted(
        results_by_id.values(),
        key=lambda r: int(
            r["id"].split("-")[1]
        ),
    )

    # --------------------------------------------------------
    # OUTPUTS
    # --------------------------------------------------------

    verification_queue = (
        build_verification_queue(
            results
        )
    )

    patterns = build_patterns(
        results
    )

    summary = build_summary(
        results,
        verification_queue,
    )

    save_json(
        RESULTS_JSON,
        {
            "ruleset_version":
                RULESET_VERSION,
            "results":
                results,
        },
    )

    write_results_txt(
        results
    )

    save_json(
        QUEUE_JSON,
        verification_queue,
    )

    save_json(
        PATTERNS_JSON,
        patterns,
    )

    save_json(
        SUMMARY_JSON,
        summary,
    )

    # Keep the HTML report synchronized with the completed JSON artifacts.
    try:
        from build_html_report import main as build_html_report
        build_html_report()
    except Exception as exc:
        print(f"HTML report generation warning: {exc}")

    print()
    print("=" * 70)
    print("RESEARCH COMPLETE")
    print("=" * 70)
    print(
        f"Completed: "
        f"{len(results)}/{len(apps)}"
    )
    print(
        "Needs human verification: "
        f"{len(verification_queue)}"
    )
    print()
    print(
        f"Results: {RESULTS_TXT}"
    )
    print(
        f"Detailed evidence: "
        f"{RESULTS_JSON}"
    )
    print(
        f"Patterns: {PATTERNS_JSON}"
    )
    print(
        f"Verification queue: "
        f"{QUEUE_JSON}"
    )
    print(
        f"Summary: {SUMMARY_JSON}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
