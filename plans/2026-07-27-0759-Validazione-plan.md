# Validazione dei PDF in ingresso — piano di esecuzione

**Data:** 27/07/2026 · **Fase:** P7 (post-consegna) · **Attività:** T-44 → T-48

> Questo piano si esegue in una sessione nuova, **senza il contesto della
> discussione che l'ha prodotto**. Tutto ciò che serve è qui dentro.

> **Revisione del 27/07/2026 dopo un ricontrollo sul codice.** Sei correzioni,
> due delle quali avrebbero fatto fallire l'esecuzione:
>
> 1. **L'admin era escluso dalla validazione, e non doveva esserlo** (§3.5,
>    passi 3.4-bis e 3.5-bis). Era il difetto grave: il flusso di CA-2 avrebbe
>    scavalcato ogni limite.
> 2. Gli argomenti della fixture `crea_documento` erano **invertiti** nella
>    fase 4 — la firma è `(contenuto, nome)`.
> 3. Il conteggio delle pagine caricava l'intero file in memoria (§3.10): ora
>    sopra 2,5 MB si apre per percorso, e la soglia è **misurata**.
> 4. L'aritmetica dei test non tornava: i totali sono **38 → 42 → 44**.
> 5. Dichiarato il non-effetto su `index_fingerprint()` (§3.11), verificato sul
>    sorgente.
> 6. Confermato con grep che `load_pdf()` ha **un solo chiamante**, quindi
>    cambiarne la firma è sicuro.

---

## 1. Problema

L'ingestione accetta oggi qualunque PDF e scopre solo *a valle* se sia
lavorabile. Tre lacune, in ordine di gravità:

1. **Nessun limite di dimensione.** Un PDF da 500 MB viene accettato, scritto in
   `MEDIA_ROOT` e passato al worker, che ci resta per minuti **bloccando la coda
   per tutti gli altri documenti**. La coda è seriale.
2. **Nessun limite di pagine.** L'indicizzazione costa ~1 s per segmento
   (misurato in P2): un documento da 800 pagine non fallisce, occupa il worker
   per mezz'ora.
3. **Il testo parziale passa in silenzio.** `load_pdf()` solleva `PdfSenzaTesto`
   **solo se *tutte* le pagine sono vuote**. Un PDF con 90 pagine scansionate e
   10 di testo diventa `indexed` con `page_count: 100` e pochi segmenti: sembra
   riuscito, e nessuno segnala che il 90% del contenuto non è stato indicizzato.
   È il caso peggiore dei tre, perché è l'unico che non lascia traccia.

L'OCR è **fuori ambito** (REQUIREMENTS §8) e questo piano non lo introduce: si
tratta di **respingere** ciò che non è lavorabile, dicendo perché.

## 2. Obiettivo

Tre limiti configurabili dall'admin, applicati nel punto giusto del ciclo:

| Limite | Dove scatta | Cosa vede il client |
|---|---|---|
| dimensione massima del file | **sincrono**, all'ingresso | **400** (admin: errore sul campo), nessuna riga creata, nessun file scritto |
| numero massimo di pagine | **sincrono**, all'ingresso | **400** (admin: errore sul campo), nessuna riga creata, nessun file scritto |
| rapporto minimo di pagine con testo | **nel worker** | **202** → poi `failed` con il motivo |

Il confine è quello che il progetto ha già scelto altrove: **ciò che si sa
subito lo dice la `POST`, ciò che richiede lavoro lo scopre il worker.**

I due controlli sincroni valgono su **tutti e tre** gli inneschi che accettano un
file nuovo — `POST /api/documents/`, `manage.py ingest` e il salvataggio
dall'admin — da un unico punto di validazione (§3.5).

---

## 3. Context — decisioni prese e perché

### 3.1 I tre limiti sono configurazione, non costanti

**Vincolo non negoziabile: RF-22.** Un limite di dimensione o di pagine è un
parametro di *comportamento*: metterlo nel codice o in `config/settings/`
violerebbe il requisito centrale della traccia, che `CLAUDE.md` riassume come
«nessun parametro è una costante nel codice». Deve essere **una riga di
database modificabile dall'admin**, come `chunk_size` o `top_k`.

### 3.2 Stanno su `KnowledgeBase`

`KnowledgeBase` porta già la configurazione d'indice (`embedding_profile`,
`chunking_profile`) ed è l'entità a cui un documento appartiene. La politica di
ammissione è una proprietà della raccolta.

**Alternative scartate:**

- **`ChunkingProfile`** — riguarda *come si divide il testo già estratto*, non
  *quali file si accettano*. Per di più un profilo di segmentazione è condiviso
  fra basi di conoscenza diverse, che possono volere politiche diverse.
- **`config/settings/`** — violazione diretta di RF-22 (cfr. 3.1).
- **Un modello nuovo `IngestionPolicy`** — una tabella con tre colonne e una FK
  uno-a-uno con `KnowledgeBase` è cerimonia: aggiunge un join e una pagina
  d'admin per non separare nulla che sia realmente separabile.

### 3.3 Zero significa «nessun limite»

Tutti e tre i campi sono **additivi con default disattivato**: `0` per i due
interi, `0.0` per il rapporto. Le righe esistenti — comprese quelle create
dalla migrazione `0004` — mantengono quindi il comportamento attuale, e
**nessuna misura riportata nei report di P2 → P6 diventa incomparabile**. È la
stessa scelta della migrazione `0005`, e per la stessa ragione.

Conseguenza voluta: chi non configura nulla non si accorge di questa modifica.

### 3.4 Il conteggio delle pagine si fa **solo se un limite è configurato**

Contare le pagine richiede di aprire il PDF con PyMuPDF. È un'operazione a buon
mercato — legge il catalogo, **non** estrae il testo — ma ha una conseguenza sul
contratto: aprendo il file si scopre lì anche un **PDF corrotto o protetto**,
che oggi è scoperto dal worker.

Il contratto attuale è documentato ed esplicito (`rag/views.py`, docstring di
`documenti()`): *«IL 422 NON ESISTE PIÙ, e non è una svista»*. Riportare una
parte di quella diagnosi nella risposta sincrona è un cambio di contratto.

**Decisione:** il PDF si apre **solo quando `max_page_count > 0`**. In
configurazione predefinita il contratto resta identico a quello consegnato; il
cambio si attiva scegliendo il limite dall'admin, e va **dichiarato nel README**
insieme al limite. È la stessa forma del rilievo su CA-4 già presente nel
progetto: il filtro esiste, funziona, e si attiva scegliendo quella
configurazione.

**Alternativa scartata:** aprire sempre il PDF. Renderebbe la `POST` capace di
respingere subito un file corrotto — cosa desiderabile in sé — ma cambierebbe il
contratto **anche per chi non ha configurato nulla**, invalidando la sezione
«API» del README e la prova T-42 senza che nessuno l'abbia chiesto.

### 3.5 Un solo punto di validazione, chiamato da **tre** inneschi

Gli inneschi che accettano un file **nuovo** sono **tre**:

1. `POST /api/documents/`
2. `manage.py ingest <path>`
3. **il salvataggio dall'admin** — `DocumentAdminForm`

La validazione sta in **`rag/services/validation.py`** e la chiamano tutti e tre.

È la stessa forma per cui esiste un solo `ingest_document()` (P2) e un solo
`accoda_indicizzazione()` (P5): se ciascun innesco validasse per conto proprio,
la prima modifica ai limiti si dimenticherebbe in due punti su tre.

> **Correzione rispetto alla prima stesura di questo piano.** La versione
> iniziale escludeva l'admin, sostenendo che «lavora su un file già accettato in
> passato». **È falso**: caricare un documento nuovo dall'admin carica un file
> nuovo, ed è il flusso di CA-2 — la via che un amministratore usa per prima. Con
> quell'esclusione un PDF da 500 MB caricato dall'admin avrebbe scavalcato ogni
> limite. Rilevato dal ricontrollo sul codice, non dall'esecuzione.

