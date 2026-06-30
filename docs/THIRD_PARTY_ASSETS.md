# Third-Party Assets

| Asset | Version | License | Source | Local Path |
|---|---|---|---|---|
| HTMX | 2.0.4 | BSD 2-Clause | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | `app/static/vendor/htmx/htmx.min.js` |

## Notes

- HTMX is loaded locally via `url_for('static', filename='vendor/htmx/htmx.min.js')`.
- No remote CDN dependencies at runtime.
- No runtime Alpine.js dependency — drawer behavior is implemented in vanilla JS.
