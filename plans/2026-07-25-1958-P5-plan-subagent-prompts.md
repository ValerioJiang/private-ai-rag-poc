# Prompt dei sub-agenti — Piano P5 (asincronia e rifiniture)

Piano di riferimento: [2026-07-25-1958-P5-plan.md](2026-07-25-1958-P5-plan.md).

Quattro fasi, quattro sub-agenti **in sequenza**: ognuno parte dal commit
lasciato dal precedente. I prompt sono scritti per essere incollati così come
sono; ciò che non è scritto qui va cercato nel piano, non inventato.

**Perché quattro sub-agenti e non uno solo, né otto.** L'analisi delle dipendenze
dà questo raggruppamento, e non è arbitrario:

- la **fase 1** è puramente infrastrutturale e non cambia alcun comportamento.
  Sta da sola di proposito: un fallimento d'installazione (pacchetti, migrazioni,
  check di Django) non va confuso con un fallimento di logica, e se la coda non
  si configura, le fasi 2–4 non hanno senso;
- la **fase 2** è un blocco indivisibile: il task, la funzione di accodamento e i
  **quattro** inneschi condividono un unico contesto. Spezzarla — per esempio
  «prima l'admin, poi l'API» — lascerebbe il sistema in uno stato in cui due
  inneschi accodano e due indicizzano in linea, e ogni verifica intermedia
  misurerebbe una via mista che nessuno consegnerà mai;
- la **fase 3** (T-34) tocca file diversi (`rag/errors.py`, `rag/signals.py`,
  `LOGGING`) e non dipende dal codice della fase 2, ma **dipende dalla fase 1**
  per il controllo «coda» di `/health`, e condivide `rag/views.py` con la fase 2:
  va dopo, non in parallelo;
- la **fase 4** non scrive codice: verifica con processi veri e riallinea la
  documentazione. Ha bisogno di tutto ciò che precede.

L'orchestratore, fra una fase e l'altra:

1. legge la sezione di report scritta dal sub-agente;
2. verifica che il commit esista e che il working tree sia pulito;
3. se una fase ha prodotto uno **scostamento**, decide se le fasi successive
   vanno adeguate **prima** di lanciarle.

---

# Prerequisiti (valgono per tutti)

Da verificare all'inizio della **prima** fase e da ricontrollare se una fase
successiva fallisce in modo strano. Ogni voce porta il comando che la verifica.

## Servizi

| Che cosa | Comando | Atteso |
|---|---|---|
| PostgreSQL + pgvector | `docker compose ps` | servizio `db` `Up … (healthy)`, porta **5434** |
| Ollama | `curl -s -m 5 http://localhost:11434/api/tags` | HTTP 200 |
| Modelli | `ollama list` | `qwen2.5:7b-instruct`, `bge-m3` |
| **PyPI raggiungibile** | `.venv\Scripts\python.exe -m pip index versions django-tasks` | elenca `0.12.0` |

La fase 1 **installa due pacchetti**: senza rete non parte. Verificato in
pianificazione il 25/07/2026 che PyPI risponde e che `django-tasks` 0.12.0 e
`django-tasks-db` 0.12.0 esistono.

Se una fase spegne Ollama per una prova, **deve** poi terminare anche i processi
`llama-server` figli: sopravvivono al padre, occupano la VRAM e fanno fallire il
caricamento successivo con un 500 di out-of-memory che sembra un difetto del
codice. Costato mezz'ora in P3.

## Ambiente

- Interprete: `.venv\Scripts\python.exe`, dalla radice del progetto —
  **Python 3.12.10** (verificare: `.venv\Scripts\python.exe --version`).
- `DJANGO_SETTINGS_MODULE` **non** impostato nell'ambiente: `manage.py` usa
  `config.settings.dev` (verificare: `echo $env:DJANGO_SETTINGS_MODULE` → vuoto).
