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

**Stato: completata il 24/07/2026.** T-14 → T-20 chiuse. Verifica di fase
superata nei suoi nove punti, da (a) a (i): l'upload dall'admin porta il
documento a *indicizzato* con pagine e segmenti in elenco e i chunk ispezionabili
con ordinale, pagina, caratteri ed estratto (CA-2); duplicato e PDF illeggibile
sono respinti con un motivo leggibile senza compromettere l'admin (RF-09, CA-8);
la cancellazione porta via anche i vettori (RF-08). Coperti RF-01 → RF-10, RF-19,
RF-25, RF-28, RF-29 e RNF-04; abilitati CA-2 e CA-8. Nessuna migrazione, nessuna
dipendenza nuova. Limite dell'esecuzione, dichiarato: senza un browser a
disposizione la verifica è stata replicata con `django.test.Client`, che percorre
la stessa pila (URLconf, autenticazione, `ModelAdmin`, form, template) ma non il
rendering visivo. Debiti accertati verso le fasi seguenti: la riconciliazione fra
`DocumentChunk` e pgvector avviene in un punto solo ma **non** dentro un'unica
transazione — le due metà dello schema stanno su connessioni distinte — e
l'ingestione resta **sincrona** (~0,8–1 s per segmento più ~1 s di sonda fissa,
fino a ~18 s a freddo), quindi RNF-03 non è soddisfatto finché resta aperta T-32.
La collezione `spike` è stata rimossa; `scripts/spike_rag.py` è stato cancellato
alla chiusura di P3, quando `manage.py ask` l'ha sostituito. Dettaglio in
[`plans/2026-07-24-2259-P2-plan-report.md`](plans/2026-07-24-2259-P2-plan-report.md).

## P3 — Retrieval e generazione

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-21 | `factories.get_llm()` da `LLMProfile` + cache in-process la cui **chiave contiene i valori** della configurazione, con `post_save` a liberare memoria (RF-22) | M | 1h30 | T-07 |
| T-22 | `query.esegui_ricerca()` da `RetrievalProfile` (similarity / MMR / soglia). **Non** `factories.get_retriever()`: un `VectorStoreRetriever` perde i punteggi, che RF-13 e RF-16 richiedono | M | 45m | T-16 |
| T-23 | Catena LCEL con prompt da `PromptTemplate` e formattazione del contesto | M | 1h30 | T-21, T-22 |
| T-24 | Costruzione delle fonti (documento, pagina, estratto, score) — RF-13 | M | 1h | T-23 |
| T-25 | Comportamento «non dispongo dell'informazione» sotto soglia (RF-14, CA-4) | S | 1h | T-23 |
| T-26 | Persistenza di `QueryLog` e `RetrievedChunk` con tempi separati | S | 45m | T-24 |
| T-27 | Comando `manage.py ask "<domanda>"` | S | 30m | T-23 |

**Verifica di fase:** `manage.py ask` risponde citando le fonti; cambiare la
temperatura dall'admin modifica la risposta senza riavvio.

**Stato: completata il 25/07/2026.** T-21 → T-27 chiuse. Verifica di fase
superata nei suoi dieci punti, da (a) a (j): `manage.py ask` risponde citando
documento, pagina, estratto e punteggio (RF-13, CA-3); una domanda fuori tema
ottiene la dichiarazione di non conoscenza (RF-14, CA-4) e, sotto soglia,
**senza nemmeno interrogare l'LLM** (`generation_ms = 0`); ridurre `top_k`
dall'admin riduce le fonti (CA-6) e due pipeline sulla stessa base di conoscenza
danno risposte diverse (CA-7). Il punto centrale della traccia è stato
verificato col criterio stretto: cambiata la temperatura dall'admin su un
`runserver` in un **processo separato**, a temperatura 0 due esecuzioni della
stessa domanda danno lo stesso testo, a 1.8 danno testi diversi — senza riavvio
(RF-22, CA-5). Coperti RF-11 → RF-16, RF-21 → RF-23, RF-28. Nessuna migrazione,
nessuna dipendenza nuova.

