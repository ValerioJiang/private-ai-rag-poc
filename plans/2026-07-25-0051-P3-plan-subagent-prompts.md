# Prompt dei sub-agenti — Piano P3 (Recupero e generazione)

Materiale di esecuzione di
[2026-07-25-0051-P3-plan.md](2026-07-25-0051-P3-plan.md).

**Analisi delle dipendenze — esito: cinque fasi, cinque sub-agenti, in
sequenza. Nessun raggruppamento necessario e nessuno possibile.**

| Fase | Produce | Consuma dalla fase precedente |
|---|---|---|
| 1 | `RagError`/`QueryError`, cache delle factory, `get_llm()` | — |
| 2 | `query.py`: `esegui_ricerca()`, `SegmentoRecuperato`, fonti | `get_vectorstore()` memorizzata |
| 3 | catena LCEL, `build_prompt()`, `rispondi()`, non-risposta | `get_llm()`, le eccezioni, tutto `query.py` della fase 2 |
| 4 | `QueryLog`/`RetrievedChunk` | **rinomina** `rispondi()` della fase 3 |
| 5 | `manage.py ask`, rimozione dello spike, verifica di fase | `rispondi()` con `query_log_id` |

Il seam più delicato è **fra la fase 3 e la fase 4**: la fase 4 *rinomina* la
funzione che la fase 3 ha scritto. Il prompt della fase 4 lo dice
esplicitamente; se il sub-agente della fase 4 non trovasse una funzione
`rispondi` nel file, deve fermarsi e segnalarlo invece di inventarne una.

---

# Prerequisiti

Da verificare **prima** di far partire il primo sub-agente. Se uno solo fallisce,
fermarsi: nessuna fase di P3 è eseguibile senza database e senza Ollama, e un
sub-agente che parte con l'ambiente rotto produce un report che descrive
fallimenti d'ambiente scambiandoli per fallimenti di codice.

## Servizi

- [ ] PostgreSQL con pgvector attivo sulla porta **5434** (rimappata nel compose,
      non 5432)
      — verifica: `docker ps --format "{{.Names}} {{.Status}}"` mostra
      `archetype-lab-db-1 ... (healthy)`
      — se manca: `docker compose up -d`
- [ ] Ollama in esecuzione sull'host, porta 11434
      — verifica: `curl -s http://localhost:11434/api/tags`
- [ ] Modello di generazione `qwen2.5:7b-instruct` scaricato
      — verifica: `curl -s http://localhost:11434/api/tags | grep qwen2.5`
      — se manca: `ollama pull qwen2.5:7b-instruct`
- [ ] Modello di embedding `bge-m3` scaricato
      — verifica: `curl -s http://localhost:11434/api/tags | grep bge-m3`
      — se manca: `ollama pull bge-m3`

## Ambiente

- [ ] Interprete del progetto presente
      — verifica: `ls .venv/Scripts/python.exe`
      — **in ogni comando si usa `.venv/Scripts/python.exe`, mai `python` nudo**
- [ ] Versioni attese: Django 6.0.7, `langchain-core` 1.5.1,
      `langchain-ollama` 1.1.0, `langchain-postgres` 0.0.17
      — verifica:
      `.venv/Scripts/python.exe -c "import langchain_core,langchain_ollama,langchain_postgres,django; print(langchain_core.__version__, langchain_ollama.__version__, langchain_postgres.__version__, django.get_version())"`
- [ ] File `.env` presente alla radice (lo legge `config/settings/base.py`)
      — verifica: `ls .env`

## Dipendenze

- [ ] **Non se ne installano di nuove in P3.** `requirements.in` e
      `requirements.txt` devono restare invariati per tutta la fase
      — verifica finale: `git diff --stat requirements.in requirements.txt` vuoto

## Stato del database

