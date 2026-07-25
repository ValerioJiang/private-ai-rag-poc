# Piano di lavoro — RAG Django + LangChain + LLM locale

Deadline: **lunedì 27, ore 9:30**. Oggi: giovedì 23.

## Decisioni prese

| Componente | Scelta | Motivazione (da riportare nel README) |
|---|---|---|
| LLM | Ollama + `qwen2.5:7b-instruct` | Locale al 100%, nessun dato esce dalla macchina. Modello selezionabile per nome dall'admin senza riavvio. Buon supporto multilingua (IT). |
| Embedding | `bge-m3` via Ollama | I documenti sono in italiano: serve un modello multilingua. Passando da Ollama, il progetto non dipende da torch/sentence-transformers e l'inferenza resta in un solo servizio. 1024 dimensioni. |
| Vector store | Postgres + pgvector (`langchain_postgres.PGVector`) | Un solo datastore per dati applicativi e vettori; coerenza transazionale tra `Document` e i suoi chunk. |
| PDF | PyMuPDF usato **direttamente** (`fitz`), non via `PyMuPDFLoader` | Veloce, conserva il numero di pagina → necessario per le citazioni. Il loader di LangChain richiederebbe `langchain-community`, cfr. ARCHITECTURE §7.10. |
| API | Django REST Framework | La browsable API funge anche da interfaccia di prova. |
| Async | `django-tasks` **0.12.0** + `django-tasks-db` **0.12.0** | L'ingestione di un PDF lungo non deve bloccare un worker HTTP. Coda su Postgres: nessun servizio con stato in più, e l'API è agnostica rispetto al backend, quindi passare a Celery è una voce di settings. **Realizzato in P5:** `POST /api/documents/` da 14,53 s a **0,94 s** con **202 Accepted**; il lavoro passa a `manage.py db_worker`. **Note:** `django.tasks` di Django 6 offre solo i backend `immediate` e `dummy`, quindi il backend DB arriva comunque dal backport; e dalla **0.12.0** i backend sono usciti da `django-tasks` in pacchetti separati, da cui il vincolo `>=0.12` e le **19** migrazioni di `django_tasks_database`. Con `TASKS_BACKEND=django_tasks.backends.immediate.ImmediateBackend` il progetto gira senza worker. Cfr. ARCHITECTURE §7.5. |
| Cache | **Dizionario di modulo** in `factories.py` | Gli oggetti memorizzati sono vivi e non serializzabili. **Corretto in P3:** era previsto `LocMemCache`, che però serializza con `pickle` anche restando in-process — verificato, `cache.set()` solleva «cannot pickle `_thread.RLock`» sia per `ChatOllama` sia per `PGVector`, che contengono un client httpx e un engine SQLAlchemy. Non è la catena a essere memorizzata, ma le sue **due parti costose** (LLM e vector store): `build_chain()` resta non cachata e rilegge la configurazione a ogni richiesta, che è ciò che rende dimostrabile RF-22. |

## Principio architetturale portante

Ogni parametro del sistema è una **riga di database**, non una costante nel codice.
Le catene LangChain vengono costruite a runtime da quelle righe da
`rag/services/factories.py`. È questa la risposta al requisito «modificare il
comportamento dall'admin senza mettere mano al codice».

A garantirlo è la **chiave** della cache, che contiene i valori della
configurazione e non solo l'id, quindi cambia da sé a ogni modifica — anche in
un processo che il `post_save` non lo riceve mai. Il signal libera memoria e
rende l'effetto immediato dove si è salvato; cfr. ARCHITECTURE §3.

## Entità

**Profili di configurazione (componibili)**
- `LLMProfile` — provider, base_url, model_name, temperature, top_p, top_k, max_tokens, timeout, is_default
- `EmbeddingProfile` — provider, model_name, dimension, normalize
- `ChunkingProfile` — splitter (recursive/token), chunk_size, chunk_overlap, separators
- `RetrievalProfile` — search_type (similarity/mmr/threshold), top_k, fetch_k, lambda_mult, score_threshold
- `PromptTemplate` — testo con `{context}` / `{question}`, validato in `clean()`

**Dominio**
- `KnowledgeBase` — collection name + FK `EmbeddingProfile`
- `RagPipeline` — aggregatore: FK a tutti i profili + KB, `is_active`
- `Document` — file, KB, stato (`pending → processing → indexed | failed`), page_count, checksum, error_message
- `DocumentChunk` — FK doc, page, ordinal, text, vector_id
- `QueryLog` — domanda, risposta, pipeline, chunk recuperati + score, **tre tempi separati** (`retrieval_ms`, `generation_ms`, `latency_ms`) ed `error`

## Fasi

Ogni fase termina con qualcosa di dimostrabile.

