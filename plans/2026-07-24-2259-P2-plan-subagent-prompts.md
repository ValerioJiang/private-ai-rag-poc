# Prompt per i sub-agenti — P2 Ingestione (T-14 → T-20)

Piano di riferimento: [`2026-07-24-2259-P2-plan.md`](2026-07-24-2259-P2-plan.md)
Report di esecuzione da produrre: `plans/2026-07-24-2259-P2-plan-report.md`

Le cinque fasi vanno eseguite **in sequenza, un sub-agente per fase**. Ogni
prompt è autosufficiente: non presuppone di aver visto l'output dei precedenti.
Prima di lanciare la fase N+1, i criteri di completamento della fase N devono
essere verdi.

## Perché cinque sub-agenti e non uno solo, né sette

Il passaggio di consegne fra fasi avviene sempre attraverso **stato persistente**
— file sul disco e contenuto del database — mai attraverso il contesto della
conversazione. È la condizione che rende le fasi separabili:

| Da → a | Cosa passa | Come sopravvive al cambio di agente |
|---|---|---|
| 1 → 2 | eccezioni di dominio e loader del PDF | `rag/services/exceptions.py`, `loaders.py` |
| 2 → 3 | le tre factory della configurazione d'indice | `rag/services/factories.py` |
| 3 → 4 | `ingest_document()`, `compute_checksum()`, `vector_id()` | `rag/services/ingestion.py` |
| 4 → 5 | comando e admin che innescano l'ingestione | `rag/management/commands/ingest.py`, `rag/admin.py` |
| 1..4 → 5 | **un documento realmente indicizzato** | righe in `rag_document`, `rag_documentchunk`, `langchain_pg_embedding` |

**Nessuna fase va accorpata.** Ognuna scrive file distinti, e le verifiche di
ciascuna sono eseguibili senza conoscere come è stata scritta la precedente: la
fase 3 usa le factory dal disco, la 4 usa il servizio dal disco, la 5 verifica
il comportamento del sistema e non l'implementazione.

**Nessuna fase va spezzata oltre.** In particolare:

- **T-15 e T-16 stanno nello stesso sub-agente (fase 2)** perché scrivono lo stesso
  file `rag/services/factories.py`: separarli costringerebbe il secondo agente a
  rileggere e fondere il lavoro del primo.
- **T-18 e T-19 stanno nello stesso sub-agente (fase 4)** perché condividono la
  stessa decisione di design — dove si innesca l'ingestione — e perché T-19
  riscrive `rag/admin.py`, che T-18 non deve toccare a metà.
- **T-20 è diviso fra fase 3 e fase 5**, ed è l'unica divisione non ovvia: la
  deduplica per checksum appartiene al servizio di ingestione (fase 3) perché è
  una regola che il servizio deve imporre, mentre la cancellazione dei vettori
  è un hook sui signal (fase 5) che ha bisogno di un documento già indicizzato
  per essere verificabile.

**Tre dipendenze non ovvie, da tenere presenti:**

1. La **fase 4 modifica `rag/admin.py`**, che esiste già ed è stato scritto in P1.
   Va **riletto dal disco e modificato**, non riscritto a memoria: contiene undici
   registrazioni di ModelAdmin che non c'entrano con P2.
2. La **fase 5 modifica `rag/apps.py`**, anch'esso preesistente.
3. La **fase 5 dipende dai dati lasciati dalle fasi 3 e 4** (un documento
   indicizzato) e li ripulisce alla fine. Se la fase 5 viene eseguita su un
   database vuoto, le sue verifiche non dimostrano nulla: in quel caso deve
   ricreare un documento indicizzato prima di procedere.

## Cosa nessun sub-agente deve fare

Vale per tutti e cinque, ed è la parte che in P0 e P1 ha richiesto correzioni:

- **Non aggiungere dipendenze** a `requirements.in` / `requirements.txt`. In
  particolare **non installare `tiktoken`** né `pytest`.
- **Non creare migrazioni.** P2 non cambia lo schema. Se
  `makemigrations --check --dry-run` non dice «No changes detected», la causa va
  capita (di norma un `help_text` toccato per sbaglio), non aggirata generando
  una migrazione.
- **Non scrivere `get_llm()`, `get_retriever()`, catene LCEL, cache delle
  factory, viste API o codice asincrono.** Sono P3, P4, P5.
