# Architettura — Sistema RAG in Django

Documento di design. Precede l'implementazione descritta in [PLAN.md](PLAN.md).

---

## 1. On-premise o cloud? Cosa chiede davvero la traccia

La traccia impone **un solo vincolo di deployment**, ripetuto due volte:

> «La generazione delle risposte deve avvenire tramite un **LLM privato locale**.»
> «L'LLM deve essere **privato**: puoi usare il modello locale che preferisci, motivando la scelta.»

Il vincolo riguarda **il confine dell'inferenza**, non la geografia dei server.
«Privato» qui significa *che il testo dei documenti non venga elaborato da terzi*,
non necessariamente *che giri sul portatile*. Tre letture possibili:

| Scenario | Ammesso? | Note |
|---|---|---|
| **A.** Tutto in locale (docker-compose sulla macchina) | Sì | Lettura più stretta e più semplice da verificare per chi valuta. **È quella adottata.** |
| **B.** Self-hosted su infrastruttura propria (VPS con GPU, VPC privata) | Sì | Resta «privato»: nessun terzo vede i dati. Stessa architettura, cambia solo dove punta `base_url`. |
| **C.** LLM via API di terzi (OpenAI, Anthropic, Gemini) | **No** | Escluso esplicitamente dalla traccia. |

Sulle **altre** componenti la traccia tace, ma la coerenza logica impone di
estendere il vincolo agli **embedding**: se i chunk dei PDF venissero inviati a
un servizio di embedding cloud, il testo dei documenti uscirebbe comunque dal
perimetro e il requisito sarebbe aggirato, non rispettato. Quindi anche
l'embedding è locale.

Postgres è infrastruttura, non elaborazione da parte di terzi: un Postgres
gestito in cloud sarebbe accettabile. Per la prova resta comunque in
docker-compose, così chi valuta avvia tutto con un comando solo. Non c'è alcun
Redis: la coda dei task vive nello stesso Postgres (cfr. §7.5).

**Conclusione:** architettura interamente on-premise, ma progettata perché lo
spostamento dell'inferenza su un server GPU proprio sia un cambio di
configurazione dall'admin (`LLMProfile.base_url`), non una modifica al codice.

---

## 2. Vista di deployment

```mermaid
flowchart LR
    subgraph client["Esterno"]
        C["curl / Postman<br/>Admin Django"]
    end
    subgraph perimeter["Perimetro privato — nessun contenuto documentale esce"]
        direction TB
        subgraph compose["docker compose"]
            D["Django + DRF"]
            W["db_worker<br/>processo separato"]
            P[("PostgreSQL<br/>pgvector + coda task")]
        end
        subgraph host["Host — accesso diretto alla GPU"]
            O["Ollama<br/>qwen2.5:7b-instruct (generazione)<br/>bge-m3 (embedding)"]
        end
    end
    C -->|HTTP| D
    D -->|enqueue| P
    P -->|polling| W
    W --> P
    D -->|host.docker.internal| O
    W -->|host.docker.internal| O
```

Un solo servizio con stato: **PostgreSQL**, che tiene dati applicativi, vettori
e coda dei task. Ollama è un processo di inferenza senza stato persistente, e
serve **entrambi** i modelli: generazione ed embedding passano dallo stesso
servizio, quindi il progetto non ha alcuna dipendenza da torch.

Ollama **non è containerizzato**: su Windows il passthrough della GPU verso
Docker richiederebbe WSL2 e nvidia-container-toolkit. Gira nativamente
sull'host e i container lo raggiungono via `host.docker.internal`. Resta dentro
il perimetro privato — «privato» riguarda il confine dell'inferenza, non il
confine di Compose.

---

## 3. Architettura logica

Tre livelli, con il **factory layer** come cerniera: è l'unico punto che traduce
righe di configurazione in oggetti LangChain.

```mermaid
flowchart TB
    subgraph api["Livello di interfaccia"]
        A1["POST /api/documents/"]
        A2["POST /api/ask/"]
        A3["Admin Django"]
        A4["manage.py ingest / ask"]
    end
    subgraph svc["Livello servizi"]
        S1["ingestion.py"]
        S2["query.py"]
        S3["factories.py<br/>config → oggetti LangChain"]
    end
    subgraph cfg["Configurazione = righe di DB"]
        K1["RagPipeline"]
        K2["LLMProfile"]
        K3["EmbeddingProfile"]
        K4["ChunkingProfile"]
        K5["RetrievalProfile"]
        K6["PromptTemplate"]
    end
    subgraph infra["Adapter LangChain"]
        I1["PGVector"]
        I2["ChatOllama"]
        I3["PyMuPDF (fitz)"]
        I4["TextSplitter"]
    end
    A1 --> S1
    A4 --> S1
    A4 --> S2
    A2 --> S2
    A3 --> cfg
    S1 --> S3
    S2 --> S3
    S3 --> cfg
    S3 --> infra
```

