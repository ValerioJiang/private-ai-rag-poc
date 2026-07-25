# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Backend Django che implementa un sistema RAG su PDF con **generazione ed
embedding interamente locali** (Ollama sull'host). Prova tecnica con consegna a
scadenza: la documentazione (`REQUIREMENTS.md`, `ARCHITECTURE.md`, `PLAN.md`,
`BACKLOG.md`) è essa stessa parte della consegna e va tenuta allineata al codice.

Lingua del progetto: **italiano**, ovunque — docstring, commenti, messaggi
d'errore, nomi di funzioni e variabili di dominio (`rispondi`, `esegui_ricerca`,
`SegmentoRecuperato`), messaggi di commit. I nomi dei campi dei modelli restano
in inglese (`chunk_size`, `is_default`), con `verbose_name` in italiano.

## Comandi

Windows, virtualenv in `.venv`. Il database gira in Docker sulla porta **5434**
(non la 5432); Ollama gira **nativamente sull'host**, mai in container.

```powershell
docker compose up -d db                     # PostgreSQL + pgvector
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
.venv\Scripts\python.exe manage.py db_worker      # secondo processo, da P5
.venv\Scripts\python.exe manage.py ingest samples/manuale-dipendenti.pdf
.venv\Scripts\python.exe manage.py ask "Quanti giorni di ferie si maturano?"
.venv\Scripts\python.exe manage.py ask "..." --pipeline "Pipeline predefinita" --json
```

I processi sono **due** da P5: il server accoda, il worker indicizza. Senza
worker i documenti restano «In attesa» a tempo indeterminato — non è un guasto, e
`/health` lo dichiara sotto la voce «coda». Per girarne uno solo:
`TASKS_BACKEND=django_tasks.backends.immediate.ImmediateBackend` in `.env`
riporta l'ingestione in linea, col comportamento di P4.

Verifica dei presupposti prima di qualunque lavoro: `GET /health` riporta lo
stato di database, estensione `vector`, Ollama e coda dei task; `ollama list`
deve mostrare `qwen2.5:7b-instruct` e `bge-m3`.

**Test:** da P6 esistono, in `rag/tests/` — **29 test in ~10,4 s**, con `pytest`
e `pytest-django`, configurati in `pytest.ini`.

```powershell
docker compose up -d db
.venv\Scripts\python.exe -m pytest -q
```

Richiedono **PostgreSQL** (la migrazione `0001` fa `CREATE EXTENSION vector`) e
**non** Ollama: tutto ciò che parla con la rete passa da `factories.py`, e i test
sostituiscono quei nomi. La controprova è misurata — con
`$env:OLLAMA_BASE_URL = 'http://127.0.0.1:1'` la suite passa identica. Sono in
stile pytest, quindi **`manage.py test` non li raccoglie**. `pytest.ini` non ha
`--reuse-db` di proposito: un database riusato non applicherebbe una migrazione
nuova. Restano fuori dalla suite le verifiche end-to-end con Ollama vero, che
sono quelle descritte in ogni piano di fase — comandi reali su dati reali, con
l'output nel report — e `scripts/dimostrazione.ps1`, che le percorre tutte.

`requirements.txt` è generato con `pip freeze` da `requirements.in` dopo
un'installazione reale: modificare `requirements.in`, non il `.txt` a mano.

## Architettura

### Il principio portante: nessun parametro è una costante nel codice

Ogni parametro di comportamento — modello, temperatura, `chunk_size`, strategia
di retrieval, prompt — è una **riga di database** modificabile dall'admin.
`config/settings/` contiene solo l'indirizzo del servizio di inferenza. Qualsiasi
modifica che introduca un valore di comportamento nel codice o nei settings
viola il requisito centrale della traccia (RF-22).

`rag/services/factories.py` è la **cerniera**: l'unico punto che traduce profili
in oggetti LangChain. Tutto il resto riceve oggetti già costruiti.

`build_chain()` **non è in cache** di proposito: rilegge la configurazione a ogni
richiesta. Sono memorizzate le due sole parti costose, LLM e vector store, in un
**dizionario di modulo** — non `django.core.cache`, che serializza con pickle e
fallisce su questi oggetti (client httpx, engine SQLAlchemy). La correttezza di
RF-22 la garantisce la **chiave**, che contiene i *valori* della configurazione
(`updated_at`, `index_fingerprint()`) e non solo l'id: cambia da sé anche in un
processo che il `post_save` non lo riceve mai. Il receiver di `rag/signals.py`
libera memoria, non è la garanzia.

### Le due metà dello schema

Le tabelle `langchain_pg_collection` e `langchain_pg_embedding` sono di
`langchain_postgres` e stanno **fuori dalle migrazioni Django**, su una
connessione SQLAlchemy distinta: nessun `transaction.atomic()` le comprende
entrambe. Il ponte è `DocumentChunk.vector_id`, deterministico
(`"<document_id>:<ordinal>"`) — è ciò che rende idempotente la reindicizzazione e
possibile cancellare i vettori a righe Django già sparite.