Il punto d'aggancio per l'admin esiste già ed è provato: `DocumentAdminForm.clean()`
(`rag/admin.py`, righe ~341-374) è dove vive la **deduplica** per quella via, e
porta già il discriminante corretto —

```python
if not isinstance(file, UploadedFile):
    return dati
```

— che distingue un file **appena caricato** da un `FieldFile` già salvato
(«verificato che un FieldFile NON è un UploadedFile, mentre un upload lo è»,
dice il commento in loco). Agganciando lì la validazione si ottiene **gratis** la
semantica di §3.8: risalvare un documento senza toccarne il file non rivaluta
nulla.

> L'unico innesco che resta **fuori** è l'azione «Reindicizza», che non riceve
> alcun file: rilegge dal disco un documento già in archivio. Abbassare un limite
> non deve far fallire il riesame di ciò che è già stato accettato (§3.8).

### 3.6 La deduplica resta **prima** della validazione

Nella vista l'ordine diventa: `serializer` → **checksum e deduplica (409)** →
**validazione (400)** → scrittura → accodamento.

Motivo: il 409 e la sua garanzia («la riga NON viene creata e il file NON viene
scritto») sono già documentati, provati in P4 e coperti da test. Mettendo la
validazione prima, un file duplicato *e* troppo grande cambierebbe risposta da
409 a 400 e farebbe regredire una verifica esistente. Un duplicato è inoltre
l'informazione più azionabile: «ce l'hai già» batte «è troppo grande».

**Conseguenza dichiarata:** un duplicato che eccede i limiti riceve 409, non
400. È corretto: non viene indicizzato comunque.

### 3.7 `seek(0)` — il difetto già pagato una volta

`compute_checksum()` riporta il puntatore del file a zero, e la docstring della
vista spiega perché: *«senza quel seek(0) si salverebbe un PDF di zero byte,
accertato in P2»*.

La lettura per contare le pagine ha **esattamente lo stesso difetto**. Ogni
funzione che legge il file deve riportare il puntatore a zero prima di
restituire. È scritto nel codice della fase 2 e va verificato da un test.

### 3.8 Abbassare un limite non invalida l'archivio

I limiti valgono **all'ingresso**. I documenti già indicizzati restano
`indexed` anche se non passerebbero i limiti attuali, e la reindicizzazione non
li rivaluta. Non si introduce alcuna colonna «disallineato per validazione»: la
colonna `disallineato` esistente riguarda i profili d'*indice* (RF-25), che è
un'altra cosa, e sovraccaricarla la renderebbe illeggibile.

### 3.9 Casi limite decisi in pianificazione

| Caso | Comportamento |
|---|---|
| `max_file_size_mb = 0` | nessun controllo di dimensione |
| `max_page_count = 0` | nessun controllo di pagine, **e il PDF non viene aperto** (§3.4) |
| `min_text_page_ratio = 0.0` | nessun controllo di rapporto |
| PDF di **0 pagine** con `max_page_count > 0` | `PdfIllegibile` (già oggi: `FileDataError` su file vuoto) |
| Tutte le pagine vuote | resta **`PdfSenzaTesto`**, messaggio invariato: ha la priorità sul rapporto |
| Rapporto esattamente uguale alla soglia | **passa** — il confronto è `<`, non `<=` |
| `min_text_page_ratio = 1.0` | ammette solo PDF in cui **ogni** pagina ha testo |
| File esattamente pari al limite | **passa** — il confronto è `>`, non `>=` |

### 3.10 Il file grande non si carica in memoria — e la misura lo garantisce

`verifica_ammissibilita()` deve contare le pagine, e leggere l'intero file in
memoria significherebbe caricare in RAM **proprio il file che si vuole
respingere**: se è configurato solo `max_page_count`, un PDF da 500 MB verrebbe
letto tutto per scoprire che è troppo lungo.

**Misurato in pianificazione**, non dedotto: `FILE_UPLOAD_MAX_MEMORY_SIZE` vale
`2621440` (2,5 MB), quindi Django **spoola da sé su file temporaneo** ogni upload
più grande, e quei file espongono `temporary_file_path()` — presente su
`TemporaryUploadedFile`, **assente** su `SimpleUploadedFile` e
`InMemoryUploadedFile`. Da qui la regola:

- file **≤ 2,5 MB** → sta già in memoria, e leggerlo è innocuo *per costruzione*;
- file **> 2,5 MB** → c'è un percorso su disco, e PyMuPDF si apre **per nome**,
  senza caricare nulla;
- `manage.py ingest` → un percorso ce l'ha sempre.

Servono quindi due funzioni di conteggio — da byte e da percorso — e
`verifica_ammissibilita()` sceglie in base alla presenza di
`temporary_file_path()`. È la ragione per cui il controllo di dimensione va
comunque **prima** di quello di pagine.

### 3.11 Un effetto collaterale che NON c'è, verificato

`KnowledgeBase.index_fingerprint()` costruisce l'hash sui soli valori di
`embedding_profile` e `chunking_profile` (letto sul sorgente). I tre campi nuovi
**non entrano nell'impronta**, quindi modificare un limite **non** marca i
documenti già indicizzati come «disallineati» (RF-25).

È il comportamento voluto — un limite d'ingresso non invalida un indice — ed è
scritto qui perché al primo dubbio qualcuno «lo sistemerebbe»: aggiungere i
limiti al fingerprint farebbe apparire disallineato l'intero archivio al primo
ritocco di una soglia, senza che nulla dell'indice sia cambiato.

### 3.12 Assunzioni

- PyMuPDF sa aprire da stream: `pymupdf.open(stream=<bytes>, filetype="pdf")`.
  **Da verificare nella fase 2 sulla 1.28.0 installata**, non dare per scontato.
- `django.core.files.File` espone `.size` anche su un file aperto da disco: è
  ciò che permette a `manage.py ingest` di usare la stessa funzione della vista.
- Nessuna dipendenza nuova. Se una si rendesse necessaria, **fermarsi**: RNF-01
  vieta qualunque percorso che possa far uscire testo dalla macchina.

---

## 4. Prerequisites

Prima di eseguire qualunque fase, verificare:

### Servizi

- [ ] PostgreSQL con pgvector attivo sulla **5434** (verifica:
      `docker compose ps` mostra `db` come `Up (healthy)`)
- [ ] Se non lo è: `docker compose up -d db`
- [ ] Ollama nativo sull'host (verifica: `ollama list` mostra
      `qwen2.5:7b-instruct` e `bge-m3`) — **serve solo alla fase 5**

### Ambiente

- [ ] Virtualenv presente (verifica: `Test-Path .venv\Scripts\python.exe`)
- [ ] `.env` presente (verifica: `Test-Path .env`; se manca: `cp .env.example .env`)
- [ ] Dipendenze installate (verifica:
      `.venv\Scripts\python.exe -c "import pymupdf, django; print(pymupdf.__doc__, django.get_version())"`)

### Stato del codice

- [ ] Migrazioni applicate (verifica:
      `.venv\Scripts\python.exe manage.py showmigrations rag` mostra `0005_excerpt_length` con `[X]`)
- [ ] **Suite verde prima di cominciare** (verifica:
      `.venv\Scripts\python.exe -m pytest -q` → `29 passed`).
      Se non lo è, fermarsi: il piano assume quella base.
- [ ] Albero di lavoro pulito o modifiche note (verifica: `git status --short`).
      **Nota:** al momento della stesura sono pendenti e **non committate** le
      modifiche di `/chiedi/` (pagina HTML) e `admin.site.site_url = None`. Non
      fanno parte di questo piano e non vanno annullate.

### Lettura obbligatoria prima di iniziare

- [ ] `CLAUDE.md` — convenzioni, lingua italiana ovunque, RF-22, RNF-01
- [ ] `rag/services/exceptions.py` — gerarchia e registro dei messaggi

---

## 5. Design

### 5.1 Campi nuovi su `KnowledgeBase`