Il principio che regge tutta la prova: **nessun parametro è una costante nel
codice**. `build_chain(pipeline)` legge la configurazione a ogni richiesta, con
cache invalidata da un signal `post_save`, così una modifica dall'admin ha
effetto senza riavviare il processo.

---

## 4. Flusso di ingestione

```mermaid
sequenceDiagram
    participant U as Utente
    participant API as Django / DRF
    participant Q as coda task<br/>(db_worker)
    participant L as Loader + Splitter
    participant E as Ollama bge-m3
    participant DB as Postgres + pgvector

    U->>API: POST /api/documents/ (PDF)
    API->>DB: Document status=pending
    API->>Q: enqueue ingest_document(id)
    API-->>U: 202 Accepted + id
    Q->>DB: status=processing
    Q->>L: PyMuPDF → pagine → chunk
    L->>E: embed(chunks)
    E->>DB: upsert vettori + DocumentChunk
    Q->>DB: status=indexed
```

Lo stato è persistito sul `Document`, quindi l'admin mostra sempre il progresso
reale e un fallimento resta ispezionabile (`error_message`) invece di sparire
nei log.

---

## 5. Flusso di interrogazione

```mermaid
sequenceDiagram
    participant U as Utente
    participant API as POST /api/ask/
    participant F as build_chain
    participant DB as pgvector
    participant LLM as Ollama

    U->>API: question + pipeline
    API->>F: config della pipeline
    F-->>API: catena LCEL
    API->>DB: ricerca similarity o MMR, top_k
    DB-->>API: chunk + score
    API->>LLM: prompt(context, question)
    LLM-->>API: risposta
    API->>DB: QueryLog
    API-->>U: answer + sources + latency_ms
```

---

## 6. Modello dati

### 6.1 Principio di separazione

Le entità di configurazione si dividono in due famiglie, ed è una distinzione
che va rispettata nello schema:

| | Determina | Modificabile a caldo? |
|---|---|---|
| **Configurazione d'indice** — su `KnowledgeBase`<br/>`EmbeddingProfile`, `ChunkingProfile` | Com'è *costruito* l'indice | No: modificarla richiede una reindicizzazione |
| **Configurazione di query** — su `RagPipeline`<br/>`LLMProfile`, `RetrievalProfile`, `PromptTemplate` | Come l'indice viene *interrogato* | Sì: effetto immediato sulla richiesta successiva |

Mettere il chunking sulla pipeline sarebbe un errore: cambiare `chunk_size` non
produce alcun effetto sui documenti già indicizzati, e l'admin mostrerebbe un
parametro che mente. Sta quindi sulla `KnowledgeBase`, e ogni `Document`
conserva uno snapshot dei profili usati al momento dell'indicizzazione: se il
profilo della KB cambia in seguito, l'admin può segnalare i documenti
disallineati e proporne la reindicizzazione.

**Come si rileva il disallineamento.** Due implementazioni possibili dello
stesso principio:

| | Meccanismo | Valutazione |
|---|---|---|
| **FK-snapshot** — *per la leggibilità* | `Document.indexed_embedding_profile` e `indexed_chunking_profile` puntano ai profili usati | Ispezionabile nell'admin: si vede *quale* profilo era attivo. Ma da solo non basta come criterio: se un profilo viene **modificato sul posto** l'FK resta uguale e il disallineamento sfugge |
| **Fingerprint** — *per il criterio* | Un hash dei *valori* dei due profili, salvato sul `Document` e ricalcolato al confronto | Un solo campo, e coglie anche la modifica sul posto — che è il caso realistico, visto che l'admin edita i profili esistenti invece di crearne di nuovi. Ma un hash non dice *cosa* è cambiato |

Si adottano **entrambi**: gli FK per la leggibilità nell'admin, il fingerprint
come criterio effettivo di `needs_reindex`. Il costo è un `CharField` in più
(T-09).

### 6.2 Diagramma ER