- [ ] Migrazioni applicate, nessuna pendente
      — verifica: `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
      (deve stampare «No changes detected» ed uscire 0)
- [ ] Almeno un documento **indicizzato** — alla chiusura di P2: id **7**,
      `manuale-dipendenti.pdf`, 3 pagine, 3 segmenti, collezione `default`
      — verifica:
      `.venv/Scripts/python.exe manage.py shell -c "from rag.models import Document; print(list(Document.objects.filter(status='indexed').values_list('pk','original_filename','page_count','chunk_count')))"`
      — se vuoto: `.venv/Scripts/python.exe manage.py ingest samples/manuale-dipendenti.pdf`
- [ ] Pipeline predefinita presente
      — verifica:
      `.venv/Scripts/python.exe manage.py shell -c "from rag.models import RagPipeline; p=RagPipeline.objects.get(is_default=True); print(p.name, p.llm_profile.model_name, p.retrieval_profile.search_type, p.knowledge_base.collection_name)"`
      — atteso: `Pipeline predefinita qwen2.5:7b-instruct similarity default`

## Repository

- [ ] Branch `main`, working tree pulito
      — verifica: `git status --short` non stampa nulla
- [ ] Ultimo commit atteso: `c51dc4e` «P2: piano, prompt dei sub-agenti e report
      di esecuzione»
      — verifica: `git log --oneline -1`

## File del report

- [ ] Creare `plans/2026-07-25-0051-P3-plan-report.md` con l'intestazione, prima
      della fase 1. Ogni sub-agente vi aggiunge la propria sezione; il
      sub-agente successivo la legge prima di cominciare.

---

# Regole valide per TUTTI i sub-agenti

Da ripetere in testa a ogni prompt perché ogni prompt è autosufficiente. Sono
le lezioni pagate in P2, e ignorarle costa un falso verde.

1. **Il codice si copia dal piano, carattere per carattere**, docstring e
   commenti compresi. I commenti di questo progetto non sono decorazione: sono
   la documentazione delle trappole, e riscriverli «meglio» perde l'unica cosa
   che spiega perché il codice ha quella forma. Se un frammento del piano
   sembra sbagliato, **fermarsi e segnalarlo**, non correggerlo in silenzio.

2. **`manage.py shell < file.py` avvia una console interattiva e tronca i
   blocchi multiriga**, producendo falsi verdi. L'unica forma ammessa è:
   ```
   .venv/Scripts/python.exe manage.py shell -c "exec(open(r'<percorso>', encoding='utf-8').read())"
   ```
   Gli script di verifica si scrivono **fuori dal repository** (directory
   temporanea della sessione): `git status` deve restare pulito a parte i file
   della fase.

3. **`response.context` è `None` in `manage.py shell`** senza
   `django.test.utils.setup_test_environment()`. Chi legge i messaggi
   dell'admin deve chiamarlo per primo.

4. **Una verifica che non può fallire non è una verifica.** Prima di ogni
   `assert`, chiedersi *quale riga di codice deve essere eseguita perché questo
   passi*, e controllare che sia stata eseguita davvero: un id, un contatore,
   una riga di log. Tre dei quattro scostamenti di P2 sono stati `assert` che
   passavano **senza eseguire il codice che esistevano per provare**.

5. **I numeri misurati vanno rimisurati.** Le rilevanze citate nel piano sono
   del 25/07/2026 su 3 segmenti. Se il corpus è cambiato, sono cambiate.

6. **Un modello lento non è un modello bloccato.** Il primo embedding dopo un
   riavvio di Ollama può richiedere ~10 s, la prima generazione anche di più.
   Non interrompere prima di 60 s.

7. **Nessuna migrazione in P3.** Al termine di ogni fase:
   `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` deve
   uscire 0. Se producesse una migrazione, qualcuno ha toccato un campo che non
   doveva toccare: fermarsi.

8. **Un commit per fase**, con i soli file di codice della fase. **Mai** i file
   di `plans/`: si committano a parte alla chiusura di P3.

9. **Il report si compila alla fine della fase**, con l'esito reale — comandi
   eseguiti, output ottenuto, scostamenti dal piano e loro motivo. Un
   report che descrive ciò che il piano prometteva invece di ciò che è successo
   è peggio di nessun report.

---

# Fase 1 — Eccezioni, cache delle factory e `get_llm()` (T-21)

Sei un sub-agente che esegue **la fase 1 di cinque** del piano P3 del progetto
`archetype-lab`, un sistema RAG in Django 6 con pgvector e Ollama, interamente
locale. Il requisito centrale del progetto: **ogni parametro del comportamento
è una riga di database modificabile dall'admin, nessuna costante nel codice**.

Le fasi P0 (scaffolding e spike), P1 (modelli e admin) e P2 (ingestione) sono
chiuse. Il sistema sa costruire un indice ma **non sa ancora interrogarlo**: è
ciò che P3 aggiunge.

## Cosa devi fare

Leggi **per intero** `plans/2026-07-25-0051-P3-plan.md`, in particolare:

- la sezione **«2. Contesto — decisioni di progetto»**, decisioni **3, 4, 5, 6 e
  11**, che sono le tue;
- la sezione **«Fase 1 — Eccezioni, cache e `get_llm()` (T-21)»**, che contiene
  il codice esatto da scrivere e lo script di verifica completo.

Esegui i passi **1.1 → 1.7** nell'ordine, poi le nove verifiche.

## Prima di scrivere codice, leggi questi file

- `rag/services/exceptions.py` — la gerarchia attuale.
- `rag/services/factories.py` — il file da estendere. `get_embeddings()` e
  `verify_embedding_dimension()` sono il **modello stilistico esatto** da
  imitare per `get_llm()`.
- `rag/models/profiles.py` righe 47–118 — i campi di `LLMProfile`.
- `rag/signals.py` — la forma dei `@receiver` già registrati e il motivo degli
  import locali.
- `rag/services/ingestion.py` righe 150–167 — come `IngestionError` viene
  catturata. **La decisione 11 esiste per non doverle toccare**: se ti trovi a
  modificare `ingestion.py`, hai sbagliato qualcosa.

## Le tre trappole di questa fase

1. **`validate_model_on_init=True` solleva eccezioni di DUE famiglie diverse.**
   Verificato in pianificazione: modello non scaricato →
   `pydantic_core.ValidationError`, che è sottoclasse di **`ValueError`**;
   Ollama spento → `ConnectionError` **builtin**, sottoclasse di **`OSError`**,
   che sfugge del tutto al validatore pydantic. La clausola dev'essere
   `except (ValueError, OSError)`. Con il solo `ValueError` il caso più
   frequente — Ollama spento — passerebbe come guasto inatteso.

2. **`django.core.cache` NON è utilizzabile.** `LocMemCache` serializza con
   pickle anche restando in-process, e verificato: `cache.set()` solleva
   `TypeError: cannot pickle '_thread.RLock' object` sia per `ChatOllama` sia
   per `PGVector`. La cache è un **dizionario di modulo**. Non «migliorare» il
   codice usando `django.core.cache`: non funziona.

3. **La chiave della cache contiene i VALORI, non solo l'id.**
   `updated_at.timestamp()` per i profili, `index_fingerprint()` per la base di
   conoscenza. È ciò che rende corretto RF-22 anche in un processo che il
   `post_save` non lo riceve mai. Il receiver **non** è ciò che garantisce la
   correttezza: liberare memoria è il suo compito. Il codice del piano lo dice
   nelle docstring: copiale.

## Verifica

Lo script completo delle nove verifiche è nel piano, sezione «Fase 1 → Verify».
Scrivilo in una directory temporanea (**non** nel repository) ed eseguilo con:

```
.venv/Scripts/python.exe manage.py shell -c "exec(open(r'<percorso>', encoding='utf-8').read())"
```

Poi:

```
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py ingest --reindex 7
git status --short
git diff --stat rag/services/ingestion.py
```

La verifica **9** e il `--reindex 7` sono lì per la stessa ragione: memorizzare
`get_vectorstore()` tocca un percorso scritto in P2 (la cancellazione dei
vettori di RF-08 e l'ingestione). Se P2 si rompesse, sarebbe colpa di questa
fase.

## Hai finito quando

- Le nove verifiche stampano `OK` e lo script termina con «FASE 1: TUTTE LE
  VERIFICHE PASSATE».
- `makemigrations --check --dry-run` esce 0 con «No changes detected».
- `manage.py check` non segnala problemi.
- `manage.py ingest --reindex 7` riporta il documento a `indexed` con 3 segmenti.
- `git diff --stat rag/services/ingestion.py` è **vuoto**.
- `git status --short` elenca **solo** `rag/services/exceptions.py`,
  `rag/services/factories.py`, `rag/signals.py`.
- Hai committato con messaggio
  `P3: cache delle factory e get_llm (T-21)` e un corpo che cita (a) la doppia
  famiglia di eccezioni di `validate_model_on_init`, (b) perché la chiave
  contiene i valori e non solo l'id, (c) perché non si usa `django.core.cache`.
- Hai scritto la tua sezione nel report, con i **tempi misurati** di costruzione
  e riuso di `ChatOllama` e `PGVector` — servono alle fasi successive e a P6.

---

# Fase 2 — Ricerca vettoriale, punteggio e fonti (T-22, T-24)

Sei un sub-agente che esegue **la fase 2 di cinque** del piano P3 del progetto
`archetype-lab`, un sistema RAG in Django 6 con pgvector e Ollama, interamente
locale. Il requisito centrale: **ogni parametro è una riga di database
modificabile dall'admin**.

La fase 1 ha aggiunto la cache delle factory e `get_llm()`. Tu costruisci il
**recupero**: da una domanda ai segmenti pertinenti, con il loro punteggio e la
loro provenienza. Nessuna generazione: l'LLM è la fase 3.

## Cosa devi fare

Leggi **per intero** `plans/2026-07-25-0051-P3-plan.md`, in particolare:

- le decisioni **1** (il punteggio esposto è la rilevanza, non la distanza) e
  **2** (non si usa `as_retriever()`), che sono la ragione d'essere di tutta la
  fase;
- la sezione **«Fase 2 — Recupero e fonti (T-22, T-24)»**, con il codice esatto.

Esegui i passi **2.1 → 2.5**, poi le otto verifiche.

Leggi anche la sezione della fase 1 nel report
`plans/2026-07-25-0051-P3-plan-report.md`.

## Prima di scrivere codice, leggi questi file

- `rag/models/profiles.py` righe 256–317 — `RetrievalProfile`. I tre valori di
  `SearchType` **sono le stringhe di LangChain**, e i vincoli di database
  garantiscono già `fetch_k >= top_k` e le soglie dentro [0, 1]: **non
  rivalidarli** nel servizio.
- `rag/services/ingestion.py` righe 51–62 — `vector_id()`. È il ponte fra le due
  metà dello schema, e tu lo usi **al contrario** rispetto a P2: da un vettore
  recuperato risali alla riga `DocumentChunk`.
- `rag/services/factories.py` — `get_vectorstore()` come lo ha lasciato la fase 1.
- `rag/models/domain.py` righe 238–276 — `DocumentChunk`, in particolare
  `vector_id` e il suo `db_index=True`.
- `rag/admin.py` righe 151–170 — `RetrievalProfileAdmin`, la cui descrizione
  devi correggere.

## Le tre trappole di questa fase

1. **`similarity_search_with_score()` restituisce una DISTANZA, non una
   similarità: cresce al peggiorare della pertinenza.** RF-13 chiede un
   «punteggio di similarità» e `score_threshold` è dichiarato fra 0 e 1 con la
   semantica opposta. La conversione `rilevanza = 1 − distanza` avviene in **un
   solo punto** e da lì in poi circola una sola grandezza. Mostrare la distanza
   chiamandola «similarità» è il tipo di bugia che questo progetto rifiuta.

2. **Un `VectorStoreRetriever` perde i punteggi.** Non usare `as_retriever()`:
   RF-13 e `RetrievedChunk.score` (FloatField **non nullo**) li richiedono. I
   metodi `*_with_score` di `PGVector` esistono per tutte e tre le strategie —
   `max_marginal_relevance_search_with_score` compreso, firma verificata.

3. **Non usare `==` sui float.** `1.0 - (1.0 - 0.3169)` vale
   `0.31689999999999996`: un `assert distanza == 1.0 - punteggio` **fallirebbe**.
   Lo script di verifica del piano usa già una tolleranza; se ne scrivi altri,
   fai lo stesso.

## Riferimento — le rilevanze misurate il 25/07/2026

Sul corpus reale (`manuale-dipendenti.pdf`, 3 segmenti, `bge-m3`):

| Domanda | rilevanza top-1 | 2° e 3° |
|---|---|---|
| «Quanti giorni di ferie si maturano all'anno?» | 0,6831 | 0,4577 · 0,3725 |
| «Qual e il rimborso chilometrico?» | 0,7287 | 0,3757 · 0,3458 |
| «Qual e la capitale del Madagascar?» | 0,1976 | 0,1715 · 0,1463 |
| «Come si prepara la carbonara?» | 0,2603 | 0,2446 · 0,2432 |

**Rimisurale.** Se i tuoi numeri differiscono, sono i tuoi a valere e vanno nel
report: la soglia predefinita di 0,5 è giustificata da questi, e una soglia
giustificata da numeri vecchi non è giustificata.

## Verifica

Lo script delle otto verifiche è nel piano, sezione «Fase 2 → Verify». Due
punti meritano attenzione:

- **il punto 4** deve dimostrare che i `chunk_id` esistono **davvero** nel
  database e che pagina e ordinale della riga coincidono con quelli del
  segmento — non che l'attributo sia presente;
- **il punto 6** deve dimostrare **entrambe** le direzioni del taglio della
  soglia: pertinente sopra, fuori tema sotto. Una soglia che tiene tutto e una
  che butta tutto passerebbero ciascuna metà del controllo;
- **il punto 7** (MMR): con soli 3 segmenti i due ordini a lambda 1 e lambda 0
  **possono coincidere**. Se coincidono, **annotalo nel report** invece di
  dichiarare un verde che non c'è.

Al termine, riporta il profilo di recupero ai valori predefiniti:
`similarity`, `top_k=4`, `fetch_k=20`, `lambda_mult=0.5`, `score_threshold=0.5`.

## Hai finito quando

- Le otto verifiche passano; il punto 7 è annotato con l'esito reale.
- `makemigrations --check --dry-run` esce 0.
- `manage.py check` non segnala problemi.
- `git status --short` elenca solo `rag/services/query.py` e `rag/admin.py`.
- Il profilo di recupero è tornato ai valori predefiniti (verificalo e
  riportalo).
- Hai committato con messaggio
  `P3: ricerca vettoriale, punteggio di rilevanza e fonti (T-22, T-24)`.
- Il report contiene **le rilevanze che hai misurato tu**, la tabella dei
  metadata effettivamente presenti sui vettori, e l'esito del punto 7.

---

# Fase 3 — Catena LCEL, prompt dall'admin e non-risposta (T-23, T-25)

Sei un sub-agente che esegue **la fase 3 di cinque** del piano P3 del progetto
`archetype-lab`, un sistema RAG in Django 6 con pgvector e Ollama, interamente
locale. Il requisito centrale: **ogni parametro è una riga di database
modificabile dall'admin, senza riavvio e senza toccare il codice**.

La fase 1 ha dato la cache e `get_llm()`; la fase 2 il recupero con i punteggi.
Tu chiudi il cerchio: **la risposta**. È la fase in cui il sistema, per la prima
volta dallo spike di P0, risponde a una domanda usando **solo** configurazione
di database.

## Cosa devi fare

Leggi **per intero** `plans/2026-07-25-0051-P3-plan.md`, in particolare:

- le decisioni **7** (il prompt di sistema non è un template), **8**
  (`clean()` rifiuta i segnaposto sconosciuti) e **9** (sotto soglia non si
  interroga l'LLM);
- la sezione **«Fase 3 — Catena, generazione e non-risposta (T-23, T-25)»**.

Esegui i passi **3.1 → 3.5**, poi le undici verifiche più la verifica
supplementare a Ollama spento.

Leggi anche le sezioni delle fasi 1 e 2 nel report.

## Prima di scrivere codice, leggi questi file

- `rag/models/profiles.py` righe 21–34 — `RISPOSTA_NON_DISPONIBILE`,
  `DEFAULT_SYSTEM_PROMPT`, `DEFAULT_TEMPLATE`. **Il commento alle righe 21–24
  contiene la promessa che questa fase deve mantenere**: sotto soglia si
  risponde «non dispongo» *senza nemmeno interrogare l'LLM*.
- `rag/models/profiles.py` righe 320–362 — `PromptTemplate`, il suo `clean()`
  attuale e l'avvertenza sul conflitto di nome con
  `langchain_core.prompts.PromptTemplate`.
- `rag/models/domain.py` righe 95–147 — `RagPipeline`, `is_active`, `is_default`.
- `rag/services/query.py` — come lo ha lasciato la fase 2.
- `scripts/spike_rag.py` righe 99–128 — la catena dello spike: è il codice che
  promuovi. Le tre differenze deliberate sono elencate nella docstring di
  `build_chain()` nel piano.

## Le quattro trappole di questa fase

1. **`ChatPromptTemplate.from_messages([("system", testo), …])` estrae le `{…}`
   ANCHE dal prompt di sistema.** Un amministratore che vi scrivesse una graffa
   — un esempio JSON, una formula — romperebbe ogni richiesta successiva con un
   `KeyError`. Il campo è modificabile dall'admin per requisito (RF-21): è una
   porta aperta. Si passa un `SystemMessage(content=…)` **già costruito**, che
   LangChain inserisce letteralmente. Verificato in pianificazione:
   `input_variables` resta `['context', 'question']` e la graffa arriva intatta.

2. **`build_chain()` deve costruire l'LLM PRIMA del recupero**, anche se il
   recupero non ne ha bisogno. `get_llm()` valida contattando Ollama, quindi
   «Ollama spento» diventa `LlmNonRaggiungibile` prima che l'embedding della
   domanda fallisca con un errore inatteso. Non è casuale: è l'ordine che rende
   leggibile il guasto più frequente.

3. **Nel `try` attorno a `invoke()` si cattura solo `OSError`.** Un `KeyError` o
   un `TypeError` lì **non** sono un LLM irraggiungibile: chiamarli così
   manderebbe a cercare nel posto sbagliato. Devono restare guasti inattesi con
   il loro stack.

4. **Il punto 6 della verifica è l'unica asserzione dell'intero piano che
   dipende dall'obbedienza del modello**, non dal codice. Era verificata in P0
   con questo stesso prompt e questo stesso modello. Se fallisse, **non è una
   regressione**: annotalo come tale e affidati al punto 7, che ottiene lo
   stesso risultato per via strutturale (`generation_ms == 0`,
   `generata is False`).

## Verifica supplementare, obbligatoria

Con Ollama **spento**, esegui `rispondi("prova")` e **registra il tipo esatto
dell'eccezione**. Se non è sottoclasse di `OSError`, la clausola `except OSError`
del passo 3.5 va estesa a comprenderlo, e la modifica va documentata nel commit.
È l'unico punto del piano scritto su una previsione e non su una misura:
`get_llm()` è stato misurato, l'`invoke()` no. Riaccendi Ollama prima di
proseguire.

## Hai finito quando

- Le undici verifiche passano.
- Il punto **7** dimostra la non-risposta **per assenza di generazione**
  (`generation_ms == 0`, `generata is False`, `fonti == []`), non per confronto
  di testo.
- Il punto **9** dimostra RF-22/CA-5 nello stesso processo, senza riavvio, con
  **entrambe** le prove: quella meccanica (il prompt costruito contiene la
  modifica) e quella comportamentale (le risposte differiscono).
- La verifica a Ollama spento è stata eseguita e il tipo dell'eccezione è nel
  report; se necessario la clausola `except` è stata corretta.
- La configurazione è tornata ai valori di partenza: `RetrievalProfile` a
  `similarity / 4 / 0.5` e il prompt di sistema **senza** «MAIALINO».
- `makemigrations --check --dry-run` esce 0 — in particolare **dopo** la modifica
  a `PromptTemplate.clean()`, che non deve produrre migrazioni.
- `git status --short` elenca solo `rag/models/profiles.py` e
  `rag/services/query.py`.
- Hai committato con messaggio
  `P3: catena LCEL, prompt dall'admin e non-risposta sotto soglia (T-23, T-25)`.
