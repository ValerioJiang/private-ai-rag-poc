# Backlog operativo

Scomposizione di [PLAN.md](PLAN.md) in attività da board. Ogni voce è pensata
per stare in 30–120 minuti.

**Priorità:** `M` = indispensabile alla consegna · `S` = atteso, migliora
nettamente la valutazione · `C` = opzionale, primo candidato al taglio.

---

## Raccomandazione preliminare: prima lo spike, poi i modelli

L'ordine naturale (modelli → admin → ingestione → RAG) ha un difetto: si
spenderebbero i primi due giorni sull'admin e solo il sabato si scoprirebbe se
pgvector, gli embedding e Ollama si parlano davvero. Il rischio tecnico
resterebbe concentrato **alla fine**, cioè nel punto in cui non c'è più tempo
per assorbirlo.

Per questo la prima attività dopo lo scaffolding è uno **spike monolitico**: un
unico script, valori scritti a mano, che ingerisce un PDF e risponde a una
domanda. Serve a scoprire subito la dimensione degli embedding, i tempi reali di
Ollama sulla macchina e le asperità di `PGVector`. Si butta via appena i modelli
esistono, ma trasforma le fasi successive in lavoro di strutturazione di
qualcosa che già funziona.

---

## P0 — Scaffolding

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-01 | `git init`, `.gitignore`, README iniziale, primo commit | M | 30m | — |
| T-02 | `docker-compose`: pgvector (Ollama resta sull'host, cfr. ARCHITECTURE §2); `Dockerfile` applicativo | M | 1h | T-01 |
| T-03 | Dipendenze pinnate (Django 6, DRF, langchain-core/-ollama/-postgres/-text-splitters, PyMuPDF, psycopg) — **niente torch** | M | 45m | T-01 |
| T-04 | Progetto Django, settings suddivisi per ambiente, app `rag`, `/health` | M | 1h | T-03 |
| T-05 | Pull di `qwen2.5:7b-instruct`, verifica di `ChatOllama` dalla shell Django | M | 30m | T-02 |
| **T-06** | **Spike end-to-end monouso**: PDF → chunk → embedding → pgvector → domanda → risposta, tutto scritto a mano | **M** | **2h** | T-04, T-05 |

**Verifica di fase:** una domanda su un PDF reale riceve una risposta sensata,
per quanto il codice sia da buttare.

**Stato: completata il 24/07/2026.** T-01 → T-06 chiuse. Verifica di fase
superata: lo spike risponde correttamente su `samples/manuale-dipendenti.pdf` e
dichiara di non sapere quando l'informazione non è nel documento. Dati raccolti
sul campo — embedding a **1024** dimensioni, `PGVector.from_documents()`
funzionante con `langchain-core` 1.x, tempi a freddo e a caldo — in
[`plans/2026-07-23-1800-P0-scaffolding-plan-report.md`](plans/2026-07-23-1800-P0-scaffolding-plan-report.md).

## P1 — Modelli e admin

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-07 | Modelli dei profili: `LLMProfile`, `EmbeddingProfile`, `ChunkingProfile`, `RetrievalProfile`, `PromptTemplate` + vincoli DB | M | 1h30 | T-04 |
| T-08 | `KnowledgeBase` e `RagPipeline` con `on_delete` come da ARCHITECTURE §6.4 | M | 1h | T-07 |
| T-09 | `Document` e `DocumentChunk` con macchina a stati, snapshot dei profili e `index_fingerprint` (cfr. ARCHITECTURE §6.2) | M | 1h | T-08 |
| T-10 | `QueryLog` e `RetrievedChunk` | S | 45m | T-08 |
| T-11 | Admin dei profili: fieldset, validazione in `clean()`, `list_display` | M | 1h30 | T-07 |
| T-12 | Admin di `KnowledgeBase`, `RagPipeline`, `Document` con inline dei chunk | M | 1h | T-09 |
| T-13 | Migrazione dati: configurazione predefinita funzionante (RF-26) | M | 45m | T-08 |

**Verifica di fase:** admin navigabile, configurazione predefinita presente,
nessun parametro salvabile in stato incoerente.

**Stato: completata il 24/07/2026.** T-07 → T-13 chiuse. Verifica di fase
superata: l'admin è navigabile e riservato (accesso anonimo respinto al login,
RF-30), la configurazione predefinita è presente — **sette** righe create da
`migrate`, un solo default per `LLMProfile` e per `RagPipeline` (RF-26) — e una
configurazione incoerente non è salvabile nemmeno **dal form dell'admin** (RF-24,
verificato via POST oltre che con `full_clean()`). Undici modelli, quattro
migrazioni applicate. Debiti accertati verso P2 (deduplica nel servizio di
ingestione, hook di cancellazione dei vettori, collezione `spike` da rimuovere) in
[`plans/2026-07-24-1834-P1-plan-report.md`](plans/2026-07-24-1834-P1-plan-report.md).