- **Non toccare `config/settings/`.**
- **Non cancellare `scripts/spike_rag.py`** (solo la collezione `spike`, in fase 5).
- **Non usare `git add -A`**: `ARCHITECTURE.md`, `BACKLOG.md`, `PLAN.md`,
  `REQUIREMENTS.md`, `README.md` e `plans/` li aggiorna e committa l'utente a
  mano. Aggiungere al commit **solo** i file elencati nella propria fase.

---

# Prerequisiti

Da verificare **una sola volta**, prima della fase 1. Se uno fallisce, risolverlo
prima di partire: nessuna fase li ricontrolla per conto proprio.

## Repository

- [ ] Radice del progetto — `git rev-parse --show-toplevel`
      → `C:/Users/vjiang/Documents/archetype-lab`
- [ ] Branch `main`, working tree pulito — `git status --short` → nessun output
      (a parte i file in `plans/`, che sono di questa pianificazione)
- [ ] Ultimo commit `e81284f` o successivo — `git log --oneline -1`

## Servizi

- [ ] **Container del database attivo e sano** —
      `docker compose ps db` → atteso `Up (healthy)`, porta `0.0.0.0:5434->5432/tcp`.
      Se spento: `docker compose up -d db`
- [ ] **Le quattro migrazioni di P1 sono applicate** —
      `.venv/Scripts/python.exe manage.py showmigrations rag` → quattro `[X]`
- [ ] **Ollama attivo, con `bge-m3` scaricato** —
      `curl -s http://localhost:11434/api/tags` → l'elenco deve contenere `bge-m3`.
      Se manca: `ollama pull bge-m3`
- [ ] **`/health` verde su tutti e tre i controlli** — avviare
      `.venv/Scripts/python.exe manage.py runserver` e aprire
      `http://localhost:8000/health` → `{"status": "ok", …}`

**A differenza di P1, Ollama serve.** Le fasi 2, 3, 4 e 5 calcolano embedding
reali: senza il servizio non sono verificabili, e non ha senso proseguire
«saltando» le verifiche.

## Ambiente Python

- [ ] Virtualenv presente — `ls .venv/Scripts/python.exe`
- [ ] **Le librerie di P2 sono già installate, nessuna va aggiunta** —
      `.venv/Scripts/python.exe -c "import pymupdf, langchain_postgres, langchain_ollama, langchain_text_splitters; print('ok')"`
- [ ] `tiktoken` **non** è installato, e così deve restare —
      `.venv/Scripts/python.exe -c "import tiktoken" ` → atteso `ModuleNotFoundError`

## Dati

- [ ] Configurazione predefinita di P1 presente —
      `.venv/Scripts/python.exe manage.py shell -c "from rag.models import RagPipeline; print(RagPipeline.objects.get(is_default=True).knowledge_base.collection_name)"`
      → `default`
- [ ] PDF di prova presente — `ls samples/manuale-dipendenti.pdf`
- [ ] Esiste un superuser per le prove nell'admin; se no, crearlo con
      `manage.py createsuperuser`

## Build

Nessuno. Il progetto non ha passi di build: Django serve i file così come sono.

---

# Fase 1: Estrazione del testo dal PDF ed eccezioni di dominio (T-14)

Sei un sub-agente incaricato della **fase 1 di 5** del piano P2 del progetto
`archetype-lab` (sistema RAG in Django con LangChain e LLM locale, prova
tecnica). Lavori in `C:\Users\vjiang\Documents\archetype-lab`.

**Leggi prima di scrivere codice:**

1. `plans/2026-07-24-2259-P2-plan.md` — **la fase 1 per intero**, più le sezioni
   «Contesto» (in particolare la tabella dei dati di realtà misurati) e «Design».
   Il piano contiene il codice completo di ogni file: seguilo, non reinventarlo.
2. `ARCHITECTURE.md` §7.10 — perché PyMuPDF diretto e non `PyMuPDFLoader`, e la
   frase secondo cui il codice di estrazione dello spike «non va buttato, ma
   promosso in T-14».
3. `ARCHITECTURE.md` §8.5 — i PDF scansionati non sono supportati e il caso va
   **rilevato**, non ignorato.
4. `REQUIREMENTS.md` — RF-03, RF-10, CA-8.
5. `scripts/spike_rag.py`, righe 57-71 — la funzione `load_pdf()` da promuovere.
   **Non modificare né cancellare questo file.**