- Il report contiene **le risposte effettivamente ottenute** alle tre domande, i
  tempi separati misurati, e il tipo dell'eccezione a Ollama spento.

---

# Fase 4 — Storico delle interrogazioni (T-26)

Sei un sub-agente che esegue **la fase 4 di cinque** del piano P3 del progetto
`archetype-lab`, un sistema RAG in Django 6 con pgvector e Ollama, interamente
locale.

Le fasi 1–3 hanno costruito la catena: il sistema risponde con le fonti. Tu
aggiungi l'**osservabilità nativa** — `QueryLog` e `RetrievedChunk` — che in
questo progetto sostituisce un servizio di tracing esterno, perché lo storico
deve vivere nell'admin Django, cioè dove la traccia chiede che il sistema sia
governabile (ARCHITECTURE §7.8).

## Cosa devi fare

Leggi **per intero** `plans/2026-07-25-0051-P3-plan.md`, in particolare le
decisioni **1** (il punteggio registrato è la rilevanza) e **10** (il
`QueryLog` si scrive sempre, anche in errore), e la sezione **«Fase 4 — Storico
delle interrogazioni (T-26)»**.

Esegui i passi **4.1 → 4.4**, poi le sette verifiche più quella dall'admin.

Leggi anche le sezioni delle fasi 1, 2 e 3 nel report.

