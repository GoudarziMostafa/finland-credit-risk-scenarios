# Lending source and exposure construction

**Source: Bank of Finland, MFI_PUBL.** The observed snapshot is **31 December 2025**, using end-of-period outstanding loan stocks, all currencies expressed in euros. Reporter scope is **MFIs excluding Bank of Finland**. Borrowers are domestic non-financial corporations (sector 2241), excluding housing corporations.

## Selection and definitions

The common series template is:
`M.A.0.A.A20.A.A.U6.2241.{industry}.Z01.A.A.0.A.0.A.0`

- M: monthly; reporter A: MFIs excluding Bank of Finland.
- Measure 0: volume; transaction A: stock; balance-sheet item A20: loans.
- Area U6: domestic; borrower sector 2241: non-financial corporations.
- Industry ZZ: all; C: manufacturing; F: construction; L: real estate activities.
- Currency Z01: all currencies combined, **not only euro-denominated loans**.
- Remaining dimensions: all maturities, purposes, collateral types, loan sizes and interest-rate categories.
- Metadata UNIT=EUR, UNIT_MULT=6: multiply by 1,000,000. COLLECTION=E: end of period.

[Source API documentation](https://portal.boffsaopendata.fi/apis) · [Dimension definitions](https://api.boffsaopendata.fi/v4/structures/MFI_PUBL) · [Official access guide](https://www.suomenpankki.fi/en/statistics/statistics-info/whats_new/2023/using-the-open-data-service-interface/).

The selected C/F/L series end in December 2025, while the total continues into 2026. The analysis deliberately uses the last common December 2025 observation. Industry classifications change beginning in 2026; this avoids splicing TOL 2008 groups into revised classifications. The [official December 2025 release](https://www.suomenpankki.fi/en/statistics/statistical-news/mfi-balance-sheet/2026/household-bank-loans-almost-unchanged-year-on-year-in-december-2025/) corroborates the housing exclusion: roughly EUR108.8bn including housing corporations less EUR45.9bn housing corporations is roughly EUR62.9bn.

## Verified snapshot

| Group | Outstanding loans, EUR million | Status |
|---|---:|---|
| Manufacturing | 9,737.49721038 | Observed |
| Construction | 2,559.93771998 | Observed |
| Real estate activities | 16,266.26549554 | Observed |
| Remaining and unclassified industries | 34,351.83714290 | Derived residual |
| Total | 62,915.53756880 | Independently observed source total |

The API precision is preserved for reproducibility; the report rounds monetary findings. The residual is total minus C, F and L. It does not imply a homogeneous credit-risk group.

## EAD proxy and existing non-performing loans

The model uses these outstanding stocks as fixed EAD proxies. **Existing non-performing balances are retained.** Compatible sector-specific NPL balances are not part of this selected snapshot; we do not estimate them by treating an NPL ratio as PD or fabricate a deduction. No amortisation, new lending or undrawn commitments are modelled.

Consequently, PD×LGD×stock is an illustrative **scenario loss proxy on outstanding balances**. It is not a forecast of new defaults on a performing portfolio or a complete expected-credit-loss measurement. Different starting PDs for existing defaults, recovery cash flows and credit states would be required for that.

## Reproduce and refresh

- Offline replay: `python -m credit_scenarios.lending`
- Explicit revised data retrieval: `python -m credit_scenarios.lending --refresh`

Raw series metadata and observations, exact request URLs, retrieval UTC timestamp and SHA-256 digests are saved in data/raw/bof_mfi_*.json. The parser checks the expected series set, code/metadata consistency, unit multiplier, collection basis, common date, finite nonnegative values and residual reconciliation. Refreshing may change past observations through source revisions.

The response carries the licence header **Creative Common CC BY 4.0.** Attribution: **Source: Bank of Finland.** The residual category, euro conversion and scenario calculations are project transformations.