```
max_file_size_mb     PositiveIntegerField  default=0    0 = nessun limite
max_page_count       PositiveIntegerField  default=0    0 = nessun limite
min_text_page_ratio  FloatField            default=0.0  0.0 = disattivato, max 1.0
```

### 5.2 Eccezioni nuove

```
IngestionError
├── FileTroppoGrande        (nuova)  — sincrona, → 400
├── TroppePagine            (nuova)  — sincrona, → 400
└── PdfTestoInsufficiente   (nuova)  — nel worker, → failed
```

### 5.3 Flusso

```
POST /api/documents/
  ├─ serializer (estensione .pdf)            → 400
  ├─ checksum + deduplica                    → 409
  ├─ verifica_ammissibilita(file, kb)        → 400   ← NUOVO
  │    ├─ dimensione, se max_file_size_mb > 0
  │    └─ pagine,     se max_page_count   > 0   (apre il PDF)
  ├─ save() + accoda                         → 202
  └─ worker: ingest_document()
       └─ load_pdf(..., min_text_page_ratio) → failed  ← NUOVO

admin → DocumentAdminForm.clean()
  ├─ isinstance(file, UploadedFile)?  no → esce (non rivaluta)   [gia' presente]
  ├─ checksum + deduplica            → ValidationError           [gia' presente]
  └─ verifica_ammissibilita(file, kb) → ValidationError  ← NUOVO

manage.py ingest <path>
  └─ verifica_ammissibilita(File(aperto), kb) → CommandError  ← NUOVO

azione «Reindicizza»  → NESSUNA validazione (§3.8): nessun file nuovo
```

### 5.4 Dove si conta, e con quale funzione

| Chiamante | Il file è | Conteggio |
|---|---|---|
| upload ≤ 2,5 MB | in memoria | `conta_pagine(dati: bytes)` |
| upload > 2,5 MB | temporaneo su disco | `conta_pagine_da_percorso(...)` via `temporary_file_path()` |
| `manage.py ingest` | file di disco | `conta_pagine_da_percorso(...)` |

Cfr. §3.10: la soglia dei 2,5 MB è di Django, non una scelta di questo piano.

---

## 6. Implementation Phases

### Phase 1: I tre limiti diventano configurazione

**Status:** DONE

**Read first:**
- `rag/models/domain.py` — la classe `KnowledgeBase` (righe ~27-95): stile dei
  campi, `verbose_name` in italiano, `help_text` che spiega il perché
- `rag/models/profiles.py` — `RetrievalProfile.excerpt_length`, il campo
  aggiunto dalla `0005`: è il modello da imitare per tono e validatori
- `rag/migrations/0005_excerpt_length.py` — la docstring di una migrazione in
  questo progetto è lunga e spiega la ragione, non l'operazione
- `rag/admin.py` — `KnowledgeBaseAdmin` (righe ~240-260): struttura dei
  `fieldsets`

**Files to modify:**
- `rag/models/domain.py`
- `rag/admin.py`
- `rag/migrations/0006_limiti_di_ammissione.py` (nuovo, **generato**)

**Changes:**

- [x] **1.1** In `rag/models/domain.py`, aggiungere l'import dei validatori
  mancanti in testa al file (accanto a `FileExtensionValidator, RegexValidator`):

  ```python
  from django.core.validators import (
      FileExtensionValidator,
      MaxValueValidator,
      MinValueValidator,
      RegexValidator,
  )
  ```

- [x] **1.2** In `rag/models/domain.py`, dentro `class KnowledgeBase`, **dopo**
  il campo `chunking_profile` e **prima** di `class Meta`, aggiungere:

  ```python
      # --- limiti di ammissione (T-44, RF-22) ---------------------------
      # Stanno qui e non nel codice per la stessa ragione di excerpt_length:
      # sono parametri di COMPORTAMENTO, e RF-22 non ne ammette fuori dal
      # database. Stanno sulla base di conoscenza e non sul profilo di
      # segmentazione perche' riguardano QUALI FILE si accettano, non come si
      # divide il testo gia' estratto.
      #
      # Zero disattiva, ed e' il default: le righe esistenti — comprese quelle
      # create dalla 0004 — mantengono il comportamento con cui P2 → P6 hanno
      # misurato.
      max_file_size_mb = models.PositiveIntegerField(
          "dimensione massima (MB)",
          default=0,
          help_text=(
              "Oltre questa dimensione il caricamento e' respinto subito, con "
              "400 e senza creare ne' la riga ne' il file. Zero disattiva il "
              "controllo. La coda e' seriale: un file molto grande non fallisce, "
              "occupa il worker e ritarda tutti gli altri documenti."
          ),
      )
      max_page_count = models.PositiveIntegerField(
          "pagine massime",
          default=0,
          help_text=(
              "Oltre questo numero di pagine il caricamento e' respinto subito. "
              "Zero disattiva il controllo E il PDF non viene nemmeno aperto: "
              "con un limite attivo un file corrotto e' scoperto dalla POST "
              "invece che dal worker, ed e' un cambio di contratto dichiarato "
              "nel README. L'indicizzazione costa circa un secondo per segmento."
          ),
      )
      min_text_page_ratio = models.FloatField(
          "rapporto minimo di pagine con testo",
          default=0.0,
          validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
          help_text=(
              "Fra 0 e 1. Sotto questa quota di pagine con testo estraibile il "
              "documento e' marcato «Fallito» dal worker, con il conteggio nel "
              "motivo. Serve contro le scansioni PARZIALI: se NESSUNA pagina ha "
              "testo interviene gia' il controllo di RF-10. Zero disattiva. "
              "L'OCR resta fuori ambito (REQUIREMENTS §8)."
          ),
      )
  ```

- [x] **1.3** Generare la migrazione (**non scriverla a mano**, T-40):

  ```powershell
  .venv\Scripts\python.exe manage.py makemigrations rag --name limiti_di_ammissione
  ```

  Deve produrre `rag/migrations/0006_limiti_di_ammissione.py` con **tre**
  `AddField` e nessun'altra operazione. Se ne comparissero altre, fermarsi:
  significa che l'albero contiene modifiche ai modelli estranee a questo piano.

