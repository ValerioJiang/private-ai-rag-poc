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
.venv\Scripts\python.exe manage.py ingest samples/manuale-dipendenti.pdf
.venv\Scripts\python.exe manage.py ask "Quanti giorni di ferie si maturano?"
.venv\Scripts\python.exe manage.py ask "..." --pipeline "Pipeline predefinita" --json
```

Verifica dei presupposti prima di qualunque lavoro: `GET /health` riporta lo
stato di database, estensione `vector` e Ollama; `ollama list` deve mostrare
`qwen2.5:7b-instruct` e `bge-m3`.

**Test:** non esistono ancora (`rag/tests.py` è lo scheletro di `startapp`).
Sono pianificati in P6 (T-36 → T-38) con pytest, che **non è ancora fra le
dipendenze**. Finché non c'è, la verifica è quella descritta in ogni piano di
fase: comandi reali eseguiti su dati reali, con l'output riportato nel report.

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

### Eccezioni

`rag/services/exceptions.py`: `RagError` → `IngestionError` / `QueryError`, con
`ConfigurazioneNonSupportata` che eredita da entrambe perché le factory sono
chiamate dai due lati. Le condizioni **previste** sono eccezioni di dominio con
messaggi scritti per un amministratore che li legge nell'admin; i guasti
inattesi restano tali, con lo stack nel log. Non allargare le `except`: le
docstring documentano quali famiglie sono state *misurate* e perché
(p.es. `ConnectionError` builtin **e** `httpx.TransportError`, che non sono
imparentate).

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

P0 → P3 completate (scaffolding, modelli e admin, ingestione, recupero e
generazione). Prossima: **P4 — API REST** (T-28 → T-31): `rag/views.py` ha per
ora il solo `/health`. Poi P5 (asincronia con `django-tasks`, il cui unico punto
d'aggancio è `DocumentAdmin.save_model()`) e P6 (test e consegna).
L'ingestione è **sincrona** fino a P5: è un limite dichiarato, non una svista.