## ATTENZIONE — il passo 4.1 è una RINOMINA

La fase 3 ha scritto in `rag/services/query.py` una funzione pubblica
`rispondi(domanda, *, pipeline=None, utente=None)`. Il tuo passo 4.1 la
**rinomina** in `_esegui_interrogazione(domanda, pipeline, utente, inizio)` e le
mette attorno un nuovo `rispondi()` che registra lo storico — esattamente la
forma di `ingest_document()` / `_esegui_ingestione()` in `ingestion.py`.

**Se non trovi una funzione `rispondi` in `query.py`, fermati e segnalalo**: la
fase 3 non ha prodotto ciò che ti serve, e inventarne una versione tua
renderebbe incoerente tutto ciò che segue.

## Prima di scrivere codice, leggi questi file

- `rag/models/logs.py` **per intero** — `QueryLog` con i tre tempi separati (la
  docstring spiega perché non sono uno solo), `RetrievedChunk.chunk` con
  `on_delete=SET_NULL`, il vincolo di unicità su `(query_log, rank)`.
- `rag/services/ingestion.py` righe 130–179 — la coppia
  `ingest_document` / `_esegui_ingestione` / `_marca_fallito`. **Imitarne la
  forma è il punto della fase**: un involucro che persiste l'esito attorno a un
  corpo che non se ne occupa.