- [x] **1.4** Aggiungere in testa alla migrazione generata una docstring nello
  stile della `0005` (sostituire l'eventuale commento automatico):

  ```python
  """I limiti di ammissione dei PDF diventano configurazione (T-44, RF-22).

  Tre campi additivi su KnowledgeBase, tutti con il default che DISATTIVA il
  controllo: 0 per le due soglie intere, 0.0 per il rapporto. Le righe
  esistenti — compresa la base di conoscenza creata dalla 0004 — mantengono
  quindi esattamente il comportamento con cui P2 → P6 hanno misurato, e nessuna
  cifra riportata nei report diventa incomparabile.

  E' la stessa scelta della 0005, per la stessa ragione: una migrazione
  additiva con default neutro non chiede nulla a chi aggiorna, e il
  comportamento nuovo si attiva scegliendolo dall'admin.

  Reversibile senza perdite: RemoveField toglie tre colonne i cui unici
  consumatori sono i controlli di rag/services/validation.py.

  Generata con makemigrations, non scritta a mano (T-40).
  """
  ```

- [x] **1.5** In `rag/admin.py`, dentro `KnowledgeBaseAdmin`, aggiungere un
  fieldset **fra** «Configurazione d'indice» e `TRACCIAMENTO`:

  ```python
          (
              "Limiti di ammissione",
              {
                  "fields": ("max_file_size_mb", "max_page_count", "min_text_page_ratio"),
                  "description": (
                      "Valgono ai NUOVI caricamenti. I documenti gia' indicizzati "
                      "restano tali anche se non passerebbero i limiti attuali, e "
                      "la reindicizzazione non li rivaluta. Zero disattiva il "
                      "singolo controllo."
                  ),
              },
          ),
  ```

- [x] **1.6** Applicare la migrazione:

  ```powershell
  .venv\Scripts\python.exe manage.py migrate
  ```

**Verify:**
```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py showmigrations rag
.venv\Scripts\python.exe -m pytest -q
```

**Phase Complete When:**
- [x] `showmigrations rag` mostra `0006_limiti_di_ammissione` con `[X]`
- [x] `makemigrations --check --dry-run` non rileva modifiche pendenti
- [x] `pytest -q` → **29 passed** (nessun test nuovo ancora, nessuna regressione)
- [x] L'admin della base di conoscenza mostra il fieldset «Limiti di ammissione»

---

### Phase 2: Eccezioni e punto unico di validazione

**Status:** DONE

**Read first:**
- `rag/services/exceptions.py` — l'intero file: gerarchia, tono dei messaggi
  («scritti per un amministratore che li legge nell'admin»)
- `rag/services/loaders.py` — `load_pdf()`: come si aprono i PDF, e perché
  `pymupdf.FileNotFoundError` va catturata per nome
- `rag/services/ingestion.py` — `compute_checksum()`: il `seek(0)` di §3.7

**Files to modify:**
- `rag/services/exceptions.py`
- `rag/services/loaders.py`
- `rag/services/validation.py` (nuovo)
- `rag/tests/test_validazione.py` (nuovo)

**Changes:**

- [x] **2.1** **Verificare l'assunzione** di §3.12 prima di scrivere il codice
  che la usa:

  ```powershell
  .venv\Scripts\python.exe -c "import pymupdf; d=pymupdf.open(); d.new_page(); b=d.tobytes(); d.close(); s=pymupdf.open(stream=b, filetype='pdf'); print('pagine:', s.page_count); s.close()"
  ```

  Deve stampare `pagine: 1`. Se fallisce, **fermarsi e annotarlo nel report**:
  il ripiego è scrivere il file su disco prima di contare, che però va deciso e
  non improvvisato.

- [x] **2.2** In `rag/services/exceptions.py`, aggiungere le tre eccezioni
  **dopo** `PdfSenzaTesto` e prima di `DocumentoDuplicato`:

  ```python
  class FileTroppoGrande(IngestionError):
      """Il file eccede KnowledgeBase.max_file_size_mb (T-44).

      Condizione SINCRONA: la scopre chi carica, non il worker. La coda e'
      seriale, e un file molto grande non fallisce — occupa il worker e ritarda
      ogni altro documento.
      """


  class TroppePagine(IngestionError):
      """Il PDF eccede KnowledgeBase.max_page_count (T-44).

      Sincrona come FileTroppoGrande. Il conteggio richiede di aprire il file,
      quindi si esegue SOLO se il limite e' configurato: cfr. la docstring di
      verifica_ammissibilita().
      """


  class PdfTestoInsufficiente(IngestionError):
      """Troppe pagine senza testo rispetto a min_text_page_ratio (T-44).

      NON e' PdfSenzaTesto, che copre il caso in cui NESSUNA pagina abbia testo
      (RF-10). Questa copre la scansione PARZIALE, che oggi passa in silenzio:
      un PDF di 100 pagine di cui 10 con testo diventa «Indicizzato» con 10
      segmenti, e nulla dice che il 90% non e' stato indicizzato.

      Asincrona: richiede l'estrazione, quindi la scopre il worker.
      """
  ```

- [x] **2.3** In `rag/services/loaders.py`, aggiungere `conta_pagine()` in fondo
  al file (l'import di `PdfIllegibile` c'è già):

  ```python
  def conta_pagine(dati: bytes) -> int:
      """Numero di pagine di un PDF in memoria, senza estrarne il testo.

      Esiste per il controllo SINCRONO di T-44: chi carica deve sapere subito
      se il file eccede il limite, e leggere il catalogo delle pagine costa
      millisecondi contro i secondi dell'estrazione.

      Le clausole ricalcano quelle di load_pdf(), e per la stessa ragione:
      pymupdf.FileDataError e pymupdf.FileNotFoundError derivano da
      RuntimeError e NON da OSError (verificato sulla 1.28.0), quindi vanno
      catturate per nome o sfuggirebbero come guasto inatteso. Qui non serve
      FileNotFoundError — non c'e' alcun percorso — ma serve FileDataError, che
      copre file corrotto e file di zero byte.

      Solleva:
          PdfIllegibile: non apribile come PDF, o protetto da password.
      """
      try:
          documento = pymupdf.open(stream=dati, filetype="pdf")
      except pymupdf.FileDataError as exc:
          raise PdfIllegibile(
              f"Il file non e' un PDF leggibile ({type(exc).__name__}). "
              "Verificare che non sia corrotto o troncato."
          ) from exc

      with documento:
          if documento.needs_pass:
              raise PdfIllegibile(
                  "Il PDF e' protetto da password: non e' possibile estrarne il testo."
              )
          return documento.page_count


  def conta_pagine_da_percorso(percorso: str) -> int:
      """Come conta_pagine(), ma SENZA caricare il file in memoria.

      Esiste perche' il caso peggiore del controllo e' proprio il file grande:
      leggerlo tutto per scoprire che e' troppo lungo caricherebbe in RAM
      esattamente cio' che si vuole respingere (§3.10 del piano). PyMuPDF
      aperto per nome legge il catalogo e non il contenuto.

      Django spoola da se' gli upload oltre FILE_UPLOAD_MAX_MEMORY_SIZE
      (2 621 440 byte, MISURATO in pianificazione) su un file temporaneo che
      espone temporary_file_path(): sopra quella soglia un percorso c'e'
      sempre, e sotto la lettura in memoria e' innocua per costruzione.

      Solleva:
          PdfIllegibile: non apribile come PDF, o protetto da password.
      """
      try:
          documento = pymupdf.open(percorso)
      except pymupdf.FileNotFoundError as exc:
          # Come in load_pdf(): OMBREGGIA la builtin e NON la sottoclassa,
          # deriva da RuntimeError. Va prima di FileDataError.
          raise PdfIllegibile(f"File non trovato: {percorso}") from exc
      except pymupdf.FileDataError as exc:
          raise PdfIllegibile(
              f"Il file non e' un PDF leggibile ({type(exc).__name__}). "
              "Verificare che non sia corrotto o troncato."
          ) from exc

      with documento:
          if documento.needs_pass:
              raise PdfIllegibile(
                  "Il PDF e' protetto da password: non e' possibile estrarne il testo."
              )
          return documento.page_count
  ```

- [x] **2.4** Creare `rag/services/validation.py`:

  ```python
  """Ammissibilita' dei file in ingresso (T-44, RF-22).

  UN SOLO PUNTO DI VALIDAZIONE, chiamato da DUE inneschi: POST /api/documents/
  e `manage.py ingest <path>`. E' la stessa forma per cui esiste un solo
  ingest_document() (P2) e un solo accoda_indicizzazione() (P5): se ciascun
  innesco validasse per conto proprio, la prima modifica ai limiti si
  dimenticherebbe in uno dei due.

  NON la chiamano la reindicizzazione ne' il salvataggio dall'admin: lavorano
  su file gia' accettati, e abbassare un limite non deve far fallire il
  riesame di cio' che e' gia' in archivio.

  I limiti sono righe di database (KnowledgeBase), non costanti: RF-22. Qui non
  c'e' alcun valore predefinito di comportamento, e non va introdotto.
  """

  from __future__ import annotations

  from .exceptions import FileTroppoGrande, TroppePagine
  from .loaders import conta_pagine, conta_pagine_da_percorso

  BYTE_PER_MB = 1024 * 1024
  """Fattore di conversione, non un parametro: 1 MB e' 1 MB. Non e' RF-22."""


  def verifica_ammissibilita(file, knowledge_base) -> None:
      """Verifica dimensione e numero di pagine PRIMA di scrivere alcunche'.

      `file` e' un oggetto in stile django.core.files.File: servono `.size` e
      `.read()`. Vale sia per un caricamento HTTP sia per un file aperto da
      disco, ed e' cio' che permette ai tre inneschi di condividere questa
      funzione.

      IL PDF SI APRE SOLO SE max_page_count > 0. Aprirlo sempre farebbe
      scoprire alla POST anche i file corrotti, che oggi sono di competenza del
      worker: sarebbe un cambio del contratto documentato in views.documenti()
      («IL 422 NON ESISTE PIU'») imposto anche a chi non ha configurato nulla.
      Con il limite attivo il cambio c'e', ed e' dichiarato nel README.

      IL PUNTATORE TORNA A ZERO. Chi legge un file caricato deve riavvolgerlo,
      o il salvataggio successivo scriverebbe zero byte: e' il difetto
      accertato in P2 su compute_checksum(), e leggere per contare le pagine ha
      esattamente la stessa forma.

      Solleva:
          FileTroppoGrande: oltre max_file_size_mb.
          TroppePagine: oltre max_page_count.
          PdfIllegibile: il file non si apre (solo se il conteggio viene svolto).
      """
      limite_mb = knowledge_base.max_file_size_mb
      if limite_mb:
          dimensione = file.size
          if dimensione > limite_mb * BYTE_PER_MB:
              raise FileTroppoGrande(
                  f"Il file pesa {dimensione / BYTE_PER_MB:.1f} MB e supera il "
                  f"limite di {limite_mb} MB fissato per la base di conoscenza "
                  f"«{knowledge_base.name}». Il limite si modifica dall'admin."
              )

      limite_pagine = knowledge_base.max_page_count
      if limite_pagine:
          pagine = _conta_pagine_senza_caricare(file)
          if pagine > limite_pagine:
              raise TroppePagine(
                  f"Il documento ha {pagine} pagine e supera il limite di "
                  f"{limite_pagine} fissato per la base di conoscenza "
                  f"«{knowledge_base.name}». L'indicizzazione costa circa un "
                  f"secondo per segmento, e la coda e' seriale."
              )


  def _conta_pagine_senza_caricare(file) -> int:
      """Conta le pagine dalla via meno costosa disponibile (§3.10 del piano).

      temporary_file_path() esiste su TemporaryUploadedFile — cioe' sugli
      upload che Django ha spoolato su disco perche' oltre 2,5 MB — e sui file
      aperti da percorso che il comando `ingest` incarta in django.core.files.File.
      Non esiste su SimpleUploadedFile ne' su InMemoryUploadedFile (verificato).

      Quando non c'e', il file sta gia' in memoria per definizione e leggerlo
      non aggiunge occupazione: e' il ramo innocuo, non il ramo pigro.
      """
      percorso = getattr(file, "temporary_file_path", None)
      if callable(percorso):
          return conta_pagine_da_percorso(percorso())

      nome = getattr(file, "path", None)   # django.core.files.File su disco
      if nome:
          return conta_pagine_da_percorso(nome)

      try:
          return conta_pagine(file.read())
      finally:
          # Nel `finally`: anche se conta_pagine solleva, chi ha chiamato deve
          # ritrovare il file riavvolto. E' il difetto accertato in P2 su
          # compute_checksum().
          file.seek(0)
  ```

- [x] **2.5** Creare `rag/tests/test_validazione.py`:

  ```python
  """Ammissibilita' dei file in ingresso (T-44).

  Nessuno di questi test tocca la rete: la validazione non parla ne' con Ollama
  ne' con pgvector. Il PDF lo costruisce pymupdf, la stessa libreria che il
  sistema usa per leggerlo.
  """

  import pytest

  from rag.services.exceptions import (
      FileTroppoGrande,
      PdfIllegibile,
      TroppePagine,
  )
  from rag.services.loaders import conta_pagine
  from rag.services.validation import verifica_ammissibilita


  @pytest.fixture
  def pdf_di_tre_pagine() -> bytes:
      import pymupdf

      documento = pymupdf.open()
      for numero in range(3):
          pagina = documento.new_page()
          pagina.insert_text((72, 100), f"Pagina {numero + 1} con del testo.")
      dati = documento.tobytes()
      documento.close()
      return dati


  def _carica(dati: bytes, nome: str = "prova.pdf"):
      from django.core.files.uploadedfile import SimpleUploadedFile

      return SimpleUploadedFile(nome, dati, content_type="application/pdf")


  # --- conta_pagine ----------------------------------------------------

  def test_conta_pagine_legge_il_totale_senza_estrarre_il_testo(pdf_di_tre_pagine):
      assert conta_pagine(pdf_di_tre_pagine) == 3


  def test_conta_pagine_rifiuta_cio_che_non_e_un_pdf():
      with pytest.raises(PdfIllegibile):
          conta_pagine(b"Questo non e' un PDF.")


  def test_conta_pagine_da_percorso_da_lo_stesso_risultato(
      pdf_di_tre_pagine, tmp_path
  ):
      """Le due vie devono concordare: sopra i 2,5 MB si usa quella per
      percorso, e una discordanza renderebbe il limite dipendente dalla
      dimensione del file invece che dal suo contenuto."""
      from rag.services.loaders import conta_pagine_da_percorso

      percorso = tmp_path / "tre-pagine.pdf"
      percorso.write_bytes(pdf_di_tre_pagine)
      assert conta_pagine_da_percorso(str(percorso)) == conta_pagine(pdf_di_tre_pagine) == 3


  # --- limiti disattivati ----------------------------------------------

  def test_con_i_limiti_a_zero_non_si_verifica_nulla(
      pipeline_predefinita, pdf_di_tre_pagine
  ):
      """Il default della 0006 non cambia il comportamento consegnato."""
      kb = pipeline_predefinita.knowledge_base
      assert kb.max_file_size_mb == 0
      assert kb.max_page_count == 0
      verifica_ammissibilita(_carica(pdf_di_tre_pagine), kb)


  def test_con_le_pagine_a_zero_il_pdf_non_viene_nemmeno_aperto(
      pipeline_predefinita
  ):
      """Un file illeggibile passa la validazione se il limite non c'e'.

      E' la decisione di §3.4 del piano: senza limite il contratto resta quello
      consegnato, e a scoprire un PDF corrotto e' il worker.
      """
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 0
      verifica_ammissibilita(_carica(b"non un pdf"), kb)


  # --- dimensione -------------------------------------------------------

  def test_un_file_oltre_il_limite_di_dimensione_e_respinto(
      pipeline_predefinita, pdf_di_tre_pagine
  ):
      kb = pipeline_predefinita.knowledge_base
      kb.max_file_size_mb = 1
      grande = _carica(b"x" * (2 * 1024 * 1024))
      with pytest.raises(FileTroppoGrande) as exc:
          verifica_ammissibilita(grande, kb)
      assert "2.0 MB" in str(exc.value)
      assert kb.name in str(exc.value)


  def test_il_file_esattamente_al_limite_passa(pipeline_predefinita):
      """Il confronto e' `>`, non `>=`: il caso limite e' ammesso (§3.9)."""
      kb = pipeline_predefinita.knowledge_base
      kb.max_file_size_mb = 1
      kb.max_page_count = 0
      verifica_ammissibilita(_carica(b"x" * (1024 * 1024)), kb)


  # --- pagine -----------------------------------------------------------

  def test_un_pdf_oltre_il_limite_di_pagine_e_respinto(
      pipeline_predefinita, pdf_di_tre_pagine
  ):
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 2
      with pytest.raises(TroppePagine) as exc:
          verifica_ammissibilita(_carica(pdf_di_tre_pagine), kb)
      assert "3 pagine" in str(exc.value)


  def test_il_puntatore_torna_a_zero_dopo_il_conteggio(
      pipeline_predefinita, pdf_di_tre_pagine
  ):
      """Il difetto gia' pagato in P2 su compute_checksum: senza il seek(0)
      il salvataggio successivo scriverebbe zero byte."""
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 10
      file = _carica(pdf_di_tre_pagine)
      verifica_ammissibilita(file, kb)
      assert file.tell() == 0
      assert file.read() == pdf_di_tre_pagine
  ```

**Verify:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_validazione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Phase Complete When:**
- [x] `test_validazione.py` — **9 test verdi**
- [x] `pytest -q` → **38 passed** (29 + 9), nessuna regressione
- [x] Il controllo 2.1 su `pymupdf.open(stream=...)` è stato eseguito e annotato
- [x] `conta_pagine()` e `conta_pagine_da_percorso()` concordano sullo stesso PDF

---

### Phase 3: Aggancio ai tre inneschi

**Status:** DONE

**Read first:**
- `rag/views.py` — `documenti()` (righe ~151-223): l'ordine serializer →
  checksum → deduplica → save → accoda, e la docstring che dichiara i tre esiti
- `rag/management/commands/ingest.py` — come il comando apre il file e chiama
  l'ingestione
- `rag/admin.py` — `DocumentAdminForm.clean()` (righe ~341-374): **il
  discriminante `isinstance(file, UploadedFile)` e la deduplica accanto a cui va
  messa la validazione**. È il punto del rilievo di §3.5
- `rag/tests/test_api_ask.py` — stile dei test di vista con `client_autenticato`

**Files to modify:**
- `rag/views.py`
- `rag/management/commands/ingest.py`
- `rag/admin.py`
- `rag/tests/test_validazione.py`

**Changes:**

- [x] **3.1** In `rag/views.py`, aggiungere agli import da `.services`:

  ```python
  from .services.exceptions import IngestionError, LlmNonRaggiungibile, QueryError
  from .services.validation import verifica_ammissibilita
  ```

- [x] **3.2** In `documenti()`, **dopo** il blocco della deduplica (subito dopo
  il `return` del 409) e **prima** di `documento = Document(...)`, inserire:

  ```python
      # I limiti di ammissione (T-44), DOPO la deduplica: il 409 e la sua
      # garanzia — niente riga, niente file — sono gia' documentati e provati,
      # e anteporre questo controllo cambierebbe la risposta a un duplicato che
      # eccede anche un limite. Un duplicato e' anche la risposta piu' utile:
      # «ce l'hai gia'» batte «e' troppo grande».
      try:
          verifica_ammissibilita(file, kb)
      except IngestionError as exc:
          # 400 e non 422: e' una condizione della richiesta, scoperta prima di
          # qualunque scrittura. Nessuna riga «Fallito» resta in elenco.
          return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
  ```

- [x] **3.3** Aggiornare la docstring di `documenti()`: nell'elenco dei tre
  esiti, sostituire la riga del 400 con

  ```
      - 400 file mancante, non PDF, base di conoscenza inesistente, oppure
        oltre i limiti di ammissione della base (T-44: dimensione, pagine).
        Nessuna riga viene creata e nessun file scritto;
  ```

  e aggiungere in fondo alla docstring:

  ```
      IL 422 NON TORNA. Con max_page_count configurato la POST apre il PDF e
      puo' quindi scoprire un file corrotto, che senza quel limite resta di
      competenza del worker: la risposta e' comunque 400 e non 422, perche' la
      condizione e' nota PRIMA di ogni scrittura. Il cambio di contratto e'
      dichiarato nel README insieme al limite.
  ```

- [x] **3.4** In `rag/management/commands/ingest.py`, applicare la stessa
  verifica **prima** di creare il `Document` (oggi alla riga ~129,
  `documento = Document(knowledge_base=kb, original_filename=percorso.name)`).

  **Struttura già presente, verificata in pianificazione:** il comando importa
  `IngestionError` (riga 15), lo cattura e lo traduce in `CommandError`
  (righe ~97-100), e apre il file con `percorso.open("rb")` (righe ~119 e ~130).
  Non serve quindi alcuna gestione nuova: basta che la chiamata avvenga dentro
  il blocco già protetto da quella `except`. **Leggere il file prima di
  scrivere**, per confermare che sia ancora così.

  ```python
  from django.core.files import File

  from rag.services.validation import verifica_ammissibilita

  # ... prima di `documento = Document(knowledge_base=kb, ...)`:
          # Stessa validazione della POST, dallo stesso punto (T-44): un limite
          # che valesse solo via HTTP sarebbe un limite che non vale.
          with percorso.open("rb") as aperto:
              verifica_ammissibilita(File(aperto), kb)
  ```

  `django.core.files.File` fornisce `.size` anche su un file di disco, ed è ciò
  che permette ai tre inneschi di condividere `verifica_ammissibilita()`.

- [x] **3.4-bis** In `rag/admin.py`, agganciare la validazione a
  `DocumentAdminForm.clean()`. Aggiungere gli import

  ```python
  from .services.exceptions import IngestionError
  from .services.validation import verifica_ammissibilita
  ```

  e, **dopo** il blocco della deduplica e **prima** del `return dati` finale:

  ```python
          # I limiti di ammissione anche da qui (T-44). L'admin NON e' un
          # innesco «su file gia' accettato»: caricare un documento nuovo
          # dall'admin carica un file NUOVO, ed e' il flusso di CA-2. Senza
          # questo blocco un PDF enorme scavalcherebbe ogni limite proprio
          # dalla via che un amministratore usa per prima.
          #
          # Sta DOPO la deduplica, come nella vista, e sotto la guardia
          # isinstance(file, UploadedFile) gia' presente qualche riga sopra: e'
          # quella a garantire che risalvare un documento senza toccarne il file
          # non lo rivaluti (§3.8), senza alcun controllo nuovo.
          try:
              verifica_ammissibilita(file, kb)
          except IngestionError as exc:
              raise forms.ValidationError({"file": str(exc)}) from exc
  ```

  **Attenzione all'ordine delle letture.** `compute_checksum(file)` è già stato
  chiamato poche righe sopra e riavvolge il file; `verifica_ammissibilita()`
  riavvolge a sua volta. Sono **due** letture dove prima ce n'era una: il test
  3.5-bis deve accertare che il file salvato dopo un `clean()` riuscito non sia
  di zero byte. È esattamente il difetto pagato in P2.

- [x] **3.5** Aggiungere in coda a `rag/tests/test_validazione.py`:

  ```python
  # --- aggancio alla POST ------------------------------------------------

  @pytest.mark.django_db
  def test_la_post_respinge_con_400_e_non_crea_nulla(
      client_autenticato, pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
  ):
      """400, e soprattutto: nessuna riga e nessun file. E' il punto del
      controllo sincrono — un limite che lasciasse residui non varrebbe la pena."""
      from rag.models import Document

      settings.MEDIA_ROOT = tmp_path
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 2
      kb.save()

      risposta = client_autenticato.post(
          "/api/documents/",
          {"file": _carica(pdf_di_tre_pagine, "troppe-pagine.pdf")},
          format="multipart",
      )

      assert risposta.status_code == 400
      assert "3 pagine" in risposta.json()["detail"]
      assert Document.objects.count() == 0
      assert list(tmp_path.rglob("*.pdf")) == []


  @pytest.mark.django_db
  def test_la_post_resta_202_quando_i_limiti_sono_disattivati(
      client_autenticato, pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path, monkeypatch
  ):
      """Controprova: la 0006 non cambia il comportamento consegnato."""
      from rag import views

      settings.MEDIA_ROOT = tmp_path
      monkeypatch.setattr(views, "accoda_indicizzazione", lambda documento: "task-finto")

      risposta = client_autenticato.post(
          "/api/documents/",
          {"file": _carica(pdf_di_tre_pagine, "ammesso.pdf")},
          format="multipart",
      )

      assert risposta.status_code == 202
  ```

- [x] **3.5-bis** Aggiungere i due test dell'admin, che sono la ragione del
  rilievo di §3.5:

  ```python
  # --- aggancio all'admin ------------------------------------------------

  @pytest.mark.django_db
  def test_il_form_dell_admin_respinge_un_file_oltre_i_limiti(
      pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
  ):
      """Senza questo aggancio l'admin — il flusso di CA-2 — scavalcherebbe
      ogni limite: e' il difetto che il ricontrollo del piano ha trovato."""
      from rag.admin import DocumentAdminForm

      settings.MEDIA_ROOT = tmp_path
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 2
      kb.save()

      form = DocumentAdminForm(
          data={"knowledge_base": kb.pk},
          files={"file": _carica(pdf_di_tre_pagine, "troppe-pagine.pdf")},
      )

      assert not form.is_valid()
      assert "3 pagine" in " ".join(form.errors["file"])


  @pytest.mark.django_db
  def test_il_file_ammesso_dall_admin_si_salva_intero(
      pipeline_predefinita, pdf_di_tre_pagine, settings, tmp_path
  ):
      """Due letture del file dove prima ce n'era una (checksum + conteggio):
      senza i seek(0) si salverebbe un PDF di zero byte, difetto di P2."""
      from rag.admin import DocumentAdminForm

      settings.MEDIA_ROOT = tmp_path
      kb = pipeline_predefinita.knowledge_base
      kb.max_page_count = 10
      kb.max_file_size_mb = 5
      kb.save()

      form = DocumentAdminForm(
          data={"knowledge_base": kb.pk},
          files={"file": _carica(pdf_di_tre_pagine, "ammesso.pdf")},
      )

      assert form.is_valid(), form.errors
      documento = form.save()
      assert documento.file.size == len(pdf_di_tre_pagine)
  ```

  **Se `DocumentAdminForm` richiede altri campi obbligatori**, aggiungerli a
  `data`: leggere il modello `Document` prima di scrivere il test, non indovinare.

**Verify:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_validazione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Phase Complete When:**
- [x] `pytest -q` → **42 passed** (38 + 2 della POST + 2 dell'admin), nessuna
      regressione sui test di P6 — *poi **43**, col test di regressione sul ramo
      del percorso: cfr. lo scostamento nel report*
- [x] Il test che conta i residui (`Document.objects.count() == 0` e nessun PDF
      in `MEDIA_ROOT`) è verde: è la garanzia che dà senso al controllo sincrono
- [x] Il test del file salvato intero è verde: le due letture non si pestano
- [x] `manage.py ingest` su un file oltre limite esce con errore leggibile e
      **senza** creare la riga
- [ ] **Prova manuale dall'admin**: caricare un PDF oltre il limite di pagine
      mostra l'errore sul campo *file* e non crea la riga — **rimandata alla
      fase 5**, che è dell'operatore: richiede sessione e superutente. Coperta a
      livello di form da `test_il_form_dell_admin_respinge_un_file_oltre_i_limiti`

---

### Phase 4: Il rapporto di pagine con testo

**Status:** NOT_STARTED

**Read first:**
- `rag/services/loaders.py` — `load_pdf()` e `PdfEstratto`: `page_count` è il
  totale del **file**, non delle pagine con testo (criterio CA-2)
- `rag/services/ingestion.py` — il punto in cui `load_pdf()` viene chiamata
- `rag/tests/test_ingestione.py` — la fixture `ingestione_senza_ollama` e
  `crea_documento`

**Files to modify:**
- `rag/services/loaders.py`
- `rag/services/ingestion.py`
- `rag/tests/test_ingestione.py`

**Changes:**

- [ ] **4.1** In `rag/services/loaders.py`, cambiare la firma di `load_pdf()`:

  ```python
  def load_pdf(
      path: str,
      *,
      metadata_extra: dict | None = None,
      min_text_page_ratio: float = 0.0,
  ) -> PdfEstratto:
  ```

  Il default `0.0` **non è un parametro di comportamento nascosto** (RF-22): è
  «controllo disattivato», e il valore vero arriva sempre dal chiamante, che lo
  legge dalla base di conoscenza. Annotarlo nella docstring.

- [ ] **4.2** In `load_pdf()`, sostituire il blocco finale:

  ```python
      if not pagine:
          raise PdfSenzaTesto(
              f"Nessun testo estraibile dalle {page_count} pagine del documento. "
              "E' probabilmente una scansione senza OCR: l'OCR e' dichiarato fuori "
              "ambito (REQUIREMENTS §8), quindi questo file non e' indicizzabile."
          )

      # Scansione PARZIALE (T-44). L'ordine conta: PdfSenzaTesto ha la
      # precedenza, perche' «nessuna pagina» e' una diagnosi piu' precisa di
      # «poche pagine» e ha un requisito suo (RF-10).
      if min_text_page_ratio and page_count:
          rapporto = len(pagine) / page_count
          if rapporto < min_text_page_ratio:
              raise PdfTestoInsufficiente(
                  f"Solo {len(pagine)} pagine su {page_count} contengono testo "
                  f"estraibile ({rapporto:.0%}), sotto la quota minima del "
                  f"{min_text_page_ratio:.0%} fissata per questa base di "
                  f"conoscenza. E' probabilmente una scansione parziale senza "
                  f"OCR: le pagine mancanti non finirebbero nell'indice, e la "
                  f"loro assenza non sarebbe visibile nelle risposte."
              )
      return PdfEstratto(pagine=pagine, page_count=page_count)
  ```

  Aggiornare l'import in testa al file:

  ```python
  from .exceptions import PdfIllegibile, PdfSenzaTesto, PdfTestoInsufficiente
  ```

  e la sezione `Solleva:` della docstring di `load_pdf()`.

- [ ] **4.3** In `rag/services/ingestion.py`, passare il valore alla chiamata di
  `load_pdf()` (adattare al nome della variabile del documento):

  ```python
      estratto = load_pdf(
          document.file.path,
          metadata_extra=metadata_extra,
          # Dal database, mai una costante: RF-22.
          min_text_page_ratio=document.knowledge_base.min_text_page_ratio,
      )
  ```

- [ ] **4.4** Aggiungere a `rag/tests/test_ingestione.py`:

  ```python
  @pytest.fixture
  def pdf_meta_scansionato() -> bytes:
      """Quattro pagine, una sola con testo: rapporto 0,25.

      E' il caso che oggi passa in silenzio — «Indicizzato» con un solo
      segmento su quattro pagine.
      """
      import pymupdf

      documento = pymupdf.open()
      prima = documento.new_page()
      prima.insert_text((72, 100), "L'unica pagina con del testo estraibile.")
      for _ in range(3):
          documento.new_page()
      dati = documento.tobytes()
      documento.close()
      return dati


  def test_una_scansione_parziale_sotto_la_quota_lascia_stato_fallito(
      ingestione_senza_ollama, crea_documento, pdf_meta_scansionato
  ):
      """Il buco piu' insidioso dei tre: senza questo controllo il documento
      diventa «Indicizzato» e nulla dice che tre pagine su quattro sono fuori."""
      from rag.models import Document
      from rag.services.exceptions import PdfTestoInsufficiente
      from rag.services.ingestion import ingest_document

      # ATTENZIONE all'ordine: la fixture e' _crea(contenuto, nome), col
      # CONTENUTO per primo. Invertirli creerebbe un documento il cui file
      # contiene il nome del file.
      documento = crea_documento(pdf_meta_scansionato, "meta-scansionato.pdf")
      kb = documento.knowledge_base
      kb.min_text_page_ratio = 0.5
      kb.save()

      with pytest.raises(PdfTestoInsufficiente):
          ingest_document(documento)

      documento.refresh_from_db()
      assert documento.status == Document.Status.FAILED
      assert "1 pagine su 4" in documento.error_message


  def test_con_la_quota_a_zero_la_scansione_parziale_viene_indicizzata(
      ingestione_senza_ollama, crea_documento, pdf_meta_scansionato
  ):
      """Controprova: il default non cambia il comportamento consegnato."""
      from rag.models import Document
      from rag.services.ingestion import ingest_document

      # ATTENZIONE all'ordine: la fixture e' _crea(contenuto, nome), col
      # CONTENUTO per primo. Invertirli creerebbe un documento il cui file
      # contiene il nome del file.
      documento = crea_documento(pdf_meta_scansionato, "meta-scansionato.pdf")
      assert documento.knowledge_base.min_text_page_ratio == 0.0

      ingest_document(documento)

      documento.refresh_from_db()
      assert documento.status == Document.Status.INDEXED
      # page_count resta il totale del FILE, non delle pagine con testo (CA-2).
      assert documento.page_count == 4
  ```

**Verify:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_ingestione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Phase Complete When:**
- [ ] `pytest -q` → **44 passed**
- [ ] Il test della controprova (quota a zero → `indexed`, `page_count == 4`)
      è verde: dimostra che il default non cambia nulla
- [ ] `error_message` sul documento contiene il conteggio «1 pagine su 4»
- [ ] `load_pdf()` ha **un solo chiamante** (`ingestion.py`, verificato in
      pianificazione con grep su tutto `rag/`): se ne comparissero altri,
      aggiornarli prima di chiudere la fase

---

### Phase 5: Verifica end-to-end e documentazione

**Status:** NOT_STARTED

> Questa fase **richiede Ollama vero** e i due processi. È la verifica che ogni
> piano di fase di questo progetto prevede: comandi reali su dati reali, con
> l'output nel report.

**Read first:**
- `README.md` — sezioni «API» e «Limiti noti»: è lì che va dichiarato il cambio
  di contratto di §3.4
- `ARCHITECTURE.md` §7 — dove sono descritte ingestione e gestione degli errori
- `REQUIREMENTS.md` §7 — la tabella dei criteri di accettazione
- `BACKLOG.md` — struttura di una fase, con stato e attività

**Files to modify:**
- `README.md`, `ARCHITECTURE.md`, `REQUIREMENTS.md`, `BACKLOG.md`
- `plans/2026-07-27-0759-Validazione-report.md` (nuovo)

**Changes:**

- [ ] **5.1** Avviare l'ambiente e verificare i presupposti:

  ```powershell
  docker compose up -d db
  .venv\Scripts\python.exe manage.py runserver      # terminale 1
  .venv\Scripts\python.exe manage.py db_worker      # terminale 2
  curl.exe --max-time 30 http://localhost:8000/health
  ```

- [ ] **5.2** Eseguire i quattro controlli, **annotando l'output vero**:

  | # | Cosa | Atteso |
  |---|---|---|
  | a | `max_file_size_mb = 1` dall'admin, caricare un PDF > 1 MB | **400**, nessuna riga, nessun file in `MEDIA_ROOT` |
  | b | `max_page_count = 2`, caricare il PDF di esempio (3 pagine) | **400** con «3 pagine» |
  | c | limiti a **0**, ricaricare lo stesso PDF | **202**, poi `indexed` — nulla è cambiato |
  | d | `min_text_page_ratio = 0.5` su un PDF metà scansionato | **202**, poi `failed` con il conteggio nel motivo |
  | e | **dall'admin**, caricare lo stesso PDF di (b) con `max_page_count = 2` | errore sul campo *file*, nessuna riga creata |
  | f | **dall'admin**, risalvare un documento esistente senza toccare il file, con i limiti abbassati sotto le sue misure | salva senza errori: non si rivaluta ciò che è già in archivio (§3.8) |

  Per (a) generare un PDF grande senza scaricare nulla (RNF-01):

  ```powershell
  .venv\Scripts\python.exe -c "import pymupdf; d=pymupdf.open(); [d.new_page().insert_text((72,100), 'riempimento '*2000) for _ in range(400)]; d.save('grande.pdf'); d.close()"
  ```

- [ ] **5.3** **Controprova obbligatoria:** rieseguire il ciclo di consegna con
      i limiti a zero e verificare che i tempi e gli esiti non differiscano da
      quelli del README. Se differiscono, il default non è neutro e la fase 1 va
      rivista.

  ```powershell
  .\scripts\dimostrazione.ps1 -Utente <utente> -Password <password>
  ```

- [ ] **5.4** `README.md`: aggiungere i tre limiti alla descrizione della `POST`
      e, **in «Limiti noti»**, il cambio di contratto di §3.4 — con
      `max_page_count` attivo un PDF corrotto è respinto con **400** dalla
      `POST` invece che scoperto dal worker. Dichiararlo, non addolcirlo.

- [ ] **5.5** `ARCHITECTURE.md`: descrivere il punto unico di validazione e
      **perché la reindicizzazione non rivaluta** (§3.8).

- [ ] **5.6** `REQUIREMENTS.md`: registrare i requisiti nuovi (proposta:
      **RF-31** limiti di ammissione configurabili, **RF-32** rifiuto delle
      scansioni parziali) e verificare la numerazione esistente prima di
      assegnarli.

- [ ] **5.7** `BACKLOG.md`: aggiungere la fase **P7** con T-44 → T-48, stato e
      quanto è stato realmente svolto. **Non riscrivere le fasi precedenti.**

- [ ] **5.8** Scrivere `plans/2026-07-27-0759-Validazione-report.md`: cosa è
      successo davvero, **scostamenti compresi**. I `plans/` sono un registro
      storico e non si riscrivono a posteriori.

- [ ] **5.9** Commit, in italiano, con gli id delle attività e **senza alcuna
      attribuzione a Claude** (né trailer `Co-Authored-By`). Esempio:

  ```
  P7: limiti di ammissione dei PDF come configurazione (T-44, T-45)
  P7: rifiuto delle scansioni parziali sotto quota (T-46)
  docs: allinea la documentazione a P7
  ```

**Verify:**
```powershell
.venv\Scripts\python.exe -m pytest -q
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:1'
.venv\Scripts\python.exe -m pytest -q          # deve passare identica
Remove-Item Env:\OLLAMA_BASE_URL
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
git status --short
```

**Phase Complete When:**
- [ ] `pytest -q` → **44 passed**, e **identica** con `OLLAMA_BASE_URL` su porta
      chiusa: nessun test nuovo tocca la rete
- [ ] I sei controlli (a)–(f) hanno un esito **misurato** nel report
- [ ] La controprova 5.3 conferma che a limiti zero nulla è cambiato
- [ ] `README.md`, `ARCHITECTURE.md`, `REQUIREMENTS.md`, `BACKLOG.md` allineati
- [ ] Il report esiste e dichiara gli scostamenti
- [ ] Nessuna dipendenza nuova in `requirements.in` (RNF-01)

---

## 7. Rischi noti

| Rischio | Mitigazione |
|---|---|
| `pymupdf.open(stream=...)` non si comporta come atteso | **Passo 2.1**, prima di scriverci sopra |
| Il default non è neutro e una misura del README cambia | Controprova **5.3** con `dimostrazione.ps1` |
| `manage.py ingest` gestisce `IngestionError` diversamente dal previsto | **3.4** impone di leggere il comando e riusare la sua strada |
| Il conteggio pagine rallenta la `POST` | Si attiva solo con il limite configurato; leggere il catalogo non estrae il testo. **Misurare in 5.2 (b)** e riportarlo |
| Un `AddField` inatteso nella migrazione | **1.3** impone di fermarsi se ne compaiono altri: l'albero ha modifiche pendenti su `/chiedi/` |
| Un innesco dimenticato scavalca i limiti | **Già accaduto** in prima stesura, sull'admin (§3.5). Gli inneschi sono tre e uno solo è escluso, con la ragione scritta. Il controllo 5.2 (e) lo prova a mano |
| Due letture del file nel `clean()` dell'admin → PDF di zero byte | Difetto già pagato in P2. Test **3.5-bis** sul `file.size` dopo il salvataggio |
| Il file grande viene caricato in RAM per contarne le pagine | Risolto in §3.10: sopra 2,5 MB Django spoola su disco e si apre per percorso. Sotto, la lettura è innocua per costruzione |

## 8. Fuori ambito

- **OCR** — resta fuori (REQUIREMENTS §8). Qui si respinge, non si converte.
- **Limiti globali** validi per tutte le basi di conoscenza: sarebbero un
  valore fuori dal database, cioè RF-22.
- **Rivalutazione dell'archivio** rispetto ai limiti nuovi (§3.8).
- **Antivirus, sniffing del content-type oltre l'estensione, PDF/A**: nessuno è
  richiesto, e ciascuno porterebbe una dipendenza nuova da vagliare contro
  RNF-01.
