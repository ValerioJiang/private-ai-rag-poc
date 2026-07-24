# Prompt per i sub-agenti — P1 Modelli e admin (T-07 → T-13)

Piano di riferimento: [`2026-07-24-1834-P1-plan.md`](2026-07-24-1834-P1-plan.md)
Report di esecuzione da produrre: `plans/2026-07-24-1834-P1-plan-report.md`

Le quattro fasi vanno eseguite **in sequenza, un sub-agente per fase**. Ogni
prompt è autosufficiente: non presuppone di aver visto l'output dei precedenti.
Prima di lanciare la fase N+1, i criteri di completamento della fase N devono
essere verdi.

## Perché quattro sub-agenti e non uno solo, né otto

Il passaggio di consegne fra fasi avviene sempre attraverso **stato persistente**
— file sul disco e schema del database — mai attraverso il contesto della
conversazione. È la condizione che rende le fasi separabili:

| Da → a | Cosa passa | Come sopravvive al cambio di agente |
|---|---|---|
| 1 → 2 | i cinque modelli di profilo | `rag/models/profiles.py` + migrazione applicata |
| 2 → 3 | i sei modelli di dominio e log | `rag/models/domain.py`, `logs.py` + migrazione applicata |
| 3 → 4 | admin registrato | `rag/admin.py` |
| 1,2,3 → 4 | schema completo | tabelle nel database |

**Nessuna fase va accorpata.** La 1 e la 2 scrivono file diversi e producono
migrazioni distinte; la 3 legge i modelli dal disco; la 4 non fa che leggere lo
schema e scrivere una migrazione dati. Nessuna informazione vive solo nella
testa di un agente.

**Nessuna fase va spezzata oltre.** In particolare, T-11 e T-12 (admin dei
profili e admin del dominio) stanno **nello stesso sub-agente** perché scrivono
lo stesso file `rag/admin.py`: separarli significherebbe far riscrivere due
volte lo stesso modulo, con il secondo agente costretto a rileggere e fondere il
lavoro del primo.

**Una sola dipendenza non ovvia:** la fase 2 non si limita a creare file nuovi,
ma **aggiunge un metodo a `rag/models/profiles.py`** (passo 2.4), che è il file
scritto dalla fase 1. Il sub-agente della fase 2 deve quindi rileggerlo dal
disco prima di modificarlo, non ricostruirlo a memoria.

---

# Prerequisiti

Da verificare **una sola volta**, prima della fase 1. Se uno fallisce, risolverlo
prima di partire: nessuna fase li ricontrolla per conto proprio.

## Servizi

- [ ] **Container del database attivo e sano** —
      `docker compose ps db` → atteso `Up (healthy)`, porta `0.0.0.0:5434->5432/tcp`.
      Se spento: `docker compose up -d db`
- [ ] **Il database risponde** —
      `docker compose exec db psql -U rag -d ragdb -c "SELECT 1;"`
- [ ] **Estensione pgvector installata da P0** —
      `docker compose exec db psql -U rag -d ragdb -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"`
      → attesa una riga, `vector 0.8.5`

## Servizi NON necessari

- [ ] **Ollama non serve in tutta P1.** Questa fase non esegue alcuna inferenza:
      nessun embedding, nessuna generazione. Se `/health` riporta `ollama: false`
      perché il servizio è spento, **non è un problema di P1** e non va inseguito.
      Nessun sub-agente deve avviare Ollama, scaricare modelli o invocare
      `ChatOllama` / `OllamaEmbeddings`.

## Ambiente Python

- [ ] Virtualenv presente — `ls .venv/Scripts/python.exe`
- [ ] Django 6.0.x importabile —
      `.venv/Scripts/python.exe -c "import django; print(django.get_version())"`
      → atteso `6.0.7`
- [ ] Migrazioni di P0 applicate —
      `.venv/Scripts/python.exe manage.py showmigrations rag` → `[X] 0001_enable_pgvector`