**Cosa devi produrre:** i tre file nuovi `rag/services/__init__.py`,
`rag/services/exceptions.py`, `rag/services/loaders.py`, con il contenuto dei
passi 1.1, 1.2 e 1.3 del piano.

**La trappola di questa fase, da non calpestare:**
`pymupdf.FileNotFoundError` **ombreggia l'omonima eccezione builtin e non la
sottoclassa** — deriva da `RuntimeError`. Scrivere `except FileNotFoundError` non
la catturerebbe, e l'errore sfuggirebbe come guasto inatteso. Il piano cattura
`pymupdf.FileNotFoundError` per nome, **prima** di `pymupdf.FileDataError`.
`pymupdf.EmptyFileError` è sottoclasse di `FileDataError`, quindi una sola
clausola copre file corrotto e file di zero byte. Tutto verificato sulla 1.28.0
installata: non «semplificare» accorpando le clausole.

**Verifiche da eseguire e da riportare:** le tre della sezione «Verify» della
fase 1 nel piano — PDF valido, PDF corrotto/vuoto/inesistente, PDF senza testo.
**Tutte e tre devono passare**, inclusi i casi di errore: sono loro a dimostrare
RF-10 e CA-8.

**Criteri di completamento:** quelli elencati in «Phase Complete When» della
fase 1. In più: `.venv/Scripts/python.exe manage.py check` senza problemi.

**Chiudi così:**

1. Commit con **solo** i file di questa fase:
   `git add rag/services && git commit -m "P2: estrazione del testo dai PDF ed eccezioni di dominio (T-14)"`
2. Crea `plans/2026-07-24-2259-P2-plan-report.md` (è la prima fase: il file non
   esiste ancora) e scrivi la sezione della fase 1 con la struttura usata in P0 e
   P1: esito, attività coperte, commit, file creati, **scostamenti dal piano**,
   output delle verifiche, consegna alla fase successiva.
3. Aggiorna a `DONE` lo `**Status:**` della fase 1 e a `[x]` le sue caselle nel
   piano `plans/2026-07-24-2259-P2-plan.md`.

Se durante l'esecuzione scopri che il piano è **sbagliato** su un fatto
verificabile, non adattarti in silenzio: correggi, e scrivi nel report cosa non
tornava e come lo hai verificato.

---

# Fase 2: Factory della configurazione d'indice (T-15, T-16)

Sei un sub-agente incaricato della **fase 2 di 5** del piano P2 del progetto
`archetype-lab` (sistema RAG in Django con LangChain e LLM locale, prova
tecnica). Lavori in `C:\Users\vjiang\Documents\archetype-lab`.

La fase 1 ha già creato `rag/services/exceptions.py` e `rag/services/loaders.py`:
**rileggili dal disco**, non presumere cosa contengano.

**Leggi prima di scrivere codice:**

1. `plans/2026-07-24-2259-P2-plan.md` — **la fase 2 per intero**, più le
   **decisioni di design 3, 4, 5, 6** e la tabella dei dati di realtà. Il piano
   contiene il codice completo: seguilo.