- `rag/services/query.py` — come lo ha lasciato la fase 3.
- `rag/admin.py` righe 494–530 — `QueryLogAdmin` e `RetrievedChunkInline`, già
  in sola lettura dalla P1.

## Le tre trappole di questa fase

1. **Si registra la RILEVANZA, non la distanza.** È la stessa grandezza mostrata
   nelle fonti e confrontata con la soglia. Registrare la distanza qui e la
   rilevanza altrove significherebbe avere nello stesso database due numeri con
   lo stesso nome e ordini opposti. La verifica 3 esiste per escluderlo.

2. **`_registra()` non deve MAI sollevare.** Un guasto della registrazione non
   può trasformare una risposta riuscita in un errore: si annota nel log e
   basta.

3. **`rank` parte da 1, non da 0.** È un numero mostrato nell'admin, e la
   posizione zero in una classifica non si scrive. Il vincolo di unicità è su
   `(query_log, rank)`: `enumerate(..., start=1)`.

## Hai finito quando

- Le sette verifiche passano.
- Il punto **3** esclude esplicitamente che sia stata registrata la distanza.
- Il punto **5** dimostra che un'interrogazione **fallita** lascia comunque una
  riga con il motivo in `QueryLog.error`.
- La pagina di `QueryLog` nell'admin mostra le fonti con documento, pagina e
  punteggio (verifica con `django.test.Client`, ricordando
  `setup_test_environment()`).
