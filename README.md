# TPRM DDA Artifact Coverage Agent — Phase 2.1

This is a GitHub-ready Streamlit Community Cloud demo for an artifact-centered Third Party Risk Management DDA workflow.

## What this version demonstrates

- Historical DDA repository for seven domains:
  - InfoSec
  - Model Risk
  - Regulatory
  - Reputation
  - Finance
  - Business Resiliency
  - Operational
- DDA-to-artifact mapping
- Artifact freshness / expiration logic
- LexisNexis-style vendor/entity fuzzy matching
- Abbreviated DDA artifact request generation
- Risk Advisor action center
- Vendor artifact upload simulation
- Before / after coverage refresh
- Optional OpenAI-powered Q&A tab
- Rule-based fallback Q&A when no OpenAI key is configured

## Repository structure

```text
app.py
requirements.txt
README.md
.gitignore
.streamlit/config.toml
data/
  historical_ddas.csv
  artifacts_required_to_complete_ddas.csv
  lexisnexis_vendor_records.csv
  new_triggered_dda_package.csv
  vendor_uploaded_artifacts.csv
  public_evidence_library.csv
```

## Streamlit Community Cloud deployment

1. Create a new public GitHub repository.
2. Upload the contents of this folder to the repo root.
3. Confirm `app.py` is at the repository root.
4. In Streamlit Community Cloud, deploy from GitHub.
5. Use:

```text
Main file path: app.py
```

## Optional OpenAI Q&A

The app will run without OpenAI. If no key is configured, the Q&A tab uses fallback rule-based responses.

To enable OpenAI Q&A in Streamlit Community Cloud:

1. Deploy the app.
2. Go to Manage App > Settings > Secrets.
3. Add:

```toml
OPENAI_API_KEY = "your-key-here"
```

4. Save and reboot the app.

Do not commit your OpenAI key to GitHub.

## Demo talk track

1. Show the historical DDA repository across seven domains.
2. Explain that the new review triggers multiple DDAs.
3. Run artifact coverage analysis.
4. Show which artifacts are reusable, expiring, expired, or missing.
5. Review LexisNexis-style vendor/entity matches.
6. Generate the abbreviated DDA artifact request.
7. Draft the vendor outreach email.
8. Use sample vendor upload.
9. Re-run coverage and show before/after improvement.
10. Use the Q&A tab to ask plain-English questions about gaps, stale artifacts, and vendor matches.

## Data sensitivity

All data in this demo is synthetic. Do not upload proprietary DDA content, Archer exports, vendor evidence, or confidential risk records into the public demo.

## Phase 2.1a Update

This version adds a multi-vendor selector in the sidebar. The default demo vendor is **Contoso AI Services**, with additional synthetic vendors included to show how the same workflow can operate across a broader third-party portfolio.

It also fixes the Abbreviated DDA Artifact Request display so the Risk Advisor editable request appears cleanly instead of showing an empty styled bar.
