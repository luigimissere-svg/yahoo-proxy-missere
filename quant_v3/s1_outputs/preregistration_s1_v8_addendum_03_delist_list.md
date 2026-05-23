# Pre-registration S1 v8 — Addendum 03-DELIST-LIST

Data sigillo: 23/05/2026 — 20:55 CEST (emesso retrospettivamente)
Riferimento: pre-reg root + addendum 01 + addendum 02-WIKI-PARSER
Scope: lista esplicita ticker rimossi da S&P 500 nel periodo 2020-2026

## Nota di emissione

Come addendum 02-WIKI-PARSER, anche questo è emesso retrospettivamente
dopo che gli artefatti tecnici (CSV) erano già committati in `4d2101d`.
Mea culpa registrato in §0 della risposta consulente al mandato S1.

## Correzione numerica importante (mea culpa onesto)

Nel summary precedente avevo dichiarato "40 ticker rimossi 2024→2026".
Riconteggio rigoroso da `sp500_changes_2020_2026.csv` filtrato
`date_iso >= 2024-01-01`:

**42 ticker rimossi distinti nel periodo 2024-01-01 → 2026-05-07.**

Differenza di +2 rispetto al numero precedentemente dichiarato. Causa:
errore di calcolo manuale nel summary. La criterio pre-reg "≥ 15 ticker
rimossi" è ampiamente soddisfatto (42 >> 15), quindi il verdetto S1.2
PASS resta valido. Ma il numero corretto è 42, non 40.

## Statistiche universo

| Universo | N. ticker | SHA256 |
|---|---|---|
| Snapshot 23/05/2026 (corrente) | 503 | `dbe9a0371bd0ef09...` |
| Eventi changes 2020-2026 | 125 eventi, 112 rimozioni distinte | `c1b7e455cf3f7d0a...` |
| Universe PIT v8 | 616 ticker | `6c350fd7566bf300...` |
| Rimossi 2024-2026 nel PIT | 42 | (vedi tabella sotto) |
| Rimossi 2020-2023 nel PIT | 70 | (back-revert da snapshot) |

Decomposizione: 616 PIT = 503 snapshot + 113 ticker storici riaggiunti
dalla back-revert delle changes (112 rimozioni distinte + 1 caso edge
con doppia change su stesso ticker).

## Lista completa rimozioni 2024-2026 (ordine cronologico)

| Data | Ticker | Security |
|---|---|---|
| 2024-03-18 | WHR | Whirlpool Corporation |
| 2024-03-18 | ZION | Zions Bancorporation |
| 2024-04-03 | VFC | VF Corporation |
| 2024-04-03 | XRAY | Dentsply Sirona |
| 2024-05-08 | PXD | Pioneer Natural Resources |
| 2024-06-24 | CMA | Comerica |
| 2024-06-24 | ILMN | Illumina, Inc. |
| 2024-06-24 | RHI | Robert Half |
| 2024-09-23 | AAL | American Airlines Group |
| 2024-09-23 | BIO | Bio-Rad Laboratories |
| 2024-09-23 | ETSY | Etsy |
| 2024-10-01 | BBWI | Bath & Body Works, Inc. |
| 2024-11-26 | MRO | Marathon Oil |
| 2024-12-23 | AMTM | Amentum |
| 2024-12-23 | CTLT | Catalent |
| 2024-12-23 | QRVO | Qorvo |
| 2025-03-24 | BWA | BorgWarner |
| 2025-03-24 | CE | Celanese |
| 2025-03-24 | FMC | FMC Corporation |
| 2025-03-24 | TFX | Teleflex |
| 2025-05-19 | DFS | Discover Financial |
| 2025-07-09 | JNPR | Juniper Networks |
| 2025-07-18 | ANSS | Ansys |
| 2025-07-23 | HES | Hess Corporation |
| 2025-08-28 | WBA | Walgreens Boots Alliance |
| 2025-09-22 | CZR | Caesars Entertainment |
| 2025-09-22 | ENPH | Enphase Energy |
| 2025-09-22 | MKTX | MarketAxess |
| 2025-10-31 | KMX | CarMax |
| 2025-11-04 | EMN | Eastman Chemical Co. |
| 2025-11-28 | IPG | Interpublic Group |
| 2025-12-11 | K | Kellanova |
| 2025-12-22 | LKQ | LKQ Corporation |
| 2025-12-22 | MHK | Mohawk Industries |
| 2025-12-22 | SOLS | Solstice Advanced Materials |
| 2026-02-09 | DAY | Dayforce |
| 2026-03-23 | LW | Lamb Weston |
| 2026-03-23 | MOH | Molina Healthcare |
| 2026-03-23 | MTCH | Match Group |
| 2026-03-23 | PAYC | Paycom |
| 2026-04-09 | HOLX | Hologic |
| 2026-05-07 | CTRA | Coterra Energy |

**Conta verificata**: 42.

## Verifica falsificazione F1 della pre-reg

Pre-reg: "se universo storico identico a attuale → Bug 6 non materiale".
Universo PIT (616) ≠ snapshot attuale (503), differenza 113 ticker.
Verdetto: **Bug 6 MATERIALE confermato, mitigazione corretta**.

## Limiti dichiarati

1. **Reasoning dei delisting non distinto**: alcune rimozioni sono per
   M&A (es. PXD → ExxonMobil), altre per market cap (es. WBA), altre
   per spin-off (es. SOLS da HON). Non distinguiamo nel PIT — tutte
   sono trattate come "ticker membri al tempo T".

2. **Date di effective inclusion vs trading date**: vedi §3.4 di
   addendum 02-WIKI-PARSER.

3. **Cross-check fonte secondaria**: pendente al gate 27/05 (iShares
   IVV holdings storici via SEC EDGAR 13F filings).

## Tracciabilità

- Commit artefatti: `4d2101d`
- Commit questo addendum: TBD (gate 24/05 21:30)

SHA256 di questo file: (calcolato post-write)