- `makemigrations --check --dry-run` esce 0.
- `git status --short` elenca solo `rag/services/query.py` e `rag/admin.py`.
- Hai committato con messaggio
  `P3: storico delle interrogazioni con tempi e fonti (T-26)`.
- Il report riporta un `QueryLog` reale con i suoi tre tempi e le sue fonti.

---

# Fase 5 — `manage.py ask`, rimozione dello spike e verifica di fase (T-27)

Sei un sub-agente che esegue **la fase 5 di cinque**, l'ultima, del piano P3 del
progetto `archetype-lab`, un sistema RAG in Django 6 con pgvector e Ollama,
interamente locale.

Le fasi 1–4 hanno costruito e reso osservabile l'interrogazione. Tu la rendi
**usabile da riga di comando**, cancelli lo spike di P0 che non ha più ragione
d'essere, ed esegui la **verifica di fase di P3** — quella che decide se P3 è
chiusa.

## Cosa devi fare

Leggi **per intero** `plans/2026-07-25-0051-P3-plan.md`, in particolare la
decisione **12** (lo spike si cancella qui) e la sezione **«Fase 5 —
`manage.py ask`, rimozione dello spike e verifica di fase (T-27)»**.

Esegui i passi **5.1 → 5.2**, poi la verifica di fase nei suoi dieci punti da
**(a)** a **(j)**.