- [ ] Superuser presente (serve alle verifiche delle fasi 3 e 4) —
      `.venv/Scripts/python.exe manage.py shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_superuser=True).count())"`
      → atteso `1` (utente `admin` / `admin`, creato in P0). Se stampa `0`:
      `DJANGO_SUPERUSER_PASSWORD=admin .venv/Scripts/python.exe manage.py createsuperuser --noinput --username admin --email admin@example.com`

## Dipendenze — nulla da installare

- [ ] **Nessun pacchetto va aggiunto in P1.** In particolare **pytest non è
      installato ed è corretto così**: i test sono P6 (T-36 → T-38). Le verifiche
      di questa fase usano `manage.py shell -c` e `django.test.Client`, che sono
      già disponibili. Verifica: `.venv/Scripts/python.exe -m pip freeze | grep -Ei "^pytest" ` → **nessun output atteso**

## Repository

- [ ] Posizionati nella radice corretta — `git rev-parse --show-toplevel`
      → atteso `C:/Users/vjiang/Documents/archetype-lab`
- [ ] Working tree pulito — `git status --short` → **nessun output**, a parte
      eventualmente `?? plans/…` per i file di piano non ancora committati
- [ ] Il piano è leggibile — `ls plans/2026-07-24-1834-P1-plan.md`
- [ ] Documenti di progetto presenti —
      `ls ARCHITECTURE.md REQUIREMENTS.md BACKLOG.md PLAN.md`

## Stato atteso del working tree durante l'esecuzione

- [ ] `ARCHITECTURE.md`, `BACKLOG.md`, `PLAN.md`, `REQUIREMENTS.md` e la cartella
      `plans/` **li aggiorna e committa l'utente a mano**. Nessun sub-agente deve
      aggiungerli, committarli, modificarli o «sistemarli». La loro comparsa in
      `git status` non è un errore da correggere.

---

# Fase 1: Profili di configurazione

Copre **T-07**. Nessuna fase precedente di P1: è la prima. Richiede solo che P0
sia chiusa (schema migrato, venv funzionante).

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-24-1834-P1-plan.md, sezione "Fase 1" — contiene il sorgente
  ESATTO dei file da creare, copialo da li' senza riscriverlo a modo tuo. Leggi
  anche le sezioni "Contesto" e "Design" dello stesso piano: contengono le
  decisioni gia' prese, che non vanno rimesse in discussione.
- ARCHITECTURE.md §6.1, §6.2 (blocco ER dei cinque profili) e §6.4 (tabella dei
  vincoli) — e' la specifica di questa fase
- REQUIREMENTS.md §3.3, requisiti RF-17 -> RF-21 e RF-24
- scripts/spike_rag.py, righe 38-44 e 99-110 — i valori scritti a mano che qui
  diventano default, prompt di sistema compreso

Obiettivo: trasformare i parametri che in P0 erano costanti Python dentro lo
spike (modello, temperatura, chunk_size, top_k, prompt) in righe di database
governabili dall'admin. E' il requisito centrale della traccia.

Contesto che NON puoi dedurre dal codice:
- I valori di default NON sono inventati: sono quelli misurati sulla macchina in
  P0. Embedding a 1024 dimensioni (bge-m3), timeout 180 s (il cold start ha
  toccato i 156 s), chunk 800/120, top_k 4, e un system prompt che ha prodotto la
  frase di non conoscenza carattere per carattere. Non "arrotondarli" a valori
  piu' belli.
- Django 6.0 ha RIMOSSO il parametro `check=` di CheckConstraint. Si usa
  `condition=`. Tutti gli esempi in circolazione scritti prima della 5.1 usano
  ancora `check=`: se copi da li' ottieni un TypeError al caricamento dei modelli.
- pytest NON e' installato ed e' corretto cosi': i test sono P6. Le verifiche di
  questa fase si fanno con `manage.py shell -c`.
- Ollama non serve: questa fase non esegue alcuna inferenza.

Esegui, nell'ordine, i passi da 1.1 a 1.6 della Fase 1 del piano:

1.1 Cancellare rag/models.py e creare la cartella rag/models/:
      rm rag/models.py
      mkdir -p rag/models
    Il file NON va lasciato accanto al package: i due si escluderebbero a vicenda
    e l'import diventerebbe ambiguo.
