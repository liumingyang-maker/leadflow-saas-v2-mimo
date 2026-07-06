# MiMo Live Tests

These tests are optional local integration checks for the real MiMo API. They are not part of
normal CI or release gates.

## Default behavior

`tests/live/test_mimo_search_intent_live.py` is skipped unless all required live-test inputs are
provided locally.

Normal test runs remain fake-provider based:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest -q
```

## Manual run

Run the live smoke only from a trusted local shell:

```bash
RUN_LIVE_MIMO=1 \
MIMO_API_KEY=<your-local-mimo-api-key> \
MIMO_BASE_URL=<mimo-openai-compatible-base-url> \
MIMO_MODEL=mimo-v2.5-pro \
PYTHONPATH=$PWD .venv/bin/python -m pytest -q tests/live/test_mimo_search_intent_live.py
```

`MIMO_BASE_URL` may be omitted only if the safe test default is correct for your local MiMo
account. `MIMO_MODEL` defaults to `mimo-v2.5-pro`.

## Secret rules

- Do not commit API keys.
- Do not paste API keys into chat.
- Do not paste Authorization headers into chat.
- Do not store keys in test files or documentation.
- Do not print full prompts or full responses.
- Do not print `reasoning_content`.
- Do not save raw provider responses.

The live tests only print summaries such as model, status, content length, detected product
family, query count, and forbidden-term hit count.

## What the live tests verify

- MiMo OpenAI-compatible chat completion returns usable content.
- Packaging and LED search-intent outputs differ.
- Packaging output stays focused on packaging terms.
- LED output stays focused on LED/lighting terms.
- Outputs avoid private email, phone number, verified buyer claims, purchase intent claims,
  crawling/scraping suggestions, social scraping, and automatic email sending.

## Expected instability

Live tests can fail for reasons outside the app:

- network failures
- 429 rate limits
- provider latency
- model output variation
- temporary provider incidents

Treat failures as smoke-test signals, not normal CI blockers. Production smoke and beta quality
checks should still be executed separately by MimoCode using the approved runbook.