```mermaid
erDiagram
    LLMProfile {
        int id PK
        string name UK
        string provider "ollama | openai_compatible"
        string base_url
        string model_name
        float temperature
        float top_p
        int top_k
        int max_tokens
        int timeout_s
        bool is_default
    }
    EmbeddingProfile {
        int id PK
        string name UK
        string provider "huggingface | ollama"
        string model_name
        int dimension
        bool normalize
        int batch_size
    }
    ChunkingProfile {
        int id PK
        string name UK
        string splitter "recursive | token"
        int chunk_size
        int chunk_overlap
        json separators
    }
    RetrievalProfile {
        int id PK
        string name UK
        string search_type "similarity | mmr | threshold"
        int top_k
        int fetch_k
        float lambda_mult
        float score_threshold
    }
    PromptTemplate {
        int id PK
        string name UK
        text system_prompt
        text template "richiede context e question"
    }
    KnowledgeBase {
        int id PK
        string name UK
        string collection_name UK
        int embedding_profile_id FK
        int chunking_profile_id FK
        text description
    }
    RagPipeline {
        int id PK
        string name UK
        int knowledge_base_id FK
        int llm_profile_id FK
        int retrieval_profile_id FK
        int prompt_template_id FK
        bool is_active
        bool is_default
    }
    Document {
        int id PK
        int knowledge_base_id FK
        file file
        string original_filename
        string checksum "sha256, unico per KB"
        string status "pending|processing|indexed|failed"
        int page_count
        int chunk_count
        text error_message
        int indexed_embedding_profile_id FK "snapshot"
        int indexed_chunking_profile_id FK "snapshot"
        string index_fingerprint "hash dei valori dei profili"
        datetime uploaded_at
        datetime indexed_at
    }
    DocumentChunk {
        int id PK
        int document_id FK
        int ordinal
        int page_number
        text content
        int char_count
        string vector_id "= langchain_pg_embedding.id"
    }
    QueryLog {
        int id PK
        int pipeline_id FK
        int user_id FK
        text question
        text answer
        int retrieval_ms
        int generation_ms
        int latency_ms
        text error
        datetime created_at
    }
    RetrievedChunk {
        int id PK
        int query_log_id FK
        int chunk_id FK
        int rank
        float score
    }
    langchain_pg_collection {
        uuid uuid PK
        string name
        json cmetadata
    }
    langchain_pg_embedding {
        string id PK
        uuid collection_id FK
        vector embedding
        text document
        jsonb cmetadata
    }

    KnowledgeBase }o--|| EmbeddingProfile : "indicizzata con"
    KnowledgeBase }o--|| ChunkingProfile : "segmentata con"
    KnowledgeBase ||--o{ Document : contiene
    RagPipeline }o--|| KnowledgeBase : interroga
    RagPipeline }o--|| LLMProfile : genera-con
    RagPipeline }o--|| RetrievalProfile : recupera-con
    RagPipeline }o--|| PromptTemplate : formatta-con
    Document ||--o{ DocumentChunk : produce
    Document }o--o| EmbeddingProfile : "snapshot"
    Document }o--o| ChunkingProfile : "snapshot"
    QueryLog }o--o| RagPipeline : eseguita-da
    QueryLog ||--o{ RetrievedChunk : "ha recuperato"
    RetrievedChunk }o--o| DocumentChunk : riferisce
    DocumentChunk ||--o| langchain_pg_embedding : "puntata da vector_id"
    langchain_pg_collection ||--o{ langchain_pg_embedding : contiene
    KnowledgeBase ||--o| langchain_pg_collection : "mappata su collection_name"
```

### 6.3 Le due metà dello schema

Lo schema è gestito da **due proprietari diversi**, ed è una distinzione da
tenere presente nelle migrazioni:

- Le tabelle in `snake_case` con PK intera sono **modelli Django**, sotto
  controllo delle migrazioni del progetto.
- `langchain_pg_collection` e `langchain_pg_embedding` sono create e gestite da
  `langchain_postgres.PGVector`. Django non le conosce e non deve
  migrarle. Il ponte tra i due mondi è `DocumentChunk.vector_id`.

### 6.4 Vincoli e cancellazioni

| Relazione | `on_delete` | Motivo |
|---|---|---|
| `RagPipeline` → profili | `PROTECT` | Cancellare un profilo in uso romperebbe la pipeline in silenzio |
| `KnowledgeBase` → `Embedding/ChunkingProfile` | `PROTECT` | Idem, e l'indice diventerebbe non riproducibile |
| `Document` → `KnowledgeBase` | `CASCADE` | Eliminare una KB elimina i suoi documenti |
| `DocumentChunk` → `Document` | `CASCADE` | + hook che rimuove i vettori corrispondenti da pgvector |
| `QueryLog` → `RagPipeline` | `SET_NULL` | Lo storico delle interrogazioni sopravvive alla pipeline |
| `RetrievedChunk` → `DocumentChunk` | `SET_NULL` | Lo storico sopravvive alla cancellazione del documento |