Da qui due invarianti da non invertire:

- **si scrive prima in pgvector, poi in Django.** L'ordine inverso lascerebbe
  chunk che puntano a vettori inesistenti: guasto silenzioso e permanente. Nel
  verso scelto restano al più vettori orfani, sovrascritti dalla prossima
  esecuzione;
- `get_vectorstore()` ha **effetti collaterali**: `PGVector.__post_init__`
  esegue DDL a ogni costruzione. Si costruisce una volta per ingestione, mai
  dentro un ciclo sui lotti.

### Ingestione e interrogazione

`ingestion.py` e `query.py` sono gemelli e hanno la stessa forma: un involucro
che **persiste l'esito, riuscito o fallito**, attorno a un corpo che non se ne
occupa. Documento fallito → stato `failed` con `error_message`; interrogazione
fallita → `QueryLog` con `error`. Un fallimento che non lascia traccia rende
inutile proprio ciò che servirebbe (RNF-04).

Nel percorso di lettura il **recupero sta fuori dalla catena LCEL**
(`prompt | llm | parser`), prima di essa, perché `QueryLog` vuole `retrieval_ms`
e `generation_ms` separati. Non si usa `as_retriever()`: perderebbe i punteggi
richiesti da RF-13/RF-16.

Il punteggio che circola nel sistema è la **rilevanza** (`1 - distanza`, più alto
= più pertinente), convertita in un solo punto — `rilevanza()`. La distanza
grezza di pgvector non esce mai da lì. Zero segmenti recuperati → dichiarazione
di non conoscenza **senza interrogare l'LLM** (RF-14).

### La coda: un solo punto di accodamento, il task riceve un intero

`rag/tasks.py` esporta **una** funzione — `accoda_indicizzazione(documento)` —
che porta il documento a `pending`, azzera `error_message` e accoda. Gli inneschi
sono quattro (admin, azione «Reindicizza», `POST /api/documents/`,
`ingest --async`) e passano tutti da lì: se ognuno scrivesse per conto proprio
stato ed `enqueue`, la prima modifica a quella coppia di righe si dimenticherebbe
in tre punti su quattro. È la stessa forma per cui P2 ha un solo
`ingest_document()`.

**L'import è `django_tasks`, con l'underscore.** Django 6 ha una propria
`django.tasks` che legge lo *stesso* setting `TASKS` ma spedisce solo i backend
`immediate` e `dummy`: un import sbagliato non dà errore, dà un task accodato su
un altro handler che nessun worker verrà mai a prendere. Il task riceve
`document_id`, non il documento: gli argomenti attraversano la coda come JSON, e
fra accodamento ed esecuzione il documento può essere cambiato o cancellato — il
worker deve leggere lo stato *attuale*, non una fotografia.

Le eccezioni del task **non si inghiottono**: il worker marca la riga
`DBTaskResult` come `FAILED` con il traceback, e `ingest_document()` ha già
persistito stato e motivo leggibile sul documento. Sono due registrazioni con due
destinatari — l'amministratore e chi sviluppa — e inghiottirle lascerebbe una
coda tutta verde sopra a documenti falliti.

`TASKS` sta nei settings e **non** viola RF-22: è l'indirizzo di un servizio di
infrastruttura, come `DATABASES` e `OLLAMA_BASE_URL`. Nessuna risposta cambia
perché il task è stato eseguito da un worker invece che in linea; cambia
*quando*.

### Eccezioni

`rag/services/exceptions.py`: `RagError` → `IngestionError` / `QueryError`, con
`ConfigurazioneNonSupportata` che eredita da entrambe perché le factory sono
chiamate dai due lati. Le condizioni **previste** sono eccezioni di dominio con
messaggi scritti per un amministratore che li legge nell'admin; i guasti
inattesi restano tali, con lo stack nel log. Non allargare le `except`: le
docstring documentano quali famiglie sono state *misurate* e perché
(p.es. `ConnectionError` builtin **e** `httpx.TransportError`, che non sono
imparentate).

Sotto tutto questo, da P5, c'è **`rag/errors.py`**: l'`EXCEPTION_HANDLER` di DRF
che risponde **JSON sempre**, anche con `DEBUG=True` — sulle rotte `/api/` non
c'è più la pagina di debug HTML, ed è una scelta: un client di un'API deve poter
leggere ogni risposta, e lo stack completo resta sulla console via
`logger.exception`. È la **rete di sicurezza, non la cura**: le viste continuano
a tradurre da sé le condizioni previste, e a dire *quale* id non esiste.

## Convenzioni di lavoro