1.2 Creare rag/models/profiles.py con il sorgente del piano. E' il file piu'
    importante della fase: cinque modelli (LLMProfile, EmbeddingProfile,
    ChunkingProfile, RetrievalProfile, PromptTemplate) piu' la base astratta
    TimestampedModel e tre costanti di modulo.
    NON rimuovere i commenti e gli help_text: motivano scelte non ovvie
    (perche' il timeout e' 180, perche' la dimensione e' 1024, perche'
    EmbeddingProfile non ha base_url) e finiscono sotto gli occhi di chi usa
    l'admin.
1.3 Creare rag/models/__init__.py che riesporta i profili, con __all__.
1.4 Generare e applicare la migrazione, con nome esplicito:
      .venv/Scripts/python.exe manage.py makemigrations rag --name profili
      .venv/Scripts/python.exe manage.py migrate
1.5 OBBLIGATORIO — eseguire lo script di verifica del passo 1.5 del piano, che
    prova a salvare sei configurazioni incoerenti (overlap >= size, temperatura
    fuori scala, top_p fuori scala, fetch_k < top_k, prompt senza segnaposto,
    separatori non lista, secondo profilo predefinito) e pretende che vengano
    TUTTE rifiutate. Gira dentro una transazione annullata: il database resta
    pulito.
    Attese: SETTE righe "OK" (tante quante le chiamate a rifiutato(): alle sei
    prove elencate si aggiunge quella del secondo profilo predefinito), e
    "profili rimasti: 0" in fondo.
    Se anche una sola riga stampa "ERRORE", il vincolo corrispondente e' sbagliato
    e va corretto PRIMA di proseguire: non annotarlo e tirare avanti.
1.6 Commit:
      git add rag
      git commit -m "P1: profili di configurazione come righe di database"

PRINCIPIO ARCHITETTURALE DA NON VIOLARE:
nessun parametro di comportamento del RAG deve finire in config/settings/. Il
default vive nel campo del modello, mai nei settings. In questa fase non toccare
affatto la cartella config/.

VINCOLI IMPORTANTI:
- NON scrivere il servizio di ingestione, la factory, i signal post_save o i
  serializer: sono P2, P3 e P4. Questa fase crea SOLO modelli.
- NON registrare nulla in rag/admin.py: e' la fase 3.
- NON installare dipendenze, in particolare pytest.
- NON toccare scripts/spike_rag.py ne' samples/: si cancellano a fine P2, non ora.
- NON usare `git add -A` ne' `git add .`: ARCHITECTURE.md, BACKLOG.md, PLAN.md,
  REQUIREMENTS.md e plans/ li gestisce l'utente a mano.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe manage.py check
  .venv/Scripts/python.exe manage.py makemigrations --check --dry-run
  .venv/Scripts/python.exe manage.py showmigrations rag
  docker compose exec db psql -U rag -d ragdb -c "\dt rag_*"
  docker compose exec db psql -U rag -d ragdb -c "\d rag_chunkingprofile"
  git status --short

Criteri di completamento:
- manage.py check non riporta problemi
- makemigrations --check --dry-run risponde "No changes detected"
- showmigrations rag mostra [X] 0002_profili
- \dt rag_* elenca CINQUE tabelle: rag_llmprofile, rag_embeddingprofile,
  rag_chunkingprofile, rag_retrievalprofile, rag_prompttemplate
- \d rag_chunkingprofile mostra il vincolo chunkingprofile_overlap_minore_di_size
- il passo 1.5 stampa sette "OK" e nessun "ERRORE"
- rag/models.py non esiste piu'; esiste rag/models/ con __init__.py e profiles.py
- un commit sul branch main con i soli file di rag/