Vincoli a livello di DB:

- `UniqueConstraint(knowledge_base, checksum)` su `Document` — deduplica gli
  upload dello stesso PDF
- `UniqueConstraint(document, ordinal)` su `DocumentChunk`
- `CheckConstraint(chunk_overlap < chunk_size)` su `ChunkingProfile`
- `CheckConstraint(0 <= temperature <= 2)` su `LLMProfile`
- `UniqueConstraint(is_default=True)` parziale su `LLMProfile` e `RagPipeline` —
  un solo default per tipo

### 6.5 Duplicazione consapevole del testo dei chunk

Il testo di ogni chunk esiste **due volte**: in `DocumentChunk.content` e in
`langchain_pg_embedding.document`. È ridondanza accettata di proposito:

- **Pro:** l'admin può ispezionare, cercare e citare i chunk con l'ORM normale;
  le citazioni riportano numero di pagina e ordinale senza interrogare il vector
  store; una reindicizzazione può ripartire dai chunk già calcolati.
- **Contro:** circa il doppio dello spazio per il testo e due scritture da
  mantenere allineate. La riconciliazione avviene in un unico punto
  (`services/ingestion.py`), dentro una transazione.

L'alternativa — tenere tutto solo nei metadata di pgvector — risparmierebbe
spazio ma renderebbe l'admin cieco sul contenuto indicizzato, che è proprio ciò
che la traccia chiede di poter governare.

### 6.6 Come si legge il modello

`RagPipeline` è l'entità che rende il sistema dimostrabile: si creano due
pipeline sulla stessa `KnowledgeBase` — «veloce» (top_k basso, temperatura 0,
modello 3b) e «accurata» (MMR, top_k alto, modello 7b) — e si confrontano
cambiando una tendina, senza toccare il codice né reindicizzare.

---

## 7. Alternative valutate

### 7.1 Servizio di inferenza LLM

| Opzione | Pro | Contro |
|---|---|---|
| **Ollama** ✅ | Installazione in un comando; gestione modelli integrata; `langchain-ollama` è di prima classe; cambiare modello = cambiare una stringa nell'admin | Overhead superiore a vLLM; batching limitato; non pensato per alta concorrenza |
| vLLM | Throughput elevato, continuous batching, API OpenAI-compatibile | Setup CUDA delicato, immagine pesante; sovradimensionato per una prova |
| llama.cpp / llama-server | Leggerissimo, ottimo su CPU, GGUF quantizzati | Gestione modelli manuale, integrazione meno curata |
| transformers in-process | Nessun servizio esterno | Il modello vive nel processo Django: memoria enorme, reload lentissimo, incompatibile con più worker. **Scartato** |
| LM Studio | Ottima GUI | Non scriptabile né containerizzabile. **Scartato** |

### 7.2 Vector store

| Opzione | Pro | Contro |
|---|---|---|
| **pgvector** ✅ | Un solo datastore; coerenza transazionale tra `Document` e vettori; filtri sui metadata in SQL; un solo backup | Dimensione del vettore fissata nello schema; su milioni di vettori un motore dedicato è più veloce |
| Chroma | Zero infrastruttura, ideale per prototipi | Persistenza separata dal DB → rischio di disallineamento; meno maturo |
| FAISS | Ricerca velocissima | In-memory, nessuna persistenza dei metadata, nessun filtro, reindicizzazione a ogni avvio |
| Qdrant | Filtri potenti, prodotto eccellente | Un servizio in più senza un vantaggio concreto a questa scala |

### 7.3 Modello di embedding

| Opzione | Pro | Contro |
|---|---|---|
| **`bge-m3` via Ollama** ✅ | Multilingua di prima fascia (i PDF sono in italiano); **stesso servizio dell'LLM**, quindi nessuna dipendenza da torch/sentence-transformers (~2,5 GB di wheel risparmiati); nessun caricamento in-process nel worker HTTP | 1024 dimensioni: indice più pesante; ~1,2 GB di VRAM condivisi con il modello di generazione |
| `intfloat/multilingual-e5-small` (HuggingFace) | Buon multilingua, 384 dimensioni = indice compatto | Gira **in-process** via sentence-transformers: torch fra le dipendenze, primo caricamento lento, memoria duplicata per ogni worker |
| `nomic-embed-text` via Ollama | Stesso servizio dell'LLM, 768 dimensioni | Prevalentemente inglese: degraderebbe il retrieval su documenti italiani |
| Embedding cloud (OpenAI, Cohere) | Qualità superiore, nessun costo computazionale locale | Il testo dei documenti uscirebbe dal perimetro. **Contraddice il requisito** |