Leggi anche tutte le sezioni precedenti del report.

## Prima di scrivere codice, leggi questi file

- `rag/management/commands/ingest.py` **per intero** — è il modello stilistico
  esatto: `CommandError` per le condizioni previste, `self.style.WARNING` per
  gli avvisi sui tempi, risoluzione per nome o id.
- `scripts/spike_rag.py` righe 115–135 — le tre domande di prova e la forma
  dell'output. È ciò che il comando sostituisce, e le tre domande vanno riusate
  nella verifica di fase.
- `rag/services/query.py` — come lo ha lasciato la fase 4, in particolare la
  firma di `rispondi()` e i campi di `EsitoInterrogazione`.

## L'ordine conta

**Prima** esegui la verifica di fase, **poi** cancelli
`scripts/spike_rag.py` con `git rm`. Se cancellassi prima e la verifica
fallisse, avresti perso l'unico riferimento funzionante contro cui confrontare
il comportamento.

## La verifica di fase — dieci punti

Sono nel piano, sezione «Fase 5 → Verify». Tre meritano attenzione particolare:

- **(f) è il punto che chiude P3**, ed è il requisito centrale della traccia:
  cambiare la temperatura **dall'admin nel browser** e vedere la risposta
  successiva cambiare **senza riavvio**. Il criterio non è «la risposta cambia»
  in senso vago: a temperatura **0** due esecuzioni della stessa domanda devono
  dare **lo stesso testo**, a **1.8** devono differire. È così che si distingue
  un effetto reale da una coincidenza.
  Se `runserver` gira in un processo e `manage.py ask` in un altro, l'effetto è
  comunque visibile — ed è la prova che la decisione 4 del piano (la chiave
  della cache contiene i valori) non era teoria. **Annotalo nel report.**
  Se non hai un browser a disposizione, replica con `django.test.Client` e
  **dichiara il limite**, come ha fatto P2.