- `.env` presente alla radice (verificare: `Test-Path .env`).
- Versioni attese prima di cominciare: Django **6.0.7**, djangorestframework
  3.17.1, langchain-core 1.5.1, langchain-ollama 1.1.0, langchain-postgres
  0.0.17, httpx 0.28.1 (verificare: `.venv\Scripts\python.exe -m pip list`).
- `curl` disponibile (verificare: `curl --version`).

## Dipendenze introdotte dalla fase 1

- [ ] `django-tasks>=0.12` e `django-tasks-db>=0.12` installati
      (verificare: `.venv\Scripts\python.exe -c "import django_tasks, django_tasks_db; print(django_tasks.__version__, django_tasks_db.__version__)"`).
- [ ] Le loro **19** migrazioni applicate
      (verificare: `.venv\Scripts\python.exe manage.py showmigrations django_tasks_database`).

Le fasi 2, 3 e 4 **presuppongono** questi due punti: se una parte e li trova
mancanti, si ferma e riferisce invece di installarli per conto proprio.

## Stato del database (misurato il 25/07/2026 alle 19:58)

- Documenti: uno, **id 7**, `manuale-dipendenti.pdf`, `indexed`, 3 segmenti.
- Base di conoscenza: una, **id 5**, «Base di conoscenza predefinita»,
  collezione `default`.
- Pipeline: una, **id 3**, attiva e predefinita. Profilo di recupero **id 3**,
  `similarity`, `top_k` 4, soglia 0,5.
- Storico: **58** `QueryLog`, **111** `RetrievedChunk`.
- Utenti: `admin` (superuser, **password ignota al piano**).
- `MEDIA_ROOT`: **6** file sotto `media/documents/2026/07/`.
- `DBTaskResult`: la tabella **non esiste ancora**; dopo la fase 1 esiste e ha
  **0 righe**.

Verifica in blocco:

```powershell
.venv\Scripts\python.exe manage.py shell -c "from rag.models import *; print(Document.objects.count(), QueryLog.objects.count(), RetrievedChunk.objects.count())"
```

Se i numeri non coincidono: **annotarlo nel report** e adeguare le asserzioni,
non i dati. Le verifiche di questo piano contano **delta** proprio per questo — è
la lezione di P4, dove i conteggi assoluti erano già stantii il giorno stesso.

## Repository

- Branch `main`, working tree pulito, ultimo commit **`023367f`** «docs:
  istruzioni per Claude Code» (verificare: `git status --porcelain` vuoto,
  `git log --oneline -1`).
- I tre file di `plans/` di questo piano restano **non tracciati**: li committa
  l'orchestratore alla chiusura di P5.

## File del report

`plans/2026-07-25-1958-P5-plan-report.md`. Ogni fase **aggiunge** la propria
sezione in coda; nessuna riscrive quelle altrui. Se il file non esiste, la prima
fase lo crea con l'intestazione e la tabella dei prerequisiti verificati.

---

# Regole valide per TUTTI i sub-agenti

1. **Il codice si copia dal piano carattere per carattere**, docstring e commenti
   compresi. Quei commenti contengono misure e verifiche sul sorgente delle
   librerie: riscriverli «meglio» perde l'informazione che li ha prodotti.
2. **Se il piano è sbagliato, si segnala — non si aggiusta in silenzio.** Se una
   *misura* impone di scostarsi (è successo in P3 con `except OSError`), si
   scosta, si misura di nuovo e si scrive nel report la misura che lo impone.
3. **L'import è `django_tasks`, con l'underscore.** Mai `django.tasks`, col
   punto: Django 6.0 ne ha una propria che legge lo stesso setting `TASKS` ma non
   ha backend database. Un import sbagliato non dà errore — dà un task che
   nessun worker verrà mai a prendere. Prima di chiudere la propria fase, ogni
   sub-agente esegue:
   `git grep -n "django\.tasks"` → **nessun risultato**.
4. **Gli script di verifica NON entrano nel repository.** Si scrivono nella
   directory scratch della sessione e si eseguono così:
   ```
   .venv/Scripts/python.exe manage.py shell -c "exec(open(r'<percorso>', encoding='utf-8').read())"
   ```