Scelta: **`bge-m3`**. Il fattore decisivo non è la qualità pura — `e5-small` è
adeguato — ma il fatto che passare da Ollama tiene l'intero progetto libero da
torch e concentra l'inferenza in un solo servizio governabile dall'admin. Le
1024 dimensioni sono il prezzo accettato, irrilevante alla scala di questa prova.

### 7.4 Strategia di chunking

| Opzione | Pro | Contro |
|---|---|---|
| **Recursive character** ✅ (default) | Rispetta i confini di paragrafo e frase; nessuna dipendenza extra | Ignora la struttura del documento (tabelle, colonne) |
| Token-based | Allineato alla finestra di contesto, dimensioni prevedibili | Richiede un tokenizer coerente col modello |
| Semantic chunking | Chunk coerenti per significato, retrieval migliore | Costo di embedding all'ingestione molto più alto |
| Layout-aware (`unstructured`) | Gestisce tabelle e layout multicolonna | Dipendenze pesanti (OCR, poppler), ingestione lenta |

Recursive e token-based sono entrambi esposti come valori dell'enum
`ChunkingProfile.splitter`: la scelta resta configurabile a runtime.

### 7.5 Elaborazione asincrona

| Opzione | Pro | Contro |
|---|---|---|
| **`django-tasks` + `django-tasks-db`** ✅ | API **agnostica rispetto al backend**, identica a quella entrata nella stdlib con Django 6.0; la coda vive in Postgres, quindi nessun servizio in più; un solo datastore da avviare e da salvare | Il worker fa polling sul DB; niente scheduling né retry ricchi nell'API core; **due** pacchetti community e 19 migrazioni in più |
| Celery + Redis | Standard di fatto, retry, monitoring maturo | Un servizio con stato in più; **Postgres non è un broker supportato** (il transport SQLAlchemy di kombu è di fatto abbandonato), quindi Redis diventa obbligatorio |
| procrastinate | Nativo Postgres con `LISTEN/NOTIFY`: nessun polling, retry e locking solidi | Meno diffuso, API propria non agnostica |
| django-q2 | Usa l'ORM come broker, semplice | Rimpiazzato in prospettiva da `django.tasks`; ecosistema più piccolo |
| Sincrono nella request | Semplicissimo | Timeout HTTP su PDF di centinaia di pagine |
| `threading.Thread` | Nessuna dipendenza | Nessuna durabilità: un riavvio perde il lavoro |

Scelta: **API in stile `django.tasks` con backend database**. Il vantaggio
decisivo non è tanto risparmiare un container, quanto che l'API è disaccoppiata
dalla coda: il passaggio a Celery e Redis, se il carico lo richiedesse, è una
voce di `settings.TASKS` e non una riscrittura del codice di ingestione. È la
stessa tesi che regge tutto il progetto — il comportamento è configurazione —
estesa al livello delle code.

**Precisazione verificata, contro l'assunzione più naturale.** Django 6.0
introduce `django.tasks` nella stdlib, ma ne spedisce **solo i backend
`immediate` e `dummy`**: in `django/tasks/backends/` non esiste alcun backend
database, né un comando worker. Una coda durevole richiede quindi comunque un
pacchetto esterno, e l'unico maturo — `django-tasks-db` — è costruito sopra il
**backport** `django-tasks` (modulo `django_tasks`), non sopra `django.tasks`:
il suo backend importa da `django_tasks.backends.base`.

In pratica, su Django 6 questo significa installare il backport di un framework
già presente nella stdlib, aggiungere `django_tasks` e `django_tasks_db` a
`INSTALLED_APPS` e portarsi 19 migrazioni. La decisione resta valida — è pur
sempre la coda durevole a minor costo infrastrutturale — ma la motivazione
corretta è «coda in Postgres senza servizi in più», **non** «basta la stdlib».