Al termine, crea plans/2026-07-24-1834-P1-plan-report.md (se non esiste) e
aggiungi una sezione "## Fase 1" con: esito, hash del commit, file creati, esito
riga per riga del passo 1.5, e qualunque scostamento dal piano.
Non modificare il file del piano.
```

---

# Fase 2: Entità di dominio, documenti e osservabilità

Copre **T-08, T-09, T-10**. **Richiede la fase 1 completata**: i modelli di
dominio hanno FK verso i cinque profili.

> **Attenzione:** questa fase non crea soltanto file nuovi. Il passo 2.4
> **modifica `rag/models/profiles.py`**, scritto dalla fase 1. Va riletto dal
> disco prima di essere toccato.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-24-1834-P1-plan.md, sezione "Fase 2" — contiene il sorgente
  ESATTO dei file da creare, copialo da li'. Leggi anche "Contesto" e "Design".
- rag/models/profiles.py GIA' PRESENTE sul disco — i modelli a cui puntano le FK,
  e il file che dovrai modificare al passo 2.4
- ARCHITECTURE.md §6.2 (blocco ER), §6.3 (le due meta' dello schema), §6.4
  (tabella degli on_delete), §6.5 (perche' il testo dei chunk e' duplicato)
- plans/2026-07-23-1800-P0-scaffolding-plan-report.md, sezione "Nomi effettivi
  delle tabelle create da PGVector"
- REQUIREMENTS.md, requisiti RF-06 -> RF-09, RF-16, RF-25

Obiettivo: creare le entita' di dominio (KnowledgeBase, RagPipeline, Document,
DocumentChunk) e di osservabilita' (QueryLog, RetrievedChunk), con gli on_delete
e i vincoli esatti di ARCHITECTURE §6.4.

Contesto che NON puoi dedurre dal codice:
- Le tabelle langchain_pg_collection e langchain_pg_embedding NON sono modelli
  Django: le crea e le gestisce langchain_postgres.PGVector, e Django non deve
  migrarle (ARCHITECTURE §6.3). Nessuna migrazione di questa fase deve nominarle.
  Il ponte fra i due mondi e' il campo DocumentChunk.vector_id.
- In P0 si e' verificato che langchain_pg_embedding.id e' di tipo `character
  varying`, NON uuid: per questo vector_id e' un CharField e non un UUIDField.
  Un UUIDField funzionerebbe per caso finche' LangChain genera UUID.
- Il vincolo di unicita' su (knowledge_base, checksum) e' PARZIALE, con
  condizione ~Q(checksum=""). In P1 il checksum non lo calcola nessuno (lo fara'
  T-20 in P2): senza la condizione, il secondo documento caricato nella stessa KB
  colliderebbe con il primo sul checksum vuoto.
- Django 6.0 ha rimosso `check=` da CheckConstraint: si usa `condition=`.
- Ollama non serve. pytest non e' installato ed e' corretto cosi'.

Esegui, nell'ordine, i passi da 2.1 a 2.7 della Fase 2 del piano:

2.1 Creare rag/models/domain.py con il sorgente del piano: KnowledgeBase (con il
    metodo index_fingerprint()), RagPipeline, Document (con la macchina a stati e
    la property needs_reindex), DocumentChunk.
2.2 Creare rag/models/logs.py con il sorgente del piano: QueryLog e
    RetrievedChunk.
2.3 Sostituire rag/models/__init__.py con la versione completa, che riesporta
    tutti e undici i modelli.
2.4 RILEGGI rag/models/profiles.py dal disco e AGGIUNGI a EmbeddingProfile il
    metodo clean() del piano, subito prima di __str__. Impedisce di cambiare
    modello o dimensione quando esistono documenti gia' indicizzati.
    L'import di Document e' DENTRO il metodo, non in cima al file: a livello di
    modulo creerebbe un ciclo, perche' domain.py importa profiles.py.
    Non riscrivere il resto del file: e' un'aggiunta chirurgica.
2.5 Generare e applicare la migrazione:
      .venv/Scripts/python.exe manage.py makemigrations rag --name dominio_e_log
      .venv/Scripts/python.exe manage.py migrate
2.6 OBBLIGATORIO — eseguire lo script di verifica del passo 2.6 del piano, che
    prova sul campo: il fingerprint cambia quando cambia il profilo; PROTECT
    impedisce di cancellare un profilo in uso; needs_reindex e' False su un
    documento non indicizzato e True su un fingerprint diverso; la cancellazione
    di un documento porta via i chunk ma NON lo storico delle interrogazioni, il
    cui riferimento diventa None. Gira in transazione annullata.
    Attese: sei righe "OK", "chunk rimasti 0", "RetrievedChunk rimasti 1 con
    chunk = None", e conteggi finali a zero.
    Un "ERRORE" va corretto PRIMA di proseguire.
2.7 Commit:
      git add rag
      git commit -m "P1: entita' di dominio, documenti, segmenti e storico interrogazioni"

VINCOLI IMPORTANTI:
- NON scrivere il servizio di ingestione: la macchina a stati e' definita qui ma
  la fara' girare P2. In P1 un documento creato resta "in attesa", ed e' corretto.
- NON implementare l'hook che cancella i vettori da pgvector: e' T-20, in P2.
- NON registrare nulla in rag/admin.py: e' la fase 3.
- NON creare migrazioni che nominino langchain_pg_collection o
  langchain_pg_embedding.
- NON toccare config/.
- NON usare `git add -A`: ARCHITECTURE.md, BACKLOG.md, PLAN.md, REQUIREMENTS.md e
  plans/ li gestisce l'utente a mano.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe manage.py check
  .venv/Scripts/python.exe manage.py makemigrations --check --dry-run
  docker compose exec db psql -U rag -d ragdb -c "\dt rag_*"
  docker compose exec db psql -U rag -d ragdb -c "\d rag_document"
  grep -rn "langchain_pg" rag/migrations/*.py | grep -v help_text   # deve essere VUOTO
  # NB: un grep sulla sola stringa "langchain_pg" NON puo' dare zero risultati: il
  # piano prescrive per vector_id un help_text che cita langchain_pg_embedding.id,
  # e makemigrations copia gli help_text nella migrazione. Il secondo grep esclude
  # quella riga: cio' che resta sarebbe una OPERAZIONE su quelle tabelle, e non
  # deve essercene. NON usare "grep RunSQL|RunPython" come proxy: in P1 la 0004
  # (fase 4) usa legittimamente RunPython per la configurazione predefinita.
  git status --short

Criteri di completamento:
- manage.py check non riporta problemi
- makemigrations --check --dry-run risponde "No changes detected"
- \dt rag_* elenca UNDICI tabelle (i cinque profili piu' rag_knowledgebase,
  rag_ragpipeline, rag_document, rag_documentchunk, rag_querylog,
  rag_retrievedchunk)
- \d rag_document mostra il vincolo parziale document_checksum_unico_per_kb e le
  due FK di snapshot
- il passo 2.6 stampa sei "OK" e nessun "ERRORE"
- nessuna OPERAZIONE di migrazione tocca le tabelle di langchain-postgres: nessun
  CreateModel per quelle tabelle e nessuna RunSQL che le nomini. La stringa
  "langchain_pg" puo' comparire in un help_text, ed e' corretto cosi'; il grep
  "| grep -v help_text" deve restare vuoto
- un commit sul branch main

Al termine, aggiungi al report plans/2026-07-24-1834-P1-plan-report.md una
sezione "## Fase 2" con: esito, hash del commit, file creati e file modificato
(profiles.py), esito riga per riga del passo 2.6, e qualunque scostamento.
Non modificare il file del piano.
```