- **(h)** crea una seconda `RagPipeline` per dimostrare CA-7. **Cancellala** al
  termine e riporta la configurazione ai valori predefiniti.

- **(i)** riverifica che l'**ingestione di P2 funzioni ancora**: le fasi 1 e 4
  hanno toccato `exceptions.py` e le factory, che P2 usa.
  `manage.py ingest --reindex 7` deve riportare il documento a `indexed` con 3
  segmenti.

## Hai finito quando

- I dieci punti da (a) a (j) sono stati eseguiti e il loro esito è nel report
  **con le risposte effettivamente ottenute**, non con la loro descrizione.
- Il punto (f) riporta il confronto fra due esecuzioni a temperatura 0
  (identiche) e due a 1.8 (diverse).
- La pipeline di prova del punto (h) è stata cancellata e la configurazione è
  quella predefinita.
- `scripts/spike_rag.py` non esiste più. Eventuali riferimenti nei documenti
  (`grep -rn "spike_rag" --include="*.md" .`) sono **annotati nel report** come
  voci per `/update-docs`, **non** corretti qui.
- `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` esce 0.
- `git diff --stat requirements.in requirements.txt` è vuoto: P3 non ha aggiunto
  dipendenze.
- `git status --short` è pulito dopo il commit.
- Hai committato con messaggio
  `P3: comando ask, rimozione dello spike e verifica di fase (T-27)`.

## Il report finale — è parte della consegna

Chiudi il report `plans/2026-07-25-0051-P3-plan-report.md` con quattro sezioni,
sul modello del report di P2:

1. **Esito della verifica di fase**, punto per punto, con gli output reali.
2. **Registro dell'orchestrazione**: cosa è andato storto in ogni fase e come è
   stato recuperato. Se una verifica del piano si è rivelata incapace di
   fallire, **dillo**: è l'informazione più utile del documento.
3. **Consegna a P4**: la firma di `rispondi()`, la forma di
   `EsitoInterrogazione`, quali eccezioni sono `QueryError` (→ 400) e quali no
   (→ 500), i tempi reali misurati.
4. **Consegna a P6**: le cinque voci elencate nella sezione «6. Consegna attesa
   a P4 e a P6» del piano, più qualunque altra emersa durante l'esecuzione. In
   particolare la correzione a `PLAN.md` e a `config/settings/base.py` righe
   99–107 sulla cache, che è una voce per T-40.