Con `ImmediateBackend` in fase di sviluppo il progetto gira senza worker
separato, così chi valuta può provarlo con un solo processo. È anche il motivo
per cui l'asincronia sta in P5 e non prima: se il tempo stringe si consegna
l'ingestione sincrona senza aver introdotto nessuna delle due dipendenze.

Limiti da dichiarare: il polling introduce latenza di partenza dell'ordine del
secondo, e a throughput elevato la tabella dei task diventerebbe un punto di
contesa. Per un carico fatto di poche ingestioni di PDF è ampiamente
sufficiente; per una coda ad alta frequenza servirebbe un broker vero.

### 7.6 Dove vive la configurazione

| Opzione | Pro | Contro |
|---|---|---|
| **Modelli Django** ✅ | Admin nativo, validazione in `clean()`, relazioni, storico via migrazioni | Più codice iniziale |
| django-constance | Rapidissimo per flag globali | Coppie chiave/valore piatte: niente profili multipli, niente relazioni |
| `settings.py` / variabili d'ambiente | Semplice, versionato | Richiede riavvio e accesso al codice. **Contraddice il requisito** |
| Un unico `JSONField` | Massima flessibilità | Nessuna validazione, nessuna UI decente, refactoring a mano |

### 7.7 Strategia di retrieval

| Opzione | Pro | Contro |
|---|---|---|
| **Similarity** ✅ (default) | Baseline solida, prevedibile | Può restituire chunk quasi identici |
| **MMR** ✅ (opzione) | Diversifica i risultati, utile su PDF ripetitivi | Due parametri in più da tarare (`fetch_k`, `lambda_mult`) |
| Ibrido BM25 + vettoriale | Molto meglio su codici, sigle, nomi propri | Richiede un indice full-text parallelo. **Fuori scope** |
| Reranker cross-encoder | Miglioramento netto della precisione | Raddoppia la latenza, un modello in più da servire. **Fuori scope** |

### 7.8 Osservabilità e tracing

| Opzione | Pro | Contro |
|---|---|---|
| **`QueryLog` + `RetrievedChunk` nativi** ✅ | Zero infrastruttura aggiuntiva; visibili **nell'admin Django**, cioè dove la traccia chiede che il sistema sia governabile; interrogabili con l'ORM per analisi aggregate | Nessun tracing annidato per singolo step della catena; nessun conteggio dei token; UI spartana |
| Langfuse self-hosted | Tracing per step, conteggio token, dataset e valutazioni, UI matura; interamente FOSS e installabile nel perimetro privato | **Sei container** (web, worker, Postgres, ClickHouse, Redis, MinIO), minimo raccomandato 4 vCPU e 8 GB di RAM — accanto a un modello 7B su GPU. Sproporzionato rispetto al peso che la traccia dà all'osservabilità |
| Langfuse Cloud | Nessuna infrastruttura da gestire | Le tracce contengono il prompt completo, quindi i chunk estratti dai PDF: il testo dei documenti uscirebbe dal perimetro. **Contraddice la premessa del progetto** |
| Arize Phoenix | Container singolo, OpenTelemetry, valutazioni RAG native (groundedness, rilevanza dei chunk) | Un servizio comunque in più; funzionalità di prompt management assenti |
| OpenTelemetry / OpenLLMetry puro | Leggerissimo, esporta verso qualunque backend già presente | Richiede un backend di raccolta per essere utile |

Decisione: **osservabilità nativa nei modelli Django**, più un punto di aggancio
per Langfuse dietro il flag `LANGFUSE_ENABLED`, disattivato di default e con un
profilo docker-compose dedicato. Il costo è di circa un'ora e l'integrazione
resta dimostrabile senza imporre a chi valuta un `docker compose up` da 8 GB.

```python
# rag/services/callbacks.py
def get_callbacks(pipeline):
    if not settings.LANGFUSE_ENABLED:
        return []
    from langfuse.langchain import CallbackHandler
    return [CallbackHandler(metadata={"pipeline": pipeline.name})]
```

**Nota di realtà:** sulla macchina di sviluppo uno stack Langfuse v3
self-hosted è **già in esecuzione** per altri progetti. Il costo
infrastrutturale che ne motivava l'esclusione è quindi già sostenuto *qui*, ma
non lo sarebbe per chi valuta la prova su una macchina pulita: la decisione
resta invariata, e l'attivazione resta dietro flag (T-35).

**Nota deliberata:** anche attivando Langfuse, la sua funzione di *prompt
management* resta inutilizzata. I prompt devono vivere in `PromptTemplate` e
essere modificabili dall'admin Django: spostarli altrove svuoterebbe proprio il
requisito centrale della traccia. Langfuse qui è osservabilità, mai
configurazione.