---

# Fase 3: Pannello di amministrazione

Copre **T-11 e T-12**, tenuti insieme perché scrivono lo stesso file.
**Richiede le fasi 1 e 2 completate**: l'admin espone tutti e undici i modelli —
nove come voci di primo livello, `DocumentChunk` e `RetrievedChunk` come inline.

> Questa fase contiene l'**unica eccezione ammessa in P1 alla regola «non toccare
> `config/`»**: il passo 3.3 corregge `MEDIA_URL` e serve i media in sviluppo.
> È motivata nel piano e non riguarda il comportamento del RAG.

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-24-1834-P1-plan.md, sezione "Fase 3" — contiene il sorgente
  ESATTO di rag/admin.py, copialo da li' senza riscriverlo a modo tuo
- rag/models/profiles.py, domain.py, logs.py GIA' PRESENTI sul disco — i campi da
  esporre. Gli help_text scritti nelle fasi 1 e 2 compaiono automaticamente nei
  form: NON ripeterli nell'admin.
- REQUIREMENTS.md §3.3 (RF-17 -> RF-25, RF-30) e §6, caso d'uso UC-3
- ARCHITECTURE.md §6.1 — la distinzione fra configurazione d'indice e di query,
  che va resa VISIBILE all'utente nelle descrizioni dei fieldset