5. **Una verifica che non può fallire non è una verifica.** In questa fase il
   controllo negativo è quasi sempre lo stesso: **a worker spento il documento
   deve restare «in attesa»**. Senza di esso, un `enqueue` che eseguisse di
   nascosto in linea passerebbe tutte le altre asserzioni.
6. **Nessuna migrazione dell'app `rag`.** Ogni fase chiude con
   `makemigrations --check --dry-run` e riporta l'uscita. Le **19** migrazioni di
   `django_tasks_database` sono di terze parti e sono attese solo nella fase 1;
   se comparisse una migrazione di `rag`, **fermarsi** e riferire.
7. **Non si tocca nulla fuori dal perimetro della fase.** In particolare non si
   toccano mai: `rag/models/`, `rag/serializers.py`, `rag/services/query.py`,
   `rag/services/factories.py`, `rag/services/loaders.py`,
   `rag/services/exceptions.py`, `rag/urls.py`. L'unica modifica ammessa a
   `rag/services/ingestion.py` è alle **docstring**, nella fase 2.
8. **Un commit per fase**, con il messaggio indicato. Il messaggio è in italiano,
   descrive che cosa fa il codice e **non contiene alcun trailer di
   co-attribuzione** (niente `Co-Authored-By`, per nessun motivo, in nessuna
   forma). È una richiesta esplicita dell'utente.
9. **Non committare i file di `plans/`**: restano non tracciati fino alla
   chiusura di P5.
10. **Il report è parte della consegna, non un riassunto di cortesia.** Ci vanno
    l'output reale dei comandi, i tempi misurati in cifre e gli scostamenti. Un
    «tutto ok» senza output non è accettabile.
11. **Prima di dichiarare finita la fase**, rileggere l'elenco «Hai finito
    quando» del proprio prompt, punto per punto.

---

# Fase 1 — Dipendenze, app e backend della coda (T-32, infrastruttura)

Sei il sub-agente della fase 1 del piano P5. Leggi
`plans/2026-07-25-1958-P5-plan.md`, sezioni 1–5 e «Fase 1», e attieniti ad esse.

## Cosa devi fare

Sei passi, tutti descritti nel piano con il testo da copiare:

- **1.1** aggiungere a `requirements.in` il blocco «Coda dei task (P5, T-32)» con
  `django-tasks>=0.12` e `django-tasks-db>=0.12`, **con i commenti**: spiegano
  perché il vincolo è `>=0.12` e non `>=0.10`;
- **1.2** installare e **rigenerare** `requirements.txt` con `pip freeze` (mai a
  mano: è la convenzione del progetto);
- **1.3** aggiungere `django_tasks` e `django_tasks_db` a `INSTALLED_APPS`,
  con la nota che spiega perché servono entrambe;
- **1.4** aggiungere il blocco `TASKS` dopo `OLLAMA_BASE_URL`, con la nota che
  spiega perché non viola RF-22 e con l'avvertimento sull'import;
- **1.5** aggiungere `TASKS_BACKEND` a `.env.example`;
- **1.6** `manage.py migrate` — attese 19 migrazioni `django_tasks_database`.

**Questa fase non deve cambiare alcun comportamento.** Al termine il sistema fa
esattamente ciò che faceva a P4 chiusa: l'ingestione è ancora sincrona, perché
nessun innesco è stato toccato. È deliberato.

## Cosa NON devi fare

- Non creare `rag/tasks.py`: è la fase 2.
- Non toccare `rag/admin.py`, `rag/views.py`, `rag/management/`,
  `rag/services/`.
- Non avviare `db_worker` in modo persistente: qui basta `--help`.
- Non aggiungere pacchetti oltre i due indicati. Se `pip freeze` ne mostra altri
  oltre a `django-stubs-ext` e `typing_extensions`, **annotare nel report da dove
  arrivano** e verificarli contro RNF-01 (nulla deve poter parlare con la rete)
  prima di proseguire.

## Come verifichi

