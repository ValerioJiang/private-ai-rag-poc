# Prompt dei sub-agenti — Validazione dei PDF in ingresso

Compagno di [`2026-07-27-0759-Validazione-plan.md`](2026-07-27-0759-Validazione-plan.md).
Ogni prompt qui sotto si dà a **un sub-agente**, **in ordine**, e ciascuno va
eseguito **solo se il precedente ha chiuso verde**.

Il piano è un file su disco: i prompt **rimandano alle sue sezioni** invece di
ricopiarne 1 400 righe. È ciò che li rende autosufficienti senza renderli
illeggibili — il sub-agente legge il piano, non lo riceve a memoria.

---

# Prerequisites

Da verificare **una volta sola**, prima del primo sub-agente. Se uno non passa,
**fermarsi**: nessun prompt qui sotto è in grado di rimediare a un ambiente
mancante, e proseguire produrrebbe fallimenti che sembrano difetti del codice.

## Servizi

- [ ] PostgreSQL con pgvector sulla **5434** (verifica:
      `docker compose ps` mostra `db` come `Up (healthy)`)
- [ ] Se non lo è: `docker compose up -d db`
- [ ] Ollama nativo sull'host con i due modelli — **serve SOLO alla fase 5**
      (verifica: `ollama list` mostra `qwen2.5:7b-instruct` e `bge-m3`)

## Docker

- [ ] Un solo servizio serve: `db`. **Ollama non va containerizzato**
      (ARCHITECTURE §2) — verifica: `docker compose ps` non elenca alcun
      servizio `ollama`

## Ambiente

- [ ] Virtualenv presente (verifica: `Test-Path .venv\Scripts\python.exe`)
- [ ] `.env` presente (verifica: `Test-Path .env`; se manca: `cp .env.example .env`)
- [ ] **`OLLAMA_BASE_URL` NON deve essere puntata su una porta chiusa** da una
      sessione precedente (verifica: `echo $env:OLLAMA_BASE_URL` è vuoto o
      `http://localhost:11434`)

## Dipendenze

- [ ] Installate (verifica:
      `.venv\Scripts\python.exe -c "import pymupdf, django, rest_framework; print('ok')"`)
- [ ] **Nessuna dipendenza nuova va aggiunta da questo piano.** Se un
      sub-agente ne propone una, fermarsi: RNF-01 vieta qualunque percorso che
      possa far uscire testo dalla macchina

## Stato del codice

- [ ] Migrazioni applicate fino a `0005_excerpt_length` (verifica:
      `.venv\Scripts\python.exe manage.py showmigrations rag`)
- [ ] **Suite verde: `29 passed`** (verifica: `.venv\Scripts\python.exe -m pytest -q`)
- [ ] `git status --short` — sono attese e **da non annullare** le modifiche
      pendenti su `templates/rag/chiedi.html`, `rag/views.py`, `rag/urls.py`,
      `config/urls.py`, `config/settings/base.py` (pagina `/chiedi/` e
      `site_url = None`). **Non fanno parte di questo piano.**

## Lettura obbligatoria per ogni sub-agente

- [ ] `CLAUDE.md` — **lingua italiana ovunque**, docstring che spiegano il
      perché, RF-22, RNF-01, formato dei commit
- [ ] `plans/2026-07-27-0759-Validazione-plan.md` — il piano, **compreso il
      riquadro di revisione in testa**

---

## Analisi delle dipendenze fra le fasi

| Fase | Dipende da | Sub-agente separato? |
|---|---|---|
| 1 — configurazione | — | **Sì** |
| 2 — eccezioni e validazione | 1 (i campi esistono) | **Sì** |
| 3 — aggancio ai tre inneschi | 2 (la funzione esiste); usa fixture create in 2 | **Sì** |
| 4 — rapporto di testo | 1 (campo) + 2 (eccezione) | **Sì** |
| 5 — verifica end-to-end | tutte | **NO — operatore umano** |
| 6 — documentazione e commit | 5 | **Sì**, dopo la 5 |

**Nessun raggruppamento forzato.** Le fasi 2 e 3 scrivono sullo stesso file di
test (`rag/tests/test_validazione.py`) ma in **momenti diversi e in append**: il
prompt della 3 dichiara che le fixture della 2 esistono già, ed è l'unico punto
in cui il contesto attraversa un confine.

**La fase 5 non si delega.** Richiede Ollama vero, i due processi avviati a mano,
un browser sull'admin e attese di minuti: un sub-agente non ha modo di
condurla, e fingere che l'abbia fatta produrrebbe un report falso. La conduce
l'operatore, e i suoi esiti misurati entrano nel report prima della fase 6.