Obiettivo: rendere governabile dall'admin ogni parametro del sistema. E' il caso
d'uso che dimostra il requisito centrale della traccia, quindi l'admin non deve
solo funzionare: deve spiegare, dove serve, cosa cambia modificando un campo e se
serve reindicizzare.

Contesto che NON puoi dedurre dal codice:
- L'azione admin "reindicizza" NON va implementata: e' T-19, in P2. In questa
  fase il disallineamento si VEDE (colonna "disallineato") ma non si corregge,
  perche' il servizio di ingestione non esiste ancora.
- QueryLog e' di sola lettura per scelta: lo storico lo scrive il sistema in P3,
  non l'amministratore. has_add_permission e has_change_permission tornano False.
- DocumentChunk e RetrievedChunk NON vanno registrati come voci autonome:
  compaiono solo come inline in sola lettura. E' voluto.
- Ollama non serve. pytest non e' installato ed e' corretto cosi'.

Esegui, nell'ordine, i passi da 3.1 a 3.5 della Fase 3 del piano:

3.1 Aggiungere `verbose_name = "Sistema RAG"` a RagConfig in rag/apps.py.
3.2 Sostituire rag/admin.py con il sorgente del piano: cinque ModelAdmin per i
    profili, tre per il dominio, uno per QueryLog, piu' due inline in sola
    lettura. Ogni ModelAdmin ha fieldsets con descrizioni, list_display,
    list_filter e list_select_related dove serve.
3.3 ECCEZIONE MOTIVATA, unica modifica a config/ ammessa in P1:
    - in config/settings/base.py, riga 93: MEDIA_URL = "/media/" (con la barra
      iniziale). Senza, e' un URL RELATIVO e dalla pagina di un documento nell'admin
      si risolverebbe in /admin/rag/document/1/media/...: il link al PDF e' rotto.
    - in config/urls.py, aggiungere in fondo:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
      con i relativi import. static() non produce alcuna rotta quando DEBUG e'
      falso, quindi e' sicuro anche in produzione.
    Non e' una violazione del principio architetturale: MEDIA_URL e' un indirizzo
    di infrastruttura, non un parametro di comportamento del RAG.
3.4 OBBLIGATORIO — eseguire lo script di verifica del passo 3.4 del piano, che
    con django.test.Client apre changelist e form di aggiunta di tutti i modelli
    e verifica anche che un client ANONIMO venga rediretto al login (RF-30).
    Attese: tutte 200, tranne /admin/rag/querylog/add/ che deve dare 403 (e' di
    sola lettura per scelta), la richiesta anonima 302 verso /admin/login/, e
    "ESITO COMPLESSIVO: PASS".
    Se la console solleva UnicodeEncodeError, rieseguire con PYTHONIOENCODING=utf-8.
3.5 Commit — questa volta include anche config/:
      git add rag config/settings/base.py config/urls.py
      git commit -m "P1: admin dei profili, del dominio e dello storico"

VINCOLI IMPORTANTI:
- NON aggiungere azioni admin che indicizzano, reindicizzano o cancellano vettori:
  sono P2 (T-17, T-19, T-20).
- NON modificare i modelli per far contento l'admin. Se un campo sembra mancare,
  fermati e segnalalo nel report invece di aggiungerlo: lo schema e' stato
  deciso in ARCHITECTURE §6.2.