Nell'ordine, riportando l'uscita **reale** di ciascuno:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py showmigrations django_tasks_database
.venv\Scripts\python.exe manage.py db_worker --help
git diff --stat
```

Poi lo script `fase1.py` del piano (sezione «Fase 1 → Verify»), che asserisce:
backend configurato = `DatabaseBackend`, tabella dei task presente e vuota,
corpus intatto (un documento id 7, `indexed`, 3 segmenti).

## Hai finito quando

- [ ] `manage.py check` → 0 issues.
- [ ] `makemigrations --check --dry-run` → «No changes detected», uscita 0.
- [ ] `showmigrations django_tasks_database` → **19** righe, tutte `[X]`.
- [ ] `db_worker --help` elenca `--batch`, `--interval`, `--max-tasks`,
      `--queue-name`, `--no-reload`, `--no-startup-delay`.
- [ ] `fase1.py` stampa `FASE 1 OK`.
- [ ] `git diff --stat` tocca **solo** `requirements.in`, `requirements.txt`,
      `config/settings/base.py`, `.env.example`.
- [ ] `git grep -n "django\.tasks"` → nessun risultato.
- [ ] Le righe nuove di `requirements.txt` sono elencate nel report, una per una,
      con la loro provenienza.
- [ ] Sezione di report scritta.
- [ ] Commit: `P5: coda dei task in Postgres — dipendenze, app e backend (T-32)`

---

# Fase 2 — Ingestione asincrona (T-32)

Sei il sub-agente della fase 2 del piano P5. Leggi
`plans/2026-07-25-1958-P5-plan.md`, sezioni 1–5 e «Fase 2», e attieniti ad esse.
Presupponi che la fase 1 sia chiusa: se `import django_tasks_db` fallisce o le 19
migrazioni non risultano applicate, **fermati e riferisci**.

È il cuore di P5 ed è un blocco indivisibile: il task, l'accodamento e i quattro
inneschi si tengono insieme. Non consegnare uno stato intermedio in cui due
inneschi accodano e due indicizzano in linea.

## Cosa devi fare

Sei passi, tutti col codice nel piano:

- **2.1** creare `rag/tasks.py` — `indicizza_documento` (il task) e
  `accoda_indicizzazione` (l'unico punto di accodamento). **Copiare le docstring
  per intero**: contengono le verifiche fatte sul sorgente della 0.12.0 e le
  ragioni di tre decisioni;
- **2.2** `DocumentAdmin.save_model()` accoda invece di indicizzare, e si
  **cancellano due import diventati morti** — verificato con `grep` in
  pianificazione: la riga `from .services.exceptions import IngestionError` va
  via per intero, e `ingest_document` esce dall'import successivo (restano
  `compute_checksum` e `trova_duplicato`, che usa il form). Va aggiornata anche
  la nota di fase nell'intestazione del modulo, che annuncia questa modifica al
  futuro;
- **2.3** l'azione «Reindicizza» accoda N task invece di eseguire N ingestioni;
- **2.4** `views.documenti()` risponde **202** invece di 201, perde il ramo
  **422**, e la sua docstring viene riscritta. Anche qui cadono due import
  (`IngestionError`, `ingest_document`) e va corretta la terza riga
  dell'intestazione del modulo, che dice ancora che il caricamento è un
  involucro attorno a `ingest_document()`;
- **2.5** `manage.py ingest` guadagna `--async` e **resta sincrono per difetto**
  (cfr. decisione 12: non è un ciclo richiesta/risposta, e T-42/T-43 devono
  girare senza worker). I due `stdout.write` esistenti si **sostituiscono**, non
  si duplicano;
- **2.6** due docstring di `rag/services/ingestion.py` smettono di parlare di P5
  al futuro. **Solo le docstring**: nessuna riga di codice di quel file cambia.

## Attenzione a tre cose

1. **`str(risultato.id)`**: l'id del task è un UUID, e va nel log come stringa.
2. **Nessun `transaction.on_commit()` attorno all'`enqueue`** — la decisione 9 del
   piano spiega perché è corretto in entrambe le vie (admin in transazione, API
   no). Non «migliorarlo».
3. **Non inghiottire le eccezioni del task** (decisione 10): il worker le
   registra sulla riga `DBTaskResult` con il traceback, e `ingest_document()` ha
   già persistito il motivo leggibile sul documento. Sono due registrazioni con
   due scopi diversi.

## Come verifichi

Lo script `fase2.py` del piano (sezione «Fase 2 → Verify»), **dieci** sezioni.
**Nessuna è facoltativa**, e quattro sono quelle che rendono la fase non vuota:

- **punto 1** — la POST risponde 202 in meno di 2 s e il documento è `pending`
  con 0 segmenti (se qualcuno avesse lasciato `ingest_document()` nella vista,
  sarebbe `indexed` e ci vorrebbero secondi);
- **punto 3, CONTROLLO NEGATIVO** — dopo 3 s **senza worker** il documento è
  ancora `pending`;
- **punto 5** — un PDF senza testo dà **202**, e il fallimento compare **due
  volte**: `status: failed` + `error_message` sul documento, `FAILED` +
  `traceback` sulla riga del task;
- **punto 8** — `ingest --async` **accoda** (documento `pending`, una riga di
  task in più) e `ingest` senza opzione **indicizza in linea** (documento
  `indexed`, **nessuna** riga di task in più). Sono due asserzioni simmetriche, e
  la seconda è quella che protegge la decisione 12: se qualcuno rendesse il
  comando asincrono per difetto, T-42 e T-43 smetterebbero di funzionare senza
  worker. L'argomento si passa come `asincrono=True` — `async` è una parola
  chiave di Python e non può essere un `dest`.

Il worker si esercita con `call_command("db_worker", batch=True, reload=False,
startup_delay=False)`, che processa la coda ed esce. A freddo la prima chiamata
può costare ~18 s: non interromperla.

**Sui nomi degli stati del task**: leggere `TaskResultStatus` da `django_tasks` e
confrontare con `TaskResultStatus.SUCCESSFUL` / `.FAILED` invece di scrivere le
stringhe a mano (le migrazioni 0011 e 0018 di `django_tasks_db` sono rinomine di
stati: le stringhe cambiano fra versioni, i simboli no).

Poi, come sempre:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
git status --short
```