### P0 — Scaffolding (~2h)
Progetto Django, app `rag`, docker-compose (pgvector; Ollama resta sull'host),
dipendenze pinnate, settings splittati, endpoint `/health`.
**Demo:** `ChatOllama` risponde da una shell Django.

### P1 — Modelli + admin (~4h)
Tutte le entità, migrazioni, `ModelAdmin` con fieldsets/inline/list_display,
data migration che crea una pipeline di default.
**Demo:** admin completo e navigabile.

### P2 — Ingestione (~4h)
`ingest_document(doc)`: load → split (secondo `ChunkingProfile`) → embed → upsert.
Transizioni di stato, cattura errori. Admin action «Re-index selected» +
`manage.py ingest <path>`.
**Demo:** upload di un PDF dall'admin, i chunk compaiono.

### P3 — Retrieval + generazione (~4h)
Factory layer, catena LCEL, costruzione citazioni, scrittura `QueryLog`.
La catena è `prompt | llm | parser`: il **recupero resta fuori**, prima di essa,
perché `QueryLog` vuole `retrieval_ms` e `generation_ms` separati.
**Demo:** `manage.py ask "..."` restituisce risposta + fonti.

### P4 — API (~3h)
`POST /api/documents/`, `GET /api/documents/{id}/`, `POST /api/ask/`,
`GET /api/pipelines/`.
**Demo:** flusso completo via curl.

### P5 — Async + rifiniture (~3h)
Ingestione spostata su `django-tasks` con worker `db_worker` (T-32) e gestione
uniforme degli errori (T-34): un solo `EXCEPTION_HANDLER` DRF che risponde JSON
anche sui guasti inattesi, 404 in italiano, file rimosso da `MEDIA_ROOT` con il
documento, pid nei log, voce «coda» in `/health`.

**Perimetro effettivamente svolto:** T-32 e T-34. **Tagliate** la pagina
«playground» nell'admin (T-33) e il flag `LANGFUSE_ENABLED` / aggancio Langfuse
(T-35), nell'ordine di taglio che il backlog fissava. La ragione è di priorità,
non di difficoltà: T-32 chiudeva un requisito **dichiarato non soddisfatto**
(RNF-03) e T-34 debiti già accertati nel report di P4, mentre un playground e un
flag di tracing spento non chiudono nulla, e tutte le attività `M` rimaste stanno
in P6.

### P6 — Test + documentazione (~3h)
Pytest: chunking, la factory rispetta la config, macchina a stati
dell'ingestione, `/ask` con LLM mockato. README + `ARCHITECTURE.md` con i
compromessi.

**Perimetro effettivamente svolto: T-36 → T-41; T-42 e T-43 in attesa
dell'operatore.** Nessun taglio in questa fase.

La suite è di **29 test in 10,44 s** su tre file — 11 su segmentazione e factory,
9 sulla macchina a stati dell'ingestione, 9 su `POST /api/ask/` — e passa
identica col client di inferenza puntato su una **porta chiusa** (29 passed in
10,39 s): è la prova che nessun test tocca la rete, e la conseguenza diretta di
avere un solo punto che costruisce oggetti LangChain. Coperto RNF-05, abilitato
CA-10. Due dipendenze nuove, `pytest` e `pytest-django`, nessuna delle quali
parla con la rete.

Fuori dai test, la fase ha chiuso l'ultima costante di comportamento nel codice:
`LUNGHEZZA_ESTRATTO = 300` è diventata `RetrievalProfile.excerpt_length`
(migrazione `0005`, additiva, stesso predefinito), completando **RF-22**. T-41 ha
prodotto `scripts/dimostrazione.ps1`, che percorre il flusso completo
cronometrando ogni passo: 211,12 s a modello freddo, 18,16 s alla seconda
esecuzione consecutiva. T-39 e T-40 hanno riscritto il README come documento di
consegna — prova guidata, criteri di accettazione con l'esito di ciascuno, test,
limiti noti — e riallineato gli altri documenti.

**Un rilievo dichiarato e non addolcito:** in configurazione predefinita CA-4 non
lo regge la soglia ma il prompt di sistema, perché `score_threshold` filtra solo
nella strategia `similarity_score_threshold` e la pipeline predefinita usa
`similarity`. Cfr. ARCHITECTURE §7.7.

**T-42** (prova da zero su ambiente pulito, CA-1) e **T-43** (prova a rete
staccata, RNF-01 e CA-9) richiedono l'operatore e non sono ancora state
eseguite: finché non lo sono, quei due criteri restano senza esito, e i posti
dove scriverlo sono segnati nel README, in `REQUIREMENTS.md` §7 e in
`ARCHITECTURE.md` §9.

## Fuori scope (da dichiarare nel README come limiti noti)

Reranker, ricerca ibrida BM25+vettoriale, streaming SSE, memoria
conversazionale, multi-tenancy, ACL a livello di chunk.