**Le docstring sono la documentazione di progetto.** Sono lunghe di proposito e
spiegano il *perché*, con misure prese sul campo, requisiti citati per id
(RF-xx, T-xx, CA-xx, ARCHITECTURE §x) e limiti dichiarati apertamente. Chi
modifica un file deve aggiornare la docstring quando cambia la ragione, non solo
il codice, e mantenere lo stesso registro: niente commenti decorativi, ogni nota
deve dire qualcosa che il codice non dice già.

**Distinguere verificato da dedotto.** Il progetto scrive «misurato»,
«verificato sul sorgente della 0.0.17», «osservato in fase di pianificazione».
Non affermare comportamenti di librerie senza averli controllati.

**`plans/`** contiene, per ogni fase, tre file
(`YYYY-MM-DD-HHMM-<nome>-plan.md`, `-subagent-prompts.md`, `-report.md`). Sono un
**registro storico e non si riscrivono a posteriori**: il report dice cosa è
successo davvero, scostamenti compresi. `docs/docs-manifest.yaml` esclude
deliberatamente `plans/` dal riallineamento.

**Documentazione da riallineare** a ogni modifica sostanziale: `README.md`
(ingresso), più `ARCHITECTURE.md`, `REQUIREMENTS.md`, `PLAN.md`, `BACKLOG.md`.
`BACKLOG.md` porta lo stato delle attività per fase.

**Commit:** in italiano, prefissati dalla fase e con gli id delle attività —
`P3: catena LCEL, prompt dall'admin e non-risposta sotto soglia (T-23, T-25)`;
`docs: allinea la documentazione a P3`. **Mai** il trailer `Co-Authored-By` né
alcuna attribuzione a Claude.

## Vincolo non negoziabile: nulla esce dalla macchina

RNF-01. Non introdurre dipendenze o percorsi che possano inviare testo dei
documenti fuori: niente `langchain-openai`, niente `sentence-transformers`,
nessun tracing cloud. `base.py` forza `LANGSMITH_TRACING=false` perché LangChain
lo accenderebbe da sé trovando la variabile nell'ambiente. I provider alternativi
presenti negli enum (`openai_compatible`, `huggingface`) sono **alternative
documentate, non opzioni attivabili**: sollevano `ConfigurazioneNonSupportata`
con un messaggio che spiega perché.

## Stato

P0 → P5 completate (scaffolding, modelli e admin, ingestione, recupero e
generazione, API REST, asincronia e rifiniture). **P6 in corso:** T-36 → T-41
chiuse — suite pytest, `excerpt_length` promosso a configurazione,
`scripts/dimostrazione.ps1`, documentazione di consegna. **T-42** (prova da zero
su ambiente pulito, CA-1) e **T-43** (prova a rete staccata, RNF-01 e CA-9)
richiedono l'operatore e **non sono ancora state eseguite**: i posti dove
scriverne l'esito sono segnati nel README, in `REQUIREMENTS.md` §7 e in
`ARCHITECTURE.md` §9, e finché restano vuoti quei due criteri non vanno letti
come superati.

L'ingestione è **asincrona** da P5 su tutti gli inneschi HTTP e dell'admin: la
`POST /api/documents/` risponde **202** in ~0,9 s contro i 14,53 s che costava a
freddo, e a lavorare è `manage.py db_worker`. Resta sincrono, **per scelta**,
`manage.py ingest` senza `--async`: RNF-03 parla del ciclo richiesta/risposta
HTTP, e le prove di consegna (T-42, T-43) devono poter girare con un processo
solo. Sparito anche il **422** dalla `POST`: un PDF illeggibile lo scopre il
worker, e la condizione si legge su `GET /api/documents/{id}/`.

P5 ha tagliato T-33 (playground nell'admin) e T-35 (aggancio Langfuse), nell'ordine
che `BACKLOG.md` fissa; P6 non ha tagliato nulla. `LUNGHEZZA_ESTRATTO` non esiste
più: è `RetrievalProfile.excerpt_length` dalla migrazione `0005`, e RF-22 è
completo. Resta aperto `_memoizza()`, non protetto fra thread — con due processi
non è un problema di correttezza, perché la chiave contiene i valori della
configurazione, ma il caricamento a freddo si paga una volta per processo.

**Un rilievo da non addolcire nella documentazione:** in configurazione
predefinita CA-4 non lo regge la soglia. `score_threshold` filtra **solo** nella
strategia `similarity_score_threshold` (verificato sul sorgente di `_recupera()`)
e la pipeline predefinita usa `similarity`: su una domanda fuori tema tornano 3
segmenti con rilevanza 0,2192 / 0,1946 / 0,1659 e `generata: true`, e a
dichiarare la non conoscenza è il **prompt di sistema**. Il filtro esiste,
funziona ed è coperto da un test, ma si attiva scegliendo quella strategia.