## Hai finito quando

- [ ] `fase2.py` stampa `FASE 2 OK`, con tutte e dieci le sezioni superate.
- [ ] Il tempo di accodamento misurato al punto 1 è **nel report in cifre**,
      accanto ai 14,53 s (a freddo) e 4,25 s (a caldo) misurati in P4. È la
      dimostrazione di RNF-03: senza quel confronto la fase non ha dimostrato
      nulla.
- [ ] Il controllo negativo del punto 3 è passato.
- [ ] `makemigrations --check --dry-run` → «No changes detected».
- [ ] `manage.py check` pulito, **senza import morti** lasciati in `admin.py` o
      `views.py` (controllarli a vista: `ingest_document` e `IngestionError` non
      servono più lì).
- [ ] `git grep -n "django\.tasks"` → nessun risultato.
- [ ] Corpus riportato allo stato iniziale: un solo documento, id 7, `indexed`.
- [ ] Sezione di report scritta, con l'esito reale del punto 5 (il doppio
      registro del fallimento) riportato per esteso.
- [ ] Commit: `P5: ingestione asincrona su coda Postgres (T-32)`

---

# Fase 3 — Errori uniformi, residui e osservabilità (T-34)

Sei il sub-agente della fase 3 del piano P5. Leggi
`plans/2026-07-25-1958-P5-plan.md`, sezioni 1–5 e «Fase 3», e attieniti ad esse.

Chiudi i **tre debiti accertati** che il report di P4 ha lasciato aperti, più due
che l'asincronia rende visibili. Le loro cause sono già verificate sul sorgente:
non serve riscoprirle, serve sistemarle.

## Cosa devi fare

Sei passi, tutti col codice nel piano:

- **3.1** creare `rag/errors.py` con `gestore_eccezioni()`;
- **3.2** `views.documento()` smette di usare `get_object_or_404` e solleva
  `NotFound(f"Nessun documento con id {pk}.")`;
- **3.3** `views` guadagna `_check_coda()`, quarto controllo di `/health`, che
  **non fa mai fallire** l'health check;
- **3.4** `REST_FRAMEWORK["EXCEPTION_HANDLER"]` punta al gestore;
- **3.5** `LOGGING` guadagna il pid nel formato e i logger `django_tasks` e
  `django_tasks_db`;
- **3.6** `rag/signals.py` guadagna `rimuovi_file`, che porta via il PDF da
  `MEDIA_ROOT` alla cancellazione del documento — **stessa disciplina** del
  receiver dei vettori che gli sta accanto: `on_commit`, errori loggati e non
  risollevati. Estendere anche l'intestazione del modulo, che oggi parla solo dei
  vettori.

## Due punti su cui non improvvisare

1. **Il backend della coda si legge da `settings.TASKS`**, non da
   `default_task_backend`: quest'ultimo è un `ConnectionProxy` e `type(...)`
   restituirebbe il proxy invece del backend. È scritto nella docstring del
   piano.
2. **Il gestore risponde JSON anche con `DEBUG=True`**, e quindi sulle rotte
   `/api/` non vedrai più la pagina di debug: è una scelta dichiarata
   (decisione 15), non un effetto collaterale. Lo stack resta sulla console
   grazie a `logger.exception`.

## Come verifichi

Lo script `fase3.py` del piano (sezione «Fase 3 → Verify»), sei sezioni. I due
controlli che rendono la fase non vuota:

- **punto 2** — un guasto inatteso dà **500 JSON** *e* il messaggio interno
  («guasto simulato») **non** trapela al client;
- **punto 3** — le condizioni **previste** non sono regredite: la domanda vuota
  resta 400 con il messaggio del dominio, `?status=inventato` resta 400. Un
  gestore scritto male le trasformerebbe in 500 e tutto il resto passerebbe
  ugualmente.

Contare i file in `MEDIA_ROOT` **prima e dopo**: al punto 4 il file di prova deve
sparire da solo, e alla fine il conteggio deve essere quello iniziale (6).

Il punto 4 cancella un documento che ha ancora il **task in coda**, e chiude
facendo girare il worker: è il ramo «documento sparito» di
`indicizza_documento()`, che si verifica così gratis e che deve concludersi con
**successo** — cancellare un documento è legittimo, non un guasto. Serve anche a
non lasciare alla fase 4 una coda con dentro un task pendente.

## Hai finito quando

