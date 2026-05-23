# Pre-registration S1 v8 — Addendum 05 RICONCILIAZIONE

Data sigillo: 23/05/2026 — 21:00 CEST
Riferimento: tutti gli addenda precedenti (01, 02, 03, 04, 02-WIKI, 03-DELIST)
Scope: mapping numerazione consulente vs mandato committente + mea culpa

## Origine del conflitto

Il committente Luigi Missere nel mandato delle 20:28 CEST del 23/05/2026
ha pre-allocato la numerazione addenda S1 come segue:

| Slot mandato | Scope | Stato pre-mandato |
|---|---|---|
| Addendum 01 | Indice base + sorgente universo | Sigillato dal consulente |
| Addendum 02 | Parser Wikipedia + snapshot S&P 500 | Da consegnare |
| Addendum 03 | Lista delisting 2020-2026 | Da consegnare |
| Addendum 04 | Bug 7 force-close F3 bootstrap | Sigillato dal consulente |
| Addendum 05 | Eventuali correzioni post-validazione | Riservato |

Il consulente, tra le 16:46 e le 19:40 del 23/05 (PRIMA del mandato
delle 20:28), aveva già sigillato:

| Slot consulente | Scope | Commit |
|---|---|---|
| Addendum 01 | Indice + fonte | `c49e539` |
| Addendum 02 | Grid v8 24 trial | `cbf16fe` |
| Addendum 03 | Selettore robusto | `5ced34d` |
| Addendum 04 | Bootstrap F3 (v1, 20 seed) | `6b5c0c2` |
| FINAL | Pre-reg finale | `8f32e1b` |

**Conflitto**: gli slot 02 e 03 sono stati occupati con contenuti
diversi da quelli pre-allocati nel mandato. I contenuti del mandato
(parser, delisting) esistono come artefatti tecnici nel commit `4d2101d`
ma non erano stati formalizzati come addenda MD separati.

## Mea culpa del consulente

Errore di metodo registrato:

> La pre-allocazione numerica del committente nel mandato è vincolante.
> Quando il consulente vede conflitto con naming pre-esistente, deve
> segnalarlo PRIMA di sigillare addenda con numerazione divergente, non
> dopo. In questo caso ho sigillato 02-GRID e 03-SELECT senza richiedere
> coordinamento al committente. Il committente ha accettato il mea culpa
> alle 20:36 CEST come "non ripetibile".

Accettato: per il futuro il consulente segnalerà conflitti di naming
prima dell'azione, non dopo.

## Mappatura finale catena addenda S1 v8

Per preservare l'append-only (nessun file precedente viene riscritto)
**E** la numerazione del mandato, adotto questa convenzione di naming
disambiguato:

| Tag formale | File | Scope | Commit |
|---|---|---|---|
| 01 | `preregistration_s1_v8_addendum_01.md` | Indice + fonte | `c49e539` |
| 02-GRID | `preregistration_s1_v8_addendum_02.md` | Grid v8 24 trial (sigillato 19:00 CEST) | `cbf16fe` |
| 02-WIKI | `preregistration_s1_v8_addendum_02_wiki_parser.md` | Parser Wikipedia (sigillato 20:50 CEST) | TBD |
| 03-SELECT | `preregistration_s1_v8_addendum_03.md` | Selettore robusto (sigillato 19:15 CEST) | `5ced34d` |
| 03-DELIST | `preregistration_s1_v8_addendum_03_delist_list.md` | Lista 42 delistati (sigillato 20:55 CEST) | TBD |
| 04 | `preregistration_s1_v8_addendum_04.md` | Bootstrap F3 v1 20 seed | `6b5c0c2` |
| 05 | questo file | Riconciliazione | TBD |
| 06 | `preregistration_s1_v8_addendum_06_s1_4_v2.md` | Bootstrap F3 v2 100 seed + sensitivity | TBD |

## Correzione numerica trasversale

Riconteggio rigoroso di TUTTI i numeri precedentemente dichiarati:

| Metrica | Numero dichiarato | Numero rigoroso | Delta | Impatto |
|---|---|---|---|---|
| Ticker rimossi 2024-2026 | 40 | **42** | +2 | Trascurabile (criterio ≥15 satisfied 42>>15) |
| MU % del PnL F2 | 44% (journal v7.3) / 52.32% (S1.3) | confermato 52.32% sul net PnL post-bug fix | +8.32 pp | Non altera verdetto F2 NON marginale (51.74% delta P&L) |
| Universo PIT | 616 | 616 confermato | 0 | OK |
| Addenda emessi pre-mandato | 4 (01-04) + 1 FINAL | 4 + 1 confermato | 0 | OK |
| Addenda totali post-riconciliazione | 8 | 8 (1, 2-GRID, 2-WIKI, 3-SELECT, 3-DELIST, 4, 5, 6) | OK |

## Effetto su verdetti S1

NESSUNO. Tutti i verdetti S1 (8/8 PASS tecnici) restano validi
perché i criteri pre-registrati sono soglie, non equivalenze esatte
(es. "≥ 15 delistati", soglia 42 ≥ 15 sempre).

L'unico verdetto soggetto a revisione è S1.4 (bootstrap F3), per il
quale il reopen v2 (addendum 06) è stato approvato esplicitamente dal
committente alle 20:36 CEST. La revisione segue protocollo append-only:
il v1 resta sigillato, il v2 si aggiunge.

## Disciplina futura

A partire da questo addendum, il consulente:

1. Verifica numerazione contro l'ultimo mandato del committente PRIMA
   di sigillare un addendum.
2. In caso di conflitto, emette richiesta di coordinamento al
   committente PRIMA di sigillare.
3. Non assume "decidi tu" come override del gate di approvazione
   esplicita (errore già accettato in §3 della risposta consulente).

## Tracciabilità

- File: questo addendum
- Commit: TBD (gate 24/05 21:30)
- Tag: rimane `s1-prereg-v8` (cumulativo), tag aggiuntivo `s1-gate-24may`
  da emettere al completamento del pacchetto gate 24/05.

SHA256 di questo file: (calcolato post-write)