Due scostamenti dal piano, entrambi imposti da una misura e non da un'opinione:
T-22 è una factory di **strategia** e non di oggetto (cfr. la riga qui sopra), e
la clausola attorno a `invoke()` è `except (OSError, httpx.TransportError)`
perché con Ollama spento `ChatOllama` solleva `httpx.ConnectError`, che **non**
discende da `OSError` — un `except OSError` da solo avrebbe lasciato sfuggire
proprio il caso per cui esisteva. Una verifica incrociata a fase chiusa ha poi
corretto due difetti che nessuna verifica di fase copriva: `is_active` era
aggirabile passando la pipeline come istanza, e `--json` non produceva
un'uscita analizzabile. Limite dell'esecuzione, dichiarato: nessun browser
interattivo, quindi l'admin è stato pilotato via HTTP con login, CSRF e
sessione, ma senza rendering visivo. Dettaglio in
[`plans/2026-07-25-0051-P3-plan-report.md`](plans/2026-07-25-0051-P3-plan-report.md).

## P4 — API

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-28 | Serializer e `POST /api/documents/` (multipart) | M | 1h | T-17 |
| T-29 | `GET /api/documents/` e `GET /api/documents/{id}/` con stato | M | 45m | T-28 |
| T-30 | `POST /api/ask/` con selezione della pipeline (RF-15) | M | 1h | T-24 |
| T-31 | `GET /api/pipelines/` e autenticazione degli endpoint | S | 45m | T-30 |

**Verifica di fase:** flusso completo via `curl`, dall'upload alla risposta.

**Stato: completata il 25/07/2026.** T-28 → T-31 chiuse. Verifica di fase
superata nei suoi dieci punti, da (a) a (j), e questa volta con `curl` vero
contro un `runserver` vero: è il limite che P2 e P3 avevano dichiarato — la
verifica passava per il test client, che non tocca la rete — e P4 lo chiude.
L'upload porta il documento a *indicizzato* in 14,5 s a freddo e 4,3 s a caldo
(RF-01); lo stesso file è respinto con 409 **senza lasciare file orfani**
(RF-09); `POST /api/ask/` cita documento, pagina, estratto e punteggio (RF-13,
CA-3) e una domanda fuori tema riceve la dichiarazione di non conoscenza
(RF-14, CA-4). Coperti RF-01, RF-06, RF-09, RF-11 → RF-16, RF-27, RF-30.
Nessuna migrazione, nessuna dipendenza nuova.

Il punto centrale della traccia è stato verificato in una forma **più forte** che
in P3: cambiando `top_k` da un altro processo con il server acceso — PID
verificato identico prima, durante e dopo — le fonti sono passate da **4 a 1 e
di nuovo a 4**, senza riavvio (RF-22, CA-6). Il ritorno al valore iniziale
esclude che il numero dipendesse dai segmenti disponibili. Due pipeline che
differiscono **solo** per il prompt danno risposte diverse sulle stesse fonti
(CA-7), e l'ordine degli autenticatori — `BasicAuthentication` prima di
`SessionAuthentication` — è stato verificato sulla causa e non sull'esito: due
viste identiche salvo quell'ordine danno 401 con `WWW-Authenticate` la prima e
403 senza header la seconda.

Debiti accertati, tutti verso P6: `GET /api/documents/{id}/` risponde **in
inglese** su id inesistente («No Document matches the given query.») perché
`get_object_or_404` non passa da `gettext` e DRF ne propaga l'argomento
scavalcando il proprio «Non trovato.»; cancellare un `Document` rimuove i
vettori ma **non** il file da `MEDIA_ROOT`, che `FileField` non tocca; e la
prima richiesta di ogni processo resta a freddo — misurati **30,2 s** su una
sola richiesta, che è il limite inferiore per i timeout dei client. Dettaglio in
[`plans/2026-07-25-0900-P4-plan-report.md`](plans/2026-07-25-0900-P4-plan-report.md).

## P5 — Asincronia e rifiniture

| ID | Attività | Pri | Stima | Dipende da |
|---|---|---|---|---|
| T-32 | `django-tasks` + `django-tasks-db` (due app in `INSTALLED_APPS`, 19 migrazioni), ingestione asincrona, `db_worker` nel compose | S | 2h | T-17 |
| T-33 | Pagina «playground» nell'admin per provare una pipeline inline | C | 1h30 | T-30 |
| T-34 | Gestione errori uniforme e logging strutturato | S | 1h | T-30 |
| T-35 | Punto d'aggancio Langfuse dietro flag, spento di default | C | 1h | T-26 |