---

# Phase 1: I tre limiti diventano configurazione

Lavori sul repository `archetype-lab`, backend Django di un sistema RAG locale.
**Tutto in italiano**: docstring, commenti, `verbose_name`, messaggi. Le
docstring di questo progetto sono lunghe e spiegano il *perché*, citando i
requisiti per id.

**Leggi prima:**
1. `plans/2026-07-27-0759-Validazione-plan.md`, sezioni **§3.1, §3.2, §3.3,
   §3.11 e Phase 1** — contengono i frammenti di codice esatti da usare
2. `CLAUDE.md` — convenzioni
3. `rag/models/domain.py`, classe `KnowledgeBase`
4. `rag/models/profiles.py`, campo `RetrievalProfile.excerpt_length`
5. `rag/migrations/0005_excerpt_length.py` — lo stile della docstring di una
   migrazione qui
6. `rag/admin.py`, `KnowledgeBaseAdmin`

**Fai** i passi da **1.1 a 1.6** della Phase 1 del piano, con i frammenti che il
piano riporta. In sintesi: tre campi su `KnowledgeBase`
(`max_file_size_mb`, `max_page_count`, `min_text_page_ratio`), migrazione
**generata** con `makemigrations --name limiti_di_ammissione`, docstring in testa
alla migrazione, fieldset «Limiti di ammissione» nell'admin, `migrate`.

**Vincoli non negoziabili:**
- I tre default **disattivano** il controllo (`0`, `0`, `0.0`): nessuna misura
  dei report P2 → P6 deve diventare incomparabile
- La migrazione va **generata**, non scritta a mano (T-40)
- Se `makemigrations` produce operazioni **oltre** le tre `AddField`,
  **fermati e riferisci**: l'albero ha modifiche pendenti estranee al piano
- **Non** toccare `index_fingerprint()` (§3.11 spiega perché)

**Verifica:**
```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py showmigrations rag
.venv\Scripts\python.exe -m pytest -q
```

**Hai finito quando:** `0006_limiti_di_ammissione` è `[X]`, `--check --dry-run`
non rileva nulla di pendente, e `pytest -q` dà **29 passed** — invariato, perché
questa fase non aggiunge test.

**Riferisci:** i file toccati, il nome della migrazione, l'esito di `pytest`, e
qualunque scostamento dal piano con la sua ragione.

---

# Phase 2: Eccezioni e punto unico di validazione

Prosegui il lavoro sul repository `archetype-lab`. La fase 1 ha aggiunto tre
campi a `KnowledgeBase` (`max_file_size_mb`, `max_page_count`,
`min_text_page_ratio`) con la migrazione `0006`, già applicata.

**Leggi prima:**
1. `plans/2026-07-27-0759-Validazione-plan.md`, sezioni **§3.4, §3.5, §3.7,
   §3.9, §3.10, §5.4 e Phase 2** — i frammenti sono lì per intero
2. `rag/services/exceptions.py` — l'intero file: gerarchia e tono dei messaggi
3. `rag/services/loaders.py` — `load_pdf()`, e **perché**
   `pymupdf.FileNotFoundError` va catturata per nome
4. `rag/services/ingestion.py` — `compute_checksum()` e il suo `seek(0)`
5. `rag/tests/conftest.py` — fixture disponibili (`pipeline_predefinita`,
   `client_autenticato`, i tre PDF)

**Fai** i passi da **2.1 a 2.5** della Phase 2.

**Comincia dal passo 2.1**, che è una **verifica sperimentale** e non una
formalità: accerta che `pymupdf.open(stream=..., filetype="pdf")` funzioni sulla
1.28.0 installata **prima** di scrivere il codice che ci si appoggia. Se non
funziona, **fermati e riferisci**: il ripiego va deciso, non improvvisato.

Poi: tre eccezioni nuove (`FileTroppoGrande`, `TroppePagine`,
`PdfTestoInsufficiente`), `conta_pagine()` e `conta_pagine_da_percorso()` in
`loaders.py`, il nuovo modulo `rag/services/validation.py` con
`verifica_ammissibilita()` e `_conta_pagine_senza_caricare()`, e i **9 test** in
`rag/tests/test_validazione.py`.

**Vincoli non negoziabili:**
- **Il file grande non si carica in memoria** (§3.10): sopra 2,5 MB Django lo
  spoola su disco e si apre **per percorso**. La soglia è misurata, non scelta
- **Il puntatore torna sempre a zero**, anche quando il conteggio solleva: è il
  difetto pagato in P2, e ha un test dedicato