### 7.9 Come si accede ai vettori

Scelto pgvector (§7.2), resta una seconda decisione, spesso data per scontata:
**chi scrive le query vettoriali**.

| Opzione | Pro | Contro |
|---|---|---|
| **`langchain_postgres.PGVector`** ✅ | `as_retriever()` fornisce similarity, MMR e soglia già pronti (§7.7); integrazione LCEL diretta; nessuna query SQL scritta a mano | Possiede due tabelle fuori dalle migrazioni Django (§6.3); impone la duplicazione del testo dei chunk (§6.5); ferma alla **0.0.17**; trascina **SQLAlchemy, asyncpg e psycopg-pool**, cioè un secondo ORM e un secondo driver accanto a quelli di Django |
| `BaseRetriever` custom sull'ORM Django (`pgvector.django.CosineDistance`) | **Uno schema solo**, interamente sotto migrazioni Django; nessuna duplicazione del testo; un solo ORM e un solo driver; filtri sui metadata con l'ORM normale | MMR, `fetch_k` e `score_threshold` vanno implementati a mano; più codice da testare |

Scelta: **`PGVector`**, perché la traccia premia la configurabilità del
*retrieval* e avere MMR e soglia già pronti vale più dell'eleganza dello schema.

Il costo reale è più alto di quanto sembri e va detto: il progetto finisce con
**due ORM e due driver** verso lo stesso database. È il vero prezzo di §6.3,
non la sola duplicazione delle tabelle.

**Sullo stato della libreria (verificato):** `langchain-postgres` non è mai
uscita dalla serie 0.0.x — l'ultima release è la **0.0.17** — ma dichiara
`langchain-core<2.0,>=0.2.13`, quindi la **1.5.x in uso rientra nel vincolo**.
Non c'è conflitto di risoluzione; il rischio residuo è di comportamento, non di
dipendenze, e va confermato dallo spike (T-06).

**Piano di ripiego dichiarato:** se l'integrazione si rivelasse instabile, il
retriever custom sull'ORM è la via di uscita già valutata: costa circa mezza
giornata, elimina i compromessi §6.3 e §6.5, riduce l'albero delle dipendenze,
e degrada il solo MMR — che è già dichiarato come opzione, non come default.

### 7.10 Come si estrae il testo dal PDF

Scelto PyMuPDF (§1 del PLAN), resta da decidere **se passare dal loader di
LangChain**. La risposta non è scontata, perché `PyMuPDFLoader` **non fa parte
di PyMuPDF**: vive in `langchain-community`.

| Opzione | Pro | Contro |
|---|---|---|
| **PyMuPDF diretto (`fitz`)** ✅ | ~10 righe per produrre `Document` con `page` nei metadata; controllo totale sul rilevamento del PDF senza testo (RF-10); **zero dipendenze aggiuntive** | Il codice del loader è nostro, quindi da testare |
| `langchain_community.document_loaders.PyMuPDFLoader` | Poche righe in meno, metadata già popolati | Trascina `langchain-community` → `langchain-classic`, `aiohttp`, `requests`, `pydantic-settings`, `tenacity`: sei pacchetti per dieci righe |

Scelta: **PyMuPDF diretto**, per proporzione fra beneficio e peso. È l'unica
motivazione: il loader funzionerebbe benissimo.

**Nota, contro un argomento sbagliato che è facile farsi.** Si potrebbe pensare
di evitare `langchain-community` per tenere fuori `langsmith`, che è un client
di tracing verso un servizio esterno. L'argomento non regge: `langsmith` è
**dipendenza diretta di `langchain-core`**, quindi è nell'albero comunque, per
il solo fatto di usare LangChain. La garanzia di non esfiltrazione non si
ottiene selezionando i pacchetti — quelli che sanno parlare via rete sono la
norma — ma controllando il **comportamento a runtime**. Cfr. §9.

Conseguenza operativa: il codice di estrazione dello spike (T-06) **non va
buttato** come il resto, ma scritto con cura fin da subito e promosso in T-14.

---

## 8. Compromessi accettati

