# GitHub Pages verification

Verified on 2026-08-26.

- Site: https://ju-wikun.github.io/london-bike-sharing-analysis/
- Initial deployment: https://github.com/Ju-Wikun/london-bike-sharing-analysis/actions/runs/32930639686
- Quality checks: 29 passed; pytest: 4 passed, including deployment-bundle allowlist checks.
- Deployment bundle: index.html, six active HTML views, ECharts 5.5.1, upstream license, and .nojekyll. No raw trips, database, resume or private workspace data.
- Six public navigation buttons were clicked and each iframe title verified. Canvas counts: overview 3; time 4; environment 7; flow structure 4; station diagnostics 7; season 8.
- Mobile smoke check at 390x844: outer width/scroll width 390/390; flow document width/scroll width 375/375. Layout stacks chart columns and KPI tiles. Dense charts are best inspected on desktop.
- Fixed-version ECharts is served by the same Pages origin; external CDN is fallback only.
- Public footer links to TfL, Open-Meteo, and repository data notices.