**Verifica di fase** (il backlog non ne scriveva una: se l'è data il piano):
un upload via `curl` risponde in meno di un secondo con **202** e stato «in
attesa», un worker separato porta il documento a «indicizzato», e
`GET /api/documents/{id}/` lo mostra — più il **controllo negativo**, cioè che a
worker spento il documento **resti** «in attesa» invece di fallire in silenzio.

**Stato: completata il 25/07/2026.** **T-32 e T-34 chiuse; T-33 e T-35
tagliate.** Il taglio segue l'ordine che questo stesso backlog fissa più sotto
(«si tagliano, in quest'ordine: T-35, T-33, …») e la ragione è di priorità: T-32
chiudeva **RNF-03**, dichiarato non soddisfatto dalla chiusura di P2, e T-34 i
tre debiti accertati nel report di P4, mentre un playground e un flag di tracing
spento non chiudono alcun requisito. Sono le due sole attività `C` di P5, e tutte
le attività `M` rimaste stanno in P6.

Verifica di fase superata nei suoi otto punti, da 4.1 a 4.8, con `curl` vero
contro **tre processi** — `runserver --noreload`, `db_worker --no-reload` e il
client. La misura che giustifica la fase: `POST /api/documents/` rispondeva
**14,53 s** a freddo e **4,25 s** a caldo, e ora risponde **202** in **0,94 s**
(di cui ~0,9 s di sovraccarico costante del client, misurato anche sul 409 a
0,92 s); il worker ha poi indicizzato lo stesso documento in **12,4 s** a freddo
e **2,7 s** a caldo. Il **controllo negativo** è passato: a worker spento il
documento è ancora `pending` dopo 15 s e `/health` dichiara «1 in attesa»;
riacceso il worker, viene preso. Lo stato «in elaborazione» è stato **osservato**
con un `GET` ogni 150 ms (`pending → processing → indexed`), non dedotto. Un PDF
senza testo dà **202** e poi `failed` con il motivo (RF-10 dopo il cambio di
contratto), deduplica (409) e autenticazione (401 con `WWW-Authenticate`,
`/health` anonimo) non sono regredite, e `POST /api/ask/` recupera dal server ciò
che il **worker** ha scritto, citando fonti con documento, pagina, estratto e
punteggio (RF-13, CA-3). RF-22 è stato verificato nella forma più forte finora:
`top_k` cambiato da un **terzo** processo porta le fonti da **4 a 2 e di nuovo a
4** con i pid di server *e* worker invariati — nessuno dei due si riavvia.

Coperti **RNF-03** e il completamento di **RNF-04** e **RF-08** (la cancellazione
porta via anche il file da `MEDIA_ROOT`, che `FileField` non tocca). Ripetuti
senza regressioni RF-01, RF-06, RF-07, RF-09, RF-10, RF-13, RF-14, RF-22, RF-25,
RF-27, RF-29. **Nessuna migrazione dell'app `rag`**; le **19** migrazioni
`django_tasks_database` sono di terze parti. **Due** dipendenze nuove di primo
livello — `django-tasks==0.12.0` e `django-tasks-db==0.12.0` — più una
transitiva, `django-stubs-ext==6.0.7`; nessuna parla con la rete (RNF-01).

**Un cambio di contratto dell'API**, il solo della fase: `POST /api/documents/`
risponde **202 Accepted** invece di 201 e **il 422 non esiste più**, perché un
PDF illeggibile è scoperto dal worker quando la risposta è già partita. La
condizione resta osservabile su `GET /api/documents/{id}/`.

Debiti e limiti dichiarati, verso P6: nessun retry automatico dei task falliti
(si usa «Reindicizza»); nessun lucchetto contro il doppio accodamento; il worker
fa polling con intervallo di 1 s, e al **primo task di ogni processo** paga il
caricamento del modello di embedding (12,4 s misurati contro 2,7 s a caldo);
sostituire il file di un documento esistente lascia il precedente in
`MEDIA_ROOT`; l'admin di `django_tasks_db` è di terze parti e **in inglese**; la
tabella dei task cresce e si pota con `manage.py prune_db_task_results`.
Dettaglio in
[`plans/2026-07-25-1958-P5-plan-report.md`](plans/2026-07-25-1958-P5-plan-report.md).

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

**Applicato ai primi due nomi alla chiusura di P5, il 25/07/2026:** T-35 e T-33
sono **tagliate**, per la ragione scritta nella sezione di P5. Il taglio non è
stato indolore in un punto solo, ed è dichiarato: senza T-33 non esiste modo di
provare una pipeline dall'interfaccia senza passare da `POST /api/ask/` o da
`manage.py ask`. Da T-32 in poi l'elenco resta invariato: l'attività è stata
**svolta**, non tagliata, quindi l'ingestione è asincrona e il limite noto non
serve più.

Un limite dichiarato con consapevolezza nel README pesa molto meno di una
funzionalità presente ma non funzionante.