1. **La dimensione dell'embedding è un vincolo applicativo, non di schema.**
   `bge-m3` produce vettori a **1024** dimensioni, misurato sulla macchina in P0.
   Le tabelle create da `langchain-postgres`, però, tipizzano la colonna come
   `vector` **senza dimensione dichiarata** — verificato in P0 su
   `langchain_pg_embedding`: il database non rifiuta un vettore di lunghezza
   diversa. La coerenza va quindi garantita dal codice — profilo immutabile
   finché esistono documenti indicizzati, e collezioni separate per profili
   diversi — non delegata allo schema. Modificare `EmbeddingProfile` su una
   `KnowledgeBase` già popolata romperebbe comunque il retrieval: è prevista
   un'azione admin «ricostruisci collezione» che reindicizza tutto.
2. **`base_url` modificabile dall'admin** è ciò che rende il sistema
   configurabile, ma consente a un amministratore di puntare l'inferenza verso
   un host arbitrario. Accettabile qui (l'admin è già un ruolo fidato); in
   produzione andrebbe limitato a una allow-list. È anche l'unica falla residua
   nella garanzia di §9.
3. **Nessuna valutazione quantitativa della qualità** (RAGAS o simili): senza un
   dataset di riferimento sarebbe un numero senza significato. I `QueryLog`
   conservano però domanda, chunk recuperati e score, cioè la materia prima per
   costruirla.
4. **Nessuna gestione multi-utente sui documenti.** Ogni utente autenticato vede
   l'intera base di conoscenza.
5. **PDF scansionati non supportati.** PyMuPDF estrae testo, non fa OCR: un PDF
   di sole immagini produce zero chunk. Il caso è rilevato e segnalato come
   errore esplicito invece di generare un documento vuoto e silenzioso.

## 9. Garanzia di non esfiltrazione

RNF-01 chiede che nessun contenuto documentale lasci il perimetro. È una
promessa che va resa **verificabile**, non solo dichiarata.

Il rischio non sono le dipendenze. Pacchetti capaci di parlare via rete sono la
norma, e `langsmith` entra comunque nell'albero come dipendenza diretta di
`langchain-core` (§7.10): una lista di pacchetti «puliti» non dimostrerebbe
nulla. Il rischio è che **il testo dei chunk finisca dentro una richiesta
uscente**. I punti in cui quel testo transita davvero sono tre, non di più:

| Dove | Destinazione | Controllo |
|---|---|---|
| Calcolo degli embedding, in ingestione | `OLLAMA_BASE_URL` | Unico host contattato. Default: `localhost:11434` |
| Prompt di generazione — **contiene i chunk recuperati** | `OLLAMA_BASE_URL` | Idem |
| Tracing, se attivo | LangSmith (cloud) o Langfuse | Entrambi spenti **esplicitamente**, non solo «non configurati» |

Il terzo è l'unico che tradirebbe la promessa **in silenzio**, perché una
traccia contiene il prompt completo, cioè i chunk estratti dai PDF. Due sorgenti
possibili, entrambe da neutralizzare:

- **LangSmith** si attiva da variabili d'ambiente (`LANGSMITH_TRACING` più una
  chiave API). Ometterle non basta: se la macchina che ospita il progetto le ha
  già impostate per altri lavori, il tracing si accende da solo. Per questo
  `settings/base.py` forza `LANGSMITH_TRACING=false`, invece di limitarsi a non
  impostarlo.
- **Langfuse** sta dietro `LANGFUSE_ENABLED`, spento di default (§7.8), e anche
  da acceso punta a un'istanza self-hosted.

**Come lo verifica chi valuta, in un minuto:** si stacca la macchina dalla rete
e si rifà la prova completa — upload di un PDF, domanda, risposta con fonti. Se
funziona senza connettività, nessun contenuto sta uscendo. È una dimostrazione
più forte di qualunque elenco di dipendenze.

Cosa **non** è garantito, e va detto:

1. `LLMProfile.base_url` è modificabile dall'admin: un amministratore può
   puntare l'inferenza a un host arbitrario e far uscire i chunk. È il
   compromesso §8.2 — la configurabilità che la traccia chiede *è* anche la
   superficie di rischio. In produzione servirebbe una allow-list.
2. Nessuna misura verso chi ha accesso al database: chunk in chiaro, e il PDF
   originale sta in `media/`.
3. Nessun isolamento di rete a livello di container: la garanzia è di
   **configurazione**, non di enforcement. Un `network_mode` restrittivo sui
   servizi applicativi la renderebbe strutturale, ed è il primo miglioramento da
   fare se il sistema uscisse dal contesto di prova.

## 10. Fuori scope dichiarato

Reranking, ricerca ibrida, streaming SSE, memoria conversazionale,
multi-tenancy, ACL a livello di chunk, OCR.
