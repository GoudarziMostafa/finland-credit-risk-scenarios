# Economic context: Statistics Finland bankruptcies

Source: Statistics Finland, StatFin table **13fd**, *Bankruptcies monthly by legal form and industry*. [API and table metadata](https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/kony/13fd.px).

The selected measure is **kylkm: Bankruptcies instigated, number of enterprises**. We select total legal forms (SSS), industries total (SSS), manufacturing (C), construction (F) and real estate activities (L), using TOL 2008. Other industries are derived as total minus C, F and L. Monthly counts are summed to complete quarters. The saved manifest states the exact end quarter.

The source counts the first bankruptcy petition per enterprise within a calendar year. These are instigated proceedings, not concluded bankruptcies, loan defaults or default probabilities. Total legal forms includes natural persons and other legal entities; it is broader than the population of corporate bank borrowers. Industry counts also depend on industry size. No count is divided by lending balances or used to estimate PD. Pandemic-era changes to bankruptcy rules and economic support complicate historical comparisons.

## Reproduce

From an installed project environment:
- Offline replay: `python -m credit_scenarios.macro`
- Explicit new retrieval: `python -m credit_scenarios.macro --refresh --end-quarter 2025Q4`

The module preserves query, raw response, table metadata, retrieval UTC timestamp and SHA-256 digests in data/raw/statfin_kony_13fd_*.json. Replay verifies the saved hashes. It rejects missing or suppressed values, unexpected categories, negative/non-integer counts and incomplete quarters. It writes data/processed/macro.csv and macro_metadata.json. The analysis build uses the saved processed data without making live requests.

## Reuse

[Statistics Finland open data](https://stat.fi/en/services/statistical-data-services/open-data-and-interfaces) is licensed under CC BY 4.0. Attribution: **Source: Statistics Finland.** Quarterly aggregation and the residual category are transformations by this project.