- Nessun valore di comportamento predefinito nel codice: i limiti arrivano
  **sempre** dalla `KnowledgeBase` (RF-22)
- Nessun test deve toccare la rete

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_validazione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Hai finito quando:** `test_validazione.py` dà **9 test verdi**, `pytest -q` dà
**38 passed**, e `conta_pagine()` e `conta_pagine_da_percorso()` concordano sullo
stesso PDF.

**Riferisci:** l'esito **testuale** del passo 2.1, i file creati, il conteggio
dei test, e ogni scostamento con la sua ragione.

---

# Phase 3: Aggancio ai tre inneschi

Prosegui sul repository `archetype-lab`. Esistono già: i tre campi su
`KnowledgeBase` (fase 1) e `rag/services/validation.py` con
`verifica_ammissibilita(file, knowledge_base)`, più
`rag/tests/test_validazione.py` con **9 test** e le fixture `pdf_di_tre_pagine`
e `_carica()`, che **riuserai senza ridefinirle** (fase 2).

**Leggi prima:**
1. `plans/2026-07-27-0759-Validazione-plan.md`, sezioni **§3.5, §3.6 e Phase 3**
2. `rag/views.py` — `documenti()`: l'ordine serializer → checksum → deduplica →
   save → accoda, e la docstring che dichiara i tre esiti
3. `rag/admin.py` — `DocumentAdminForm.clean()`: **il discriminante
   `isinstance(file, UploadedFile)` e la deduplica accanto a cui va messa la
   validazione**
4. `rag/management/commands/ingest.py` — cattura già `IngestionError` e lo
   traduce in `CommandError`: **riusa quella strada, non aggiungerne una seconda**
5. `rag/tests/test_api_ask.py` — stile dei test di vista

**Fai** i passi **3.1, 3.2, 3.3, 3.4, 3.4-bis, 3.5 e 3.5-bis** della Phase 3.

I tre inneschi che accettano un file **nuovo** sono `POST /api/documents/`,
`manage.py ingest` e **il salvataggio dall'admin**. L'azione «Reindicizza» resta
fuori: non riceve alcun file.

**Vincoli non negoziabili:**
- **La validazione va DOPO la deduplica**, in tutti e due i punti che la hanno
  (vista e form dell'admin): il 409 e la sua garanzia sono già provati, e
  anteporre il controllo li farebbe regredire (§3.6)
- **L'admin non è opzionale.** Ometterlo è il difetto che il ricontrollo del
  piano ha trovato: il flusso di CA-2 scavalcherebbe ogni limite
- Nel `clean()` dell'admin il file viene ora letto **due volte** (checksum e
  conteggio): il test `test_il_file_ammesso_dall_admin_si_salva_intero` deve
  accertare che il salvataggio non produca un file di zero byte
- Se `DocumentAdminForm` richiede campi obbligatori che il test non fornisce,
  **leggi il modello `Document`** e aggiungili: non indovinare

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_validazione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Hai finito quando:** `pytest -q` dà **42 passed**, il test dei residui
(`Document.objects.count() == 0` e nessun PDF in `MEDIA_ROOT`) è verde, e il test
del file salvato intero è verde.

**Riferisci:** i tre punti d'aggancio con il numero di riga, l'esito dei test, e
come il comando `ingest` gestiva già `IngestionError` — se fosse cambiato
rispetto a quanto il piano riporta, dillo.

---

# Phase 4: Il rapporto di pagine con testo

Prosegui sul repository `archetype-lab`. Esistono: i tre campi su
`KnowledgeBase`, l'eccezione `PdfTestoInsufficiente` in
`rag/services/exceptions.py` (fase 2) e la validazione sincrona agganciata ai
tre inneschi (fase 3).

**Leggi prima:**
1. `plans/2026-07-27-0759-Validazione-plan.md`, sezioni **§3.9 e Phase 4**
2. `rag/services/loaders.py` — `load_pdf()` e `PdfEstratto`: `page_count` è il
   totale del **file**, non delle pagine con testo (criterio **CA-2**)
3. `rag/services/ingestion.py`, riga ~225 — l'unica chiamata a `load_pdf()`
4. `rag/tests/test_ingestione.py` — le fixture `ingestione_senza_ollama` e
   `crea_documento`

**Fai** i passi da **4.1 a 4.4** della Phase 4.

**Vincoli non negoziabili:**
- **`PdfSenzaTesto` ha la precedenza** su `PdfTestoInsufficiente`: «nessuna
  pagina» è una diagnosi più precisa di «poche pagine», e ha un requisito suo
  (RF-10). Non invertire l'ordine dei due controlli