## P2 — Ingestione

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-14 | Loader PyMuPDF **diretto** (no `langchain-community`, cfr. ARCHITECTURE §7.10) con numero di pagina; errore esplicito su PDF senza testo (RF-10). Parte da `load_pdf()` dello spike | M | 1h | T-09 |
| T-15 | `factories.get_splitter()` da `ChunkingProfile` | M | 45m | T-07 |
| T-16 | `factories.get_embeddings()` e `get_vectorstore()` da `EmbeddingProfile` / `KnowledgeBase` | M | 1h | T-08 |
| T-17 | `services/ingestion.py`: orchestrazione, transizioni di stato, transazione, riconciliazione chunk/vettori | M | 1h30 | T-14, T-15, T-16 |
| T-18 | Comando `manage.py ingest <path>` | S | 30m | T-17 |
| T-19 | Azione admin «reindicizza» + segnalazione documenti disallineati (RF-25) | S | 1h | T-17 |
| T-20 | Deduplica per checksum (RF-09) ed eliminazione a cascata dei vettori (RF-08) | S | 45m | T-17 |

**Verifica di fase:** upload dall'admin → stato *indicizzato*, chunk visibili con
pagina e ordinale.

## P3 — Retrieval e generazione

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-21 | `factories.get_llm()` da `LLMProfile` + cache in-process invalidata da `post_save` (RF-22) | M | 1h30 | T-07 |
| T-22 | `factories.get_retriever()` da `RetrievalProfile` (similarity / MMR / soglia) | M | 45m | T-16 |
| T-23 | Catena LCEL con prompt da `PromptTemplate` e formattazione del contesto | M | 1h30 | T-21, T-22 |
| T-24 | Costruzione delle fonti (documento, pagina, estratto, score) — RF-13 | M | 1h | T-23 |
| T-25 | Comportamento «non dispongo dell'informazione» sotto soglia (RF-14, CA-4) | S | 1h | T-23 |
| T-26 | Persistenza di `QueryLog` e `RetrievedChunk` con tempi separati | S | 45m | T-24 |
| T-27 | Comando `manage.py ask "<domanda>"` | S | 30m | T-23 |

**Verifica di fase:** `manage.py ask` risponde citando le fonti; cambiare la
temperatura dall'admin modifica la risposta senza riavvio.

## P4 — API

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-28 | Serializer e `POST /api/documents/` (multipart) | M | 1h | T-17 |
| T-29 | `GET /api/documents/` e `GET /api/documents/{id}/` con stato | M | 45m | T-28 |
| T-30 | `POST /api/ask/` con selezione della pipeline (RF-15) | M | 1h | T-24 |
| T-31 | `GET /api/pipelines/` e autenticazione degli endpoint | S | 45m | T-30 |

**Verifica di fase:** flusso completo via `curl`, dall'upload alla risposta.

## P5 — Asincronia e rifiniture

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-32 | `django-tasks` + `django-tasks-db` (due app in `INSTALLED_APPS`, 19 migrazioni), ingestione asincrona, `db_worker` nel compose | S | 2h | T-17 |
| T-33 | Pagina «playground» nell'admin per provare una pipeline inline | C | 1h30 | T-30 |
| T-34 | Gestione errori uniforme e logging strutturato | S | 1h | T-30 |
| T-35 | Punto d'aggancio Langfuse dietro flag, spento di default | C | 1h | T-26 |

## P6 — Test e consegna

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-36 | Test: segmentazione e factory che rispettano la configurazione | S | 1h30 | T-21 |
| T-37 | Test: macchina a stati dell'ingestione, inclusi i casi di errore | S | 1h | T-17 |
| T-38 | Test: `POST /api/ask/` con LLM mockato | S | 1h | T-30 |
| T-39 | README: avvio, prova guidata, criteri di accettazione | M | 1h30 | — |
| T-40 | Revisione finale di ARCHITECTURE e REQUIREMENTS, limiti aggiornati | M | 1h | — |
| T-41 | PDF di esempio + script di dimostrazione riproducibile | S | 45m | T-30 |
| T-42 | Prova da zero su ambiente pulito (CA-1) | M | 1h | tutto |
| T-43 | Prova **a rete staccata**: upload + domanda + risposta devono funzionare. È la dimostrazione di RNF-01 (ARCHITECTURE §9), da riportare nel README | M | 30m | T-42 |

---

## Distribuzione nel tempo

Stima totale: **44 ore**, così ripartite: `M` 28,25 h · `S` 13,25 h · `C` 2,5 h.

Le sole attività indispensabili stanno quindi in poco più di 28 ore.

| Giorno | Obiettivo | Attività |
|---|---|---|
| **Gio 23** (pomeriggio/sera) | L'ambiente gira e il RAG funziona in forma grezza | T-01 → T-06 |
| **Ven 24** | Configurazione modellata e governabile dall'admin | T-07 → T-13, avvio T-14 |
| **Sab 25** | Ingestione e catena guidate dalla configurazione | T-14 → T-27 |
| **Dom 26** | API, asincronia, test | T-28 → T-38 |
| **Lun 27** (entro 9:30) | Documentazione e verifica finale | T-39 → T-42 |

Meglio anticipare T-39 e T-40 a sabato sera: la documentazione scritta di fretta
la domenica notte è la parte che si nota di più.

## Se il tempo disponibile è inferiore

Con circa 15 ore effettive restano realizzabili tutte le `M` più poche `S`. In
quel caso si tagliano, **in quest'ordine**: T-35, T-33, T-41, T-38, T-32
(l'ingestione resta sincrona, dichiarandolo come limite noto), T-19, T-25.

Un limite dichiarato con consapevolezza nel README pesa molto meno di una
funzionalità presente ma non funzionante.