2. `ARCHITECTURE.md` §3 (il factory layer come cerniera dell'architettura), §7.4
   (strategie di chunking), §7.9 (perché `PGVector`, e i due ORM come prezzo
   dichiarato), §8.1 (la dimensione del vettore è un vincolo applicativo, non di
   schema).
3. `rag/models/profiles.py` — `ChunkingProfile` e `EmbeddingProfile`: enum, campi,
   default e `help_text`. Sono la specifica di cosa devi tradurre.
4. `rag/models/domain.py` — `KnowledgeBase.collection_name` e il suo `help_text`.
5. `scripts/spike_rag.py`, righe 47-54 e 85-95 — la stringa di connessione e la
   costruzione dello store da strutturare. **Non modificare questo file.**

**Cosa devi produrre:** il file nuovo `rag/services/factories.py` con
`connection_string()`, `get_splitter()`, `get_embeddings()`,
`verify_embedding_dimension()`, `get_vectorstore()`, secondo i passi 2.1 → 2.4.

**Le quattro cose non ovvie di questa fase:**

1. **`separators` vuoto significa «usa i predefiniti dello splitter»**, non
   «nessun separatore». Passare `[]` a `RecursiveCharacterTextSplitter`
   disattiverebbe ogni confine di paragrafo e produrrebbe un taglio cieco a
   `chunk_size` caratteri. Il piano passa `separators` solo se non vuoto.
2. **La strategia «basato su token» va rifiutata con un errore esplicito**, non
   implementata: `tiktoken` non è installato e **non va installato** (decisione 3
   del piano: misurerebbe i chunk con il tokenizer di un altro modello). Stesso
   trattamento per il provider di embedding `huggingface`, che richiederebbe torch.
3. **Costruire un `PGVector` esegue DDL a ogni chiamata** —
   `create_tables_if_not_exists()` e `create_collection()` — su una connessione
   SQLAlchemy distinta da quella di Django. Verificato sul sorgente della 0.0.17.
   Da qui: `create_extension=False`, e mai costruirlo dentro un ciclo.
4. **`normalize` non va applicato** e `dimension` non va passato al costruttore.
   Leggi le decisioni 5 e 6 del piano prima di «migliorare» questo punto: sono
   scelte argomentate su misure fatte, non omissioni.

**Verifiche da eseguire e da riportare:** le cinque della sezione «Verify» della
fase 2. Le verifiche 4 e 5 **richiedono Ollama attivo**. Attenzione: la prima
chiamata di embedding dopo l'avvio può richiedere fino a ~18 s per il caricamento
di `bge-m3` in VRAM — **non è un blocco, aspetta**.

Atteso alla verifica 5: le collezioni diventano `['default', 'spike']`. La
collezione `default` viene creata proprio dal DDL del costruttore: è il
comportamento voluto.

**Criteri di completamento:** quelli in «Phase Complete When» della fase 2,
inclusi i due negativi — nessuna `get_llm`/`get_retriever`, nessuna cache — e
`makemigrations --check --dry-run` → «No changes detected».

**Chiudi così:**

1. `git add rag/services/factories.py && git commit -m "P2: factory di segmentazione, embedding e vector store (T-15, T-16)"`
2. Aggiungi la sezione della fase 2 a `plans/2026-07-24-2259-P2-plan-report.md`,
   con la stessa struttura della fase 1.
3. Aggiorna `**Status:**` e caselle della fase 2 nel piano.

Se il piano risulta sbagliato su un fatto verificabile, correggilo e spiegalo nel
report.

---

# Fase 3: Servizio di ingestione e macchina a stati (T-17, deduplica di T-20)

Sei un sub-agente incaricato della **fase 3 di 5** del piano P2 del progetto
`archetype-lab` (sistema RAG in Django con LangChain e LLM locale, prova
tecnica). Lavori in `C:\Users\vjiang\Documents\archetype-lab`.

È la fase centrale di P2. Le fasi 1 e 2 hanno creato `rag/services/exceptions.py`,
`loaders.py` e `factories.py`: **rileggili dal disco** prima di usarli.

**Leggi prima di scrivere codice:**

1. `plans/2026-07-24-2259-P2-plan.md` — **la fase 3 per intero**, più le
   **decisioni di design 1, 2, 4, 6, 7, 10**, la sezione «Design» (il diagramma
   del flusso e la macchina a stati) e la tabella dei casi limite. Il piano
   contiene il codice completo di ogni funzione.
2. **`ARCHITECTURE.md` §6.3 e §6.5** — le due metà dello schema e la duplicazione
   consapevole del testo dei chunk. Sono la specifica del file che stai scrivendo.
3. `ARCHITECTURE.md` §4 (flusso di ingestione), §7.9.
4. `REQUIREMENTS.md` §6 UC-1 con le estensioni 3a, 3b, 1a; RF-06, RF-09, RF-10,
   RNF-04; CA-2, CA-8.
5. `rag/models/domain.py` — `Document` (stati, snapshot dei profili,
   `index_fingerprint`, vincolo parziale sul checksum) e `DocumentChunk` (vincolo
   su `(document, ordinal)`).
6. `plans/2026-07-24-1834-P1-plan-report.md`, sezione «Debiti aperti verso P2» —
   spiega perché la deduplica non può stare nel form del modello, e perché
   `original_filename` è vuoto per tutti.

**Cosa devi produrre:** il file nuovo `rag/services/ingestion.py` con
`vector_id()`, `compute_checksum()`, `trova_duplicato()`, `EsitoIngestione`,
`ingest_document()`, `_marca_fallito()`, `_esegui_ingestione()`, secondo i passi
3.1 → 3.4.

**Le cinque cose che devi capire prima di scrivere, non dopo:**

1. **L'ordine delle scritture è una scelta di correttezza** (decisione 2 del
   piano): **prima** i vettori in pgvector, **poi** le righe Django in
   `transaction.atomic()`. Non esiste una transazione che copra entrambe le metà,
   perché `PGVector` ha una connessione SQLAlchemy propria. L'ordine scelto fa sì
   che un fallimento produca *vettori orfani* — invisibili e sovrascrivibili —
   invece di *chunk che puntano al vuoto*. **Non «sistemare» questo punto
   spostando le scritture dentro `atomic()`:** peggiorerebbe.