- `min_text_page_ratio` arriva **dalla base di conoscenza**, mai da una costante
  (RF-22). Il default `0.0` nella firma significa «controllo disattivato»
- **`page_count` resta il totale del file** anche dopo questa modifica: CA-2 non
  deve regredire, e c'è un'asserzione che lo verifica
- La fixture `crea_documento` ha firma **`(contenuto, nome)`**, col contenuto per
  primo: invertirli creerebbe un documento il cui file contiene il nome del file
- Prima di cambiare la firma di `load_pdf()`, **conferma con un grep** che abbia
  ancora un solo chiamante

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest rag/tests/test_ingestione.py -v
.venv\Scripts\python.exe -m pytest -q
```

**Hai finito quando:** `pytest -q` dà **44 passed**, la controprova (quota a zero
→ `indexed`, `page_count == 4`) è verde, e `error_message` contiene il conteggio
«1 pagine su 4».

**Riferisci:** l'esito dei test, il messaggio d'errore prodotto per esteso, e il
risultato del grep sui chiamanti di `load_pdf()`.

---

# Phase 5: Verifica end-to-end — **la conduce l'operatore, non un sub-agente**

> **Non delegare questa fase.** Richiede Ollama vero, i due processi avviati a
> mano, un browser sull'admin e attese di minuti. Un sub-agente non ha modo di
> condurla, e un report che la dichiarasse svolta senza esserlo varrebbe meno di
> nessun report.

Segui la **Phase 5, passi da 5.1 a 5.3** del piano: avvio dei due processi,
`/health`, i **sei controlli (a)–(f)** — dimensione, pagine, limiti a zero,
scansione parziale, rifiuto dall'admin, risalvataggio che non rivaluta — e la
**controprova 5.3** con `scripts/dimostrazione.ps1`, che deve dare gli stessi
esiti e tempi del README.

Annota l'output **vero** di ciascuno: è il materiale della fase 6.

**Se la controprova 5.3 differisce dal README, fermati:** significa che il
default non è neutro, e la fase 1 va rivista prima di documentare qualunque cosa.

---

# Phase 6: Documentazione, report e commit

Prosegui sul repository `archetype-lab`. Le fasi 1-4 sono implementate e la
suite dà **44 passed**; la fase 5 è stata condotta dall'operatore, e i suoi
esiti misurati ti vengono forniti insieme a questo prompt — **usa quelli, non
inventarne**.

**Leggi prima:**
1. `plans/2026-07-27-0759-Validazione-plan.md`, **Phase 5, passi 5.4-5.9**
2. `CLAUDE.md` — sezione «Convenzioni di lavoro» e formato dei commit
3. `README.md` — sezioni «API» e «Limiti noti»
4. `ARCHITECTURE.md` §7 · `REQUIREMENTS.md` §7 · `BACKLOG.md`
5. `plans/2026-07-25-2132-P6-plan-report.md` — il tono di un report qui: dice
   cosa è successo **davvero**, scostamenti compresi

**Fai** i passi da **5.4 a 5.9**: README (i tre limiti nella `POST` e, fra i
limiti noti, il cambio di contratto di §3.4), ARCHITECTURE (il punto unico di
validazione e perché la reindicizzazione non rivaluta), REQUIREMENTS (RF-31 e
RF-32, **verificando prima la numerazione esistente**), BACKLOG (fase **P7** con
T-44 → T-48), il report
`plans/2026-07-27-0759-Validazione-report.md`, e i commit.

**Vincoli non negoziabili:**
- **Il cambio di contratto va dichiarato, non addolcito**: con `max_page_count`
  attivo un PDF corrotto è respinto con 400 dalla `POST` invece che scoperto dal
  worker
- Nel report vanno **anche gli scostamenti**: i `plans/` sono un registro
  storico e non si riscrivono a posteriori
- **Non riscrivere le fasi P0 → P6** di `BACKLOG.md`: si aggiunge P7
- Commit **in italiano**, prefissati dalla fase e con gli id delle attività.
  **MAI il trailer `Co-Authored-By` né alcuna attribuzione a Claude**
- **Non committare** le modifiche pendenti estranee al piano (`/chiedi/`,
  `site_url = None`) insieme a queste: sono un lavoro diverso

**Verifica:**
```powershell
.venv\Scripts\python.exe -m pytest -q
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:1'
.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:\OLLAMA_BASE_URL
git log --oneline -5
git status --short
```

**Hai finito quando:** la suite dà **44 passed** e **identica** con
`OLLAMA_BASE_URL` su porta chiusa, i quattro documenti sono allineati, il report
esiste e dichiara gli scostamenti, e i commit non contengono alcuna attribuzione.