- NON toccare config/ oltre alle due righe del passo 3.3.
- NON installare dipendenze.
- NON usare `git add -A`.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe manage.py check
  .venv/Scripts/python.exe manage.py makemigrations --check --dry-run
  git status --short

Criteri di completamento:
- manage.py check non riporta problemi. E' il controllo principale della fase:
  gli errori di configurazione dell'admin (campi inesistenti in list_display o
  nei fieldsets) emergono qui e non a runtime.
- makemigrations --check --dry-run risponde "No changes detected": l'admin non
  deve aver introdotto modifiche allo schema
- il passo 3.4 stampa "ESITO COMPLESSIVO: PASS", richiesta anonima compresa
- MEDIA_URL vale "/media/" e config/urls.py serve i media in sviluppo
- un commit sul branch main

Al termine, aggiungi al report plans/2026-07-24-1834-P1-plan-report.md una
sezione "## Fase 3" con: esito, hash del commit, tabella degli status code
ottenuti al passo 3.4, e qualunque scostamento dal piano.
Non modificare il file del piano.
```

---

# Fase 4: Configurazione predefinita e verifica di fase

Copre **T-13**. **Richiede tutte le fasi precedenti**: la migrazione dati crea
righe per sette modelli e la verifica finale passa dall'admin.

> È la fase che chiude P1: oltre a creare la configurazione predefinita, esegue
> la **verifica di fase** richiesta da `BACKLOG.md` (admin navigabile,
> configurazione presente, nessun parametro salvabile in stato incoerente).

```
Lavora nel repository C:\Users\vjiang\Documents\archetype-lab (Windows, git-bash
disponibile tramite il tool Bash).

Leggi prima di iniziare:
- plans/2026-07-24-1834-P1-plan.md, sezione "Fase 4" — contiene il sorgente
  ESATTO della migrazione, copialo da li'
- rag/migrations/ — per confermare i nomi effettivi delle migrazioni 0002 e 0003,
  che servono in dependencies
- rag/models/profiles.py — i valori di default dei campi
- REQUIREMENTS.md, requisito RF-26 e criterio CA-1

Obiettivo: fare in modo che un'installazione pulita sia utilizzabile SUBITO dopo
`migrate`, senza dover creare a mano sette righe prima della prima domanda. E' il
requisito RF-26 e la condizione di CA-1.

Contesto che NON puoi dedurre dal codice:
- I valori della configurazione predefinita sono quelli VERIFICATI in P0:
  qwen2.5:7b-instruct a temperatura 0, bge-m3 a 1024 dimensioni, chunk 800/120,
  similarity con k=4, timeout 180 s, e il system prompt con cui il modello ha
  dichiarato di non sapere invece di inventare. Non modificarli.
- La migrazione deve usare apps.get_model() e NON importare dai modelli vivi, e
  deve RIPETERE i valori invece di leggerli dalle costanti del modulo: una
  migrazione deve continuare a funzionare quando il codice sara' cambiato.
- makemigrations NON genera migrazioni di dati: questo file si scrive a mano.
- Ollama non serve: la configurazione predefinita si crea senza contattare
  nessun modello. pytest non e' installato ed e' corretto cosi'.

Esegui, nell'ordine, i passi da 4.1 a 4.6 della Fase 4 del piano:

4.1 Creare rag/migrations/0004_configurazione_predefinita.py con il sorgente del
    piano: RunPython con funzione diretta e funzione inversa. La funzione inversa
    cancella nell'ordine opposto e NON tocca la base di conoscenza se contiene
    documenti.
4.2 Applicare la migrazione e verificarne la REVERSIBILITA':
      .venv/Scripts/python.exe manage.py migrate
      .venv/Scripts/python.exe manage.py migrate rag 0003
      .venv/Scripts/python.exe manage.py migrate
    Nessuno dei tre comandi deve produrre eccezioni. Una migrazione dati che non
    si sa disfare e' un debito nascosto: si scopre solo quando serve davvero.