2. **Gli id dei vettori sono deterministici**, `"<document_id>:<ordinal>"`, e
   `langchain-postgres` fa upsert su conflitto di id (`ON CONFLICT (id) DO
   UPDATE`, verificato sul sorgente della 0.0.17). È ciò che rende la
   reindicizzazione idempotente.
3. **`batch_size` va rispettato affettando i chunk**: `OllamaEmbeddings` non sa
   batchare e `PGVector.add_texts()` invia *tutti* i testi in una sola POST.
   Senza l'affettamento il campo dell'admin sarebbe decorativo.
4. **`processing` va salvato e commesso da solo**, prima del lavoro: dentro la
   transazione finale nessuno lo vedrebbe mai.
5. **I chunk si aggiornano con `update_or_create` per `(document, ordinal)`**, non
   si cancellano e ricreano: `RetrievedChunk.chunk` è `SET_NULL` e ricrearli
   azzererebbe lo storico delle interrogazioni (decisione 10).

**Una trappola specifica di Windows:** `compute_checksum()` deve **ripristinare
lo stato di partenza del file** — `seek(0)` se era aperto (caso del form
dell'admin: senza, si salverebbe un PDF di zero byte), `close()` se era chiuso
(caso di un `FieldFile` letto dal database: un handle aperto fa fallire con
`PermissionError [WinError 32]` la cancellazione del file da parte di un'altra
istanza). Entrambi i comportamenti sono stati osservati in fase di
pianificazione: il codice del piano li gestisce, non semplificarlo.

**Verifiche da eseguire e da riportare:** le sei della sezione «Verify» della
fase 3. **Richiedono Ollama attivo** e nessuna è facoltativa — in particolare la
3 (idempotenza), la 4 (deduplica), la 5 (rimozione dei vettori obsoleti in
entrambe le direzioni) e la 6 (CA-8, PDF corrotto). La prima chiamata di
embedding può richiedere ~18 s: non è un blocco.

**Il documento indicizzato dalla verifica 1 va lasciato nel database**: serve
alle fasi 4 e 5. **Annota il suo id nel report.**

**Criteri di completamento:** quelli in «Phase Complete When» della fase 3.

**Chiudi così:**

1. `git add rag/services/ingestion.py && git commit -m "P2: servizio di ingestione, macchina a stati e deduplica (T-17, T-20)"`
2. Aggiungi la sezione della fase 3 al report, **con l'id del documento
   indicizzato** e con i tempi misurati (servono a P3 e al README).
3. Aggiorna `**Status:**` e caselle della fase 3 nel piano.

Se il piano risulta sbagliato su un fatto verificabile, correggilo e spiegalo nel
report.

---

# Fase 4: Comando di gestione e innesco dall'admin (T-18, T-19)

Sei un sub-agente incaricato della **fase 4 di 5** del piano P2 del progetto
`archetype-lab` (sistema RAG in Django con LangChain e LLM locale, prova
tecnica). Lavori in `C:\Users\vjiang\Documents\archetype-lab`.

Le fasi 1-3 hanno creato il package `rag/services/` con loader, factory e
servizio di ingestione: **rileggilo dal disco**, in particolare la firma di
`ingest_document()`, `compute_checksum()` e `trova_duplicato()`.

**Leggi prima di scrivere codice:**

1. `plans/2026-07-24-2259-P2-plan.md` — **la fase 4 per intero**, più le
   **decisioni di design 5, 7, 8** e la tabella dei dati di realtà.
2. **`rag/admin.py` per intero.** Esiste già, l'ha scritto P1, e contiene undici
   registrazioni di ModelAdmin che non c'entrano con P2. Va **modificato**, non
   riscritto: se lo rigeneri a memoria perdi il lavoro di P1.
3. `plans/2026-07-24-1834-P1-plan-report.md`, «Debiti aperti verso P2», prima
   voce — spiega **perché** serve un form: il `ModelForm` dell'admin esclude dalla
   validazione i campi in `readonly_fields`, e `checksum` è fra quelli, quindi il
   vincolo di unicità arriverebbe al database come `IntegrityError` 500.
4. `REQUIREMENTS.md` — RF-07, RF-09, RF-25, RF-28, RF-29; CA-2.

**Cosa devi produrre:**

- `rag/management/__init__.py` e `rag/management/commands/__init__.py` (vuoti)
- `rag/management/commands/ingest.py` (nuovo) — passo 4.2
- `rag/admin.py` (**modificato**) — passi 4.3 → 4.7

**Le tre cose non ovvie di questa fase:**

1. **L'innesco dell'ingestione va in `DocumentAdmin.save_model()`, non in un
   signal `post_save`** (decisione 8): il servizio salva il documento più volte
   durante il lavoro, e un `post_save` si richiamerebbe da sé. Se vedi una
   ricorsione, la causa è qui.
2. **Il discriminante fra file appena caricato e file già salvato è
   `isinstance(file, UploadedFile)`.** Verificato: un `FieldFile` **non** è un
   `UploadedFile`. Serve a non ricalcolare il checksum su una modifica che non
   tocca il file.
3. **`normalize` e `batch_size` devono dire la verità nell'admin** (passo 4.6,
   decisione 5). E le descrizioni di `DocumentAdmin` che parlano di P2 al futuro
   vanno aggiornate al presente (passo 4.7): ora l'ingestione esiste.