- [ ] `fase3.py` stampa `FASE 3 OK`.
- [ ] Il testo inglese «No Document matches the given query.» non compare più in
      alcuna risposta (verificato con l'asserzione negativa del punto 1).
- [ ] `MEDIA_ROOT` ha lo stesso numero di file di prima della fase.
- [ ] Il dettaglio riportato da `/health` sotto «coda» è **copiato nel report**:
      è ciò che l'utente leggerà quando un documento resterà in attesa.
- [ ] `makemigrations --check --dry-run` → «No changes detected».
- [ ] `manage.py check` pulito.
- [ ] Sezione di report scritta.
- [ ] Commit: `P5: errori uniformi, 404 in italiano, file rimossi con il documento (T-34)`

---

# Fase 4 — Verifica di fase con worker vero, documentazione e report

Sei il sub-agente della fase 4 del piano P5. Leggi
`plans/2026-07-25-1958-P5-plan.md`, sezione «Fase 4», e attieniti ad essa.

**Non è previsto che tu scriva codice.** Se una verifica trova un difetto, lo
correggi, lo annoti nel report e lo committi **a parte**, prima del commit di
documentazione.

## Cosa devi fare

### Parte A — la verifica di fase, con `curl` vero e tre processi

Server (`runserver --noreload`), worker (`db_worker --no-reload
--no-startup-delay -v 2`) e `curl`. Se la password di `admin` non è nota, crea un
utente dedicato — è ciò che ha fatto P4 con `curl_p4`; il comando è nel piano.

Otto punti, dal 4.1 al 4.8. Riporta **comando e uscita**, non la parafrasi:

1. **4.1** upload → **202** in meno di un secondo, da confrontare con i 14,53 s /
   4,25 s di P4;
2. **4.2** il worker porta il documento a `indexed`;
3. **4.3** **CONTROLLO NEGATIVO**: a worker spento il documento resta `pending` e
   `/health` dichiara 1 in attesa; riacceso, viene preso;
4. **4.4** lo stato `processing` è **visibile** mentre dura — e se la finestra è
   troppo stretta per coglierlo, **dillo** invece di dichiararlo verificato;
5. **4.5** un PDF senza testo dà 202 e poi `failed` con il motivo (RF-10 dopo il
   cambio di contratto);
6. **4.6** deduplica (409) e autenticazione (401 con `WWW-Authenticate`,
   `/health` anonimo) non regredite;
7. **4.7** `POST /api/ask/` cita le fonti sul documento indicizzato **dall'altro
   processo**;
8. **4.8** RF-22 attraverso due processi: `top_k` cambiato da un terzo processo
   cambia le fonti **e torna indietro**, con i pid di server e worker invariati.

### Parte B — la documentazione

Sei documenti, elencati nel piano con il dettaglio di cosa cambia in ciascuno:
`README.md` (è quello che cambia di più — e attenzione, **non contiene ancora
esempi dell'API**: qui c'è da aggiungere, non da correggere), `ARCHITECTURE.md`,
`REQUIREMENTS.md` (RNF-03 non è più aperto), `PLAN.md`, `BACKLOG.md` (riga
«Stato: completata», con **anche** le attività tagliate e perché) e `CLAUDE.md`
(la sezione «Stato» dice ancora «Prossima: P4», e la riga «l'ingestione è
sincrona fino a P5» non è più vera).

Su `ARCHITECTURE.md` una precisazione che vale mezz'ora: **il diagramma di
sequenza di §4 descrive già la coda** — 202, `enqueue`, `status=processing`
scritto dal worker — perché era il bersaglio dichiarato. **Non va rifatto.**
Vanno cancellati i due paragrafi sotto di esso, che spiegano perché quel
diagramma non era ancora vero.

**`plans/` non si riscrive**: `docs/docs-manifest.yaml` lo esclude di proposito.
Il report di questa fase si **aggiunge**.

### Parte C — il report

`plans/2026-07-25-1958-P5-plan-report.md`, con la struttura dei report
precedenti: una sezione per fase con l'esito reale, gli scostamenti (che sono la
parte più utile da tramandare), le misure in cifre e una sezione «Consegna a P6»
che aggiorna la sezione 6 del piano con ciò che l'esecuzione ha scoperto.

## Pulizia prima di chiudere

- [ ] Documenti di prova cancellati; corpus a **un documento (id 7)**;
      `MEDIA_ROOT` ai **6 file** iniziali — e ora il receiver di T-34 deve
      avercelo riportato da solo, il che è di per sé una verifica.
- [ ] Le righe `DBTaskResult` **restano** (sono il registro della coda, come i
      `QueryLog` lo sono delle interrogazioni): riportarne il conteggio finale
      per stato.
- [ ] Server e worker spenti; nessun `llama-server` orfano.

## Hai finito quando

- [ ] Gli otto punti eseguiti con `curl` vero, comandi e uscite nel report.
- [ ] Il punto 4.3 superato: senza il controllo negativo la fase non dimostra
      l'asincronia.
- [ ] Le misure prima/dopo dell'upload riportate in cifre.
- [ ] Sei documenti riallineati; `plans/` intatto salvo l'aggiunta del report.
- [ ] `git grep -n "django\.tasks"` → nessun risultato.
- [ ] Commit: `docs: allinea la documentazione a P5` (più, se serve, un commit di
      correzione **prima**, con il difetto trovato descritto nel messaggio).