4.3 OBBLIGATORIO — eseguire lo script del passo 4.3 del piano, che stampa la
    configurazione risultante e verifica con assert che la dimensione sia 1024,
    che il template contenga {context} e {question}, che il system prompt
    contenga la frase di non conoscenza, e che esista UN SOLO default per
    LLMProfile e per RagPipeline. Atteso: "CONFIGURAZIONE PREDEFINITA: PASS".
4.4 OBBLIGATORIO — eseguire lo script del passo 4.4 del piano: verifica di fase
    di P1, cioe' l'admin navigabile CON DATI DENTRO (changelist e pagine di
    modifica della KB, della pipeline, del profilo LLM e del prompt effettivi).
    Atteso: tutte 200 e "VERIFICA DI FASE P1: PASS".
4.5 OBBLIGATORIO — eseguire lo script del passo 4.5 del piano: prova che una
    configurazione incoerente non sia salvabile ATTRAVERSO IL FORM DELL'ADMIN,
    non solo via full_clean(). E' una prova diversa e piu' forte, perche' il
    ModelForm esclude dalla validazione i campi in readonly_fields.
    Atteso: "RF-24 DALL ADMIN: PASS". Uno status 302 significherebbe che
    l'oggetto e' stato salvato: e' un FALLIMENTO, non un successo.
4.6 Commit:
      git add rag
      git commit -m "P1: configurazione predefinita funzionante (RF-26)"

VINCOLI IMPORTANTI:
- NON creare documenti ne' indicizzare nulla: l'ingestione e' P2.
- NON toccare config/.
- NON aggiornare BACKLOG.md, ARCHITECTURE.md, PLAN.md o REQUIREMENTS.md per
  segnare P1 come chiusa: li aggiorna l'utente a mano.
- NON usare `git add -A`.

Verifica prima di dichiarare finito:
  .venv/Scripts/python.exe manage.py check
  .venv/Scripts/python.exe manage.py showmigrations rag
  docker compose exec db psql -U rag -d ragdb -c "SELECT name, is_default FROM rag_ragpipeline;"
  docker compose exec db psql -U rag -d ragdb -c "SELECT name, model_name, dimension FROM rag_embeddingprofile;"
  git log --oneline -5
  git status --short

Criteri di completamento:
- showmigrations rag mostra quattro migrazioni applicate, fra cui
  [X] 0004_configurazione_predefinita
- il passo 4.2 esegue avanti, indietro e di nuovo avanti senza eccezioni
- il passo 4.3 stampa "CONFIGURAZIONE PREDEFINITA: PASS"
- il passo 4.4 stampa "VERIFICA DI FASE P1: PASS"
- il passo 4.5 stampa "RF-24 DALL ADMIN: PASS"
- git log --oneline -5 mostra i QUATTRO commit di P1, uno per fase
- git status --short non mostra file di rag/ lasciati indietro

Al termine, aggiungi al report plans/2026-07-24-1834-P1-plan-report.md una
sezione "## Fase 4" con: esito, hash del commit, output integrale dei passi 4.3,
4.4 e 4.5, e poi una sezione finale "## Esito di P1" che riepiloghi, criterio per
criterio, i "Criteri di completamento di P1" elencati nel piano, con l'evidenza
per ciascuno. Aggiungi anche una nota sui debiti aperti verso P2 (la tabella
"Consegna a P2" del piano).
Non modificare il file del piano.
```

---

# Riepilogo delle dipendenze fra fasi

| Fase | Attività | Richiede | Passa alla successiva | Commit |
|---|---|---|---|---|
| 1 | T-07 | P0 chiusa, DB acceso | `rag/models/profiles.py`, migrazione `0002` | sì |
| 2 | T-08, T-09, T-10 | fase 1 | `domain.py`, `logs.py`, migrazione `0003` | sì |
| 3 | T-11, T-12 | fasi 1, 2 | `rag/admin.py`, media serviti | sì |
| 4 | T-13 | fasi 1, 2, 3 | configurazione predefinita nel DB | sì |

Totale atteso: **quattro commit**, uno per fase. Nessuna fase di sola verifica in
P1, a differenza di P0.

**Ollama non serve in nessuna delle quattro fasi.**