**La trappola che rende una verifica falsamente verde:** un POST all'admin di
`Document` **senza** i quattro campi `chunks-TOTAL_FORMS`, `chunks-INITIAL_FORMS`,
`chunks-MIN_NUM_FORMS`, `chunks-MAX_NUM_FORMS` risponde **200 con l'errore
«ManagementForm … Campi mancanti»** e non crea alcuna riga. Una verifica di
deduplica che si limita a contare i documenti leggerebbe quel fallimento come un
successo. Verificato in fase di pianificazione: i punti 5 e 6 della sezione
«Verify» includono i quattro campi e **asseriscono** che `ManagementForm` non
compaia nella risposta. Non rimuovere quelle asserzioni.

**Verifiche da eseguire e da riportare:** le otto della sezione «Verify» della
fase 4. **Richiedono Ollama attivo.** La verifica 8 (RF-25) ripristina da sé il
profilo che modifica: assicurati che lo faccia davvero, altrimenti lasci la
configurazione predefinita alterata.

**Criteri di completamento:** quelli in «Phase Complete When» della fase 4. Nota
che `makemigrations --check --dry-run` deve restare «No changes detected»: una
modifica alla `description` di un fieldset dell'admin **non** è una modifica al
modello. Se compare una migrazione, hai toccato un `help_text` in
`rag/models/`.

**Chiudi così:**

1. `git add rag/management rag/admin.py && git commit -m "P2: comando ingest, innesco dall'admin e azione di reindicizzazione (T-18, T-19)"`
2. Aggiungi la sezione della fase 4 al report.
3. Aggiorna `**Status:**` e caselle della fase 4 nel piano.

Se il piano risulta sbagliato su un fatto verificabile, correggilo e spiegalo nel
report.

---

# Fase 5: Cancellazione dei vettori, verifica di fase e pulizia (T-20)

Sei un sub-agente incaricato della **fase 5 di 5**, l'ultima, del piano P2 del
progetto `archetype-lab` (sistema RAG in Django con LangChain e LLM locale, prova
tecnica). Lavori in `C:\Users\vjiang\Documents\archetype-lab`.

Le fasi 1-4 hanno costruito il percorso completo di ingestione e lasciato **almeno
un documento indicizzato** nel database. **Verificalo prima di iniziare:**

```bash
.venv/Scripts/python.exe manage.py shell -c "
from rag.models import Document, DocumentChunk
print(list(Document.objects.values_list('pk','original_filename','status','chunk_count')))
print('chunk totali:', DocumentChunk.objects.count())
"
```

Se non c'è alcun documento in stato `indexed`, le verifiche di questa fase non
dimostrerebbero nulla: creane uno con
`.venv/Scripts/python.exe manage.py ingest samples/manuale-dipendenti.pdf` prima
di procedere.

**Leggi prima di scrivere codice:**

1. `plans/2026-07-24-2259-P2-plan.md` — **la fase 5 per intero**, più le
   **decisioni di design 9 e 11**.
2. `ARCHITECTURE.md` §6.3 (Django non conosce le tabelle `langchain_pg_*`) e §6.4,
   dove la riga `DocumentChunk → Document` recita «`CASCADE` + hook che rimuove i
   vettori corrispondenti da pgvector»: quell'hook è ciò che stai scrivendo.
3. `REQUIREMENTS.md` — RF-08; CA-2, CA-8.
4. `rag/apps.py` — è ancora quello generato da `startapp`, senza `ready()`. Va
   **modificato**.
5. `rag/services/factories.py` — la firma di `get_vectorstore()`.

**Cosa devi produrre:**

- `rag/signals.py` (nuovo) — passo 5.1
- `rag/apps.py` (**modificato**) — passo 5.2
- L'esecuzione dei passi 5.3 (rimozione della collezione `spike`) e 5.4 (pulizia
  dei dati di prova)

**Perché tre meccanismi e non uno** (decisione 9 — leggila, è il cuore di questa
fase): `pre_delete` raccoglie i `vector_id` **finché le righe `DocumentChunk`
esistono ancora**; `post_delete` agisce solo dopo che la cancellazione è riuscita;
`transaction.on_commit()` rinvia la pulizia al commit, perché pgvector sta su
un'altra connessione e un rollback successivo di Django lascerebbe un documento
vivo **senza** vettori — la direzione sbagliata del guasto. In caso di errore
nella pulizia si **logga e non si risolleva**: il documento è già cancellato, e
una 500 dopo un'operazione riuscita sarebbe una bugia.

**Due cose da non confondere** (decisione 11): va rimossa la **collezione** `spike`
da `langchain_pg_collection`; **non** va cancellato `scripts/spike_rag.py`.
Finché `manage.py ask` non esiste (P3), quello script è l'unica dimostrazione
funzionante che il sistema *risponde*. Rimuovere la collezione non lo rompe:
la ricrea da sé con `pre_delete_collection=True`.

**Verifiche da eseguire e da riportare:** le quattro della sezione «Verify» della
fase 5. La **verifica 2 è manuale, nel browser**, ed è la verifica di fase di P2
richiesta dal backlog: nove punti da (a) a (i). **Va fatta davvero, e il report
deve dire cosa hai visto** — stato, numero di pagine e di segmenti, testo dei
messaggi, comportamento dell'errore — non solo che l'hai fatta. Se non puoi
aprire un browser, dichiaralo nel report come limite dell'esecuzione e replica i
punti (a)→(i) con `django.test.Client`, ricordando i quattro campi
`chunks-*` del management form dell'inline.

**Criteri di completamento:** quelli in «Phase Complete When» della fase 5, più i
**«Criteri di completamento di P2»** in fondo al piano: sei tu a doverli
verificare tutti, perché sei l'ultima fase.

**Chiudi così:**

1. `git add rag/signals.py rag/apps.py && git commit -m "P2: rimozione dei vettori alla cancellazione e verifica di fase (T-20)"`
2. Aggiungi al report la sezione della fase 5 **e** una sezione finale che
   consolidi:
   - l'esito dei «Criteri di completamento di P2»;
   - la sezione **«Consegna a P3 — cose accertate qui, da non riscoprire»**,
     partendo dalla tabella omonima del piano e aggiungendo quanto emerso in
     esecuzione (in particolare i tempi reali misurati e la semantica del
     punteggio restituito da pgvector);
   - la sezione **«Consegna a P6»** con i cinque punti da argomentare nella
     documentazione, il primo dei quali è la **correzione di ARCHITECTURE §6.5**;
   - un registro dell'orchestrazione: cosa è andato storto nelle cinque fasi e
     come è stato recuperato.
3. Aggiorna `**Status:**` e caselle della fase 5 nel piano.
4. **Non** aggiornare `BACKLOG.md`, `ARCHITECTURE.md`, `README.md`: li aggiorna
   l'utente, e la revisione dei documenti è `/update-docs` a valle
   dell'esecuzione.

Se il piano risulta sbagliato su un fatto verificabile, correggilo e spiegalo nel
report.
