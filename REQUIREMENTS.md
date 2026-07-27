# Analisi funzionale iniziale — Sistema RAG in Django

Documento di analisi redatto a partire dalla traccia della prova tecnica.
Precede le scelte tecniche descritte in [ARCHITECTURE.md](ARCHITECTURE.md) e la
pianificazione in [PLAN.md](PLAN.md).

Ogni voce riporta la **fonte**, per distinguere ciò che la traccia impone da ciò
che è stato dedotto o aggiunto per scelta progettuale:

| Fonte | Significato |
|---|---|
| **T** | Esplicito nel testo della traccia |
| **D** | Derivato: necessario perché un requisito **T** sia realizzabile |
| **S** | Scelta progettuale: non richiesto, aggiunto con motivazione |

---

## 1. Obiettivo

Realizzare il **backend** di un'applicazione Django che, tramite le librerie
LangChain, implementi un sistema RAG (Retrieval-Augmented Generation) capace di
rispondere a domande in linguaggio naturale sul contenuto di documenti PDF,
generando le risposte con un **LLM privato locale**.

Il sistema deve essere **riconfigurabile dal pannello di amministrazione Django
senza interventi sul codice**.

## 2. Attori

| Attore | Descrizione | Canale |
|---|---|---|
| **Amministratore** | Configura il comportamento del sistema, carica e gestisce i documenti, ispeziona lo storico | Admin Django |
| **Client interrogante** | Pone domande e riceve risposte con le fonti. Non essendo richiesto un frontend, è un consumatore di API | API REST |
| **Operatore** | Esegue ingestione e interrogazioni da riga di comando, per test e automazione | Comandi `manage.py` |
| **Worker** | Processo che esegue l'indicizzazione in modo asincrono | Interno |

## 3. Requisiti funzionali

### 3.1 Gestione della base di conoscenza

| ID | Requisito | Fonte |
|---|---|---|
| **RF-01** | Il sistema deve permettere il caricamento di **uno o più documenti PDF**, che costituiscono la base di conoscenza | T |
| **RF-02** | Ogni documento è associato a una base di conoscenza identificata, per permettere raccolte documentali distinte | S |
| **RF-03** | Il sistema deve **estrarre il testo** dal PDF conservando il riferimento alla pagina di origine | T (estrazione), D (pagina) |
| **RF-04** | Il testo estratto deve essere **suddiviso in segmenti** secondo parametri configurabili | T |
| **RF-05** | I segmenti devono essere **indicizzati** in una struttura che ne permetta il recupero per similarità semantica | T |
| **RF-06** | Lo stato di elaborazione di ogni documento deve essere osservabile (`in attesa`, `in elaborazione`, `indicizzato`, `fallito`) e, in caso di errore, deve riportare il motivo | D |
| **RF-07** | Deve essere possibile **rielaborare** un documento già caricato, senza doverlo ricaricare | D |
| **RF-08** | L'eliminazione di un documento deve rimuovere anche i suoi segmenti, i relativi vettori e il file caricato da `MEDIA_ROOT` | D |
| **RF-09** | Il caricamento dello stesso file nella stessa base di conoscenza deve essere rilevato e segnalato, non duplicato | S |
| **RF-10** | Un PDF privo di testo estraibile (scansione senza OCR) deve produrre un errore esplicito, non un documento indicizzato vuoto | S |
| **RF-31** | I limiti di ammissione di un file — dimensione massima, numero massimo di pagine, quota minima di pagine con testo — devono essere **configurabili dall'admin**, con un valore che disattiva il singolo controllo | S |
| **RF-32** | Un PDF in cui **solo una parte** delle pagine ha testo estraibile deve poter essere rifiutato, con il conteggio nel motivo, invece di essere indicizzato a metà senza che nulla lo segnali | S |

**RF-31 e RF-32 sono di P7** (T-44) e continuano la numerazione da RF-30 invece
di inserirsi dopo RF-10: gli identificativi sono riferimenti stabili — citati
nel codice, nei test e nei report delle fasi precedenti — e rinumerare li
invaliderebbe tutti.

I tre limiti sono campi di `KnowledgeBase` (migrazione
`0006_limiti_di_ammissione`): `max_file_size_mb` (predefinito 0),
`max_page_count` (0) e `min_text_page_ratio` (0.0, fra 0 e 1). **Zero disattiva
il singolo controllo**, quindi il comportamento predefinito resta quello
consegnato a P6 e nessuna misura dei report precedenti diventa incomparabile.
Sono righe di database e non costanti: è RF-22 applicato ai limiti.

**Dove scattano.** Dimensione e numero di pagine sono controlli **sincroni** —
li vede chi carica, con **400**, senza che la riga sia creata né il file
scritto — e valgono per i tre inneschi che accettano un file *nuovo*:
`POST /api/documents/`, `manage.py ingest` e il salvataggio dall'admin. Tutti e
tre stanno **dopo la deduplica**, che conserva il suo 409 (RF-09): a un
duplicato che ecceda anche un limite, «ce l'hai già» resta la risposta più
utile. L'azione «Reindicizza» **non** valida, perché non riceve un file nuovo:
abbassare un limite non deve far fallire il riesame di ciò che è già in
archivio. La quota di pagine con testo è invece **asincrona** — richiede
l'estrazione, quindi la scopre il worker, e il documento passa a *fallito* con
il conteggio nel motivo («Solo 1 pagine su 4…»).

RF-32 **non sostituisce RF-10**: quello copre il PDF in cui *nessuna* pagina ha
testo, questo la scansione **parziale**, che prima diventava «Indicizzato»
senza che nulla segnalasse le pagine mancanti. **L'OCR resta fuori ambito**
(§8): il documento viene rifiutato, non recuperato.

Il disegno per esteso — i tre inneschi, il punto unico di validazione e il
motivo per cui i limiti non entrano nell'impronta d'indice — sta in
**ARCHITECTURE §4.1**.

**Un cambio di contratto, da non addolcire.** Con `max_page_count > 0` la
`POST` apre il PDF per contarne le pagine, e scopre quindi anche un file
**corrotto**: risponde 400 invece di lasciarlo al worker. Il contratto
predefinito è invariato solo perché il predefinito è 0.

**Un effetto che non c'è**, verificato sul sorgente: i tre campi non entrano in
`KnowledgeBase.index_fingerprint()`, quindi modificare un limite **non** marca
disallineati i documenti già indicizzati (RF-25). È voluto — i limiti governano
l'ammissione, non la forma dell'indice.

### 3.2 Interrogazione

| ID | Requisito | Fonte |
|---|---|---|
| **RF-11** | Il sistema deve ricevere una **domanda in linguaggio naturale** e restituire una **risposta pertinente basata sul contenuto dei PDF** | T |
| **RF-12** | La generazione della risposta deve avvenire tramite un **LLM privato locale** | T |
| **RF-13** | La risposta deve essere accompagnata dalle **fonti utilizzate**: documento, pagina, estratto del segmento e punteggio di similarità | S |
| **RF-14** | Quando il recupero non individua contesto pertinente, il sistema deve dichiararlo esplicitamente anziché produrre una risposta non fondata | S |
| **RF-15** | Deve essere possibile indicare quale configurazione (pipeline) utilizzare per una determinata interrogazione; in assenza di indicazione si usa quella predefinita | S |
| **RF-16** | Ogni interrogazione deve essere registrata con domanda, risposta, segmenti recuperati con relativo punteggio e tempi di esecuzione | S |

### 3.3 Configurazione dal pannello di amministrazione

> Requisito centrale della traccia: *«Vogliamo poter modificare il comportamento
> del sistema dall'admin senza mettere mano al codice.»*

| ID | Requisito | Fonte |
|---|---|---|
| **RF-17** | Dall'admin deve essere possibile selezionare il **modello LLM** da utilizzare | T |
| **RF-18** | Dall'admin devono essere configurabili i **parametri di generazione**: temperatura, top-p, top-k, numero massimo di token, timeout | T |
| **RF-19** | Dall'admin devono essere configurabili le impostazioni di **elaborazione dei documenti**: strategia di segmentazione, dimensione del segmento, sovrapposizione | T |
| **RF-20** | Dall'admin devono essere configurabili le impostazioni di **retrieval**: strategia di ricerca, numero di segmenti recuperati, soglie di punteggio | T |
| **RF-21** | Dall'admin deve essere modificabile il **prompt** utilizzato per la generazione | S |
| **RF-22** | Le modifiche alla configurazione devono avere effetto **senza riavviare l'applicazione e senza modificare il codice** | T |
| **RF-23** | Il sistema deve permettere la **coesistenza di più configurazioni complete** e il passaggio dall'una all'altra, per poterle confrontare | S |
| **RF-24** | I parametri devono essere **validati** al salvataggio; una configurazione incoerente non deve poter essere salvata | D |
| **RF-25** | I parametri che richiedono una reindicizzazione devono essere **distinti** da quelli applicabili a caldo, e il sistema deve segnalare i documenti disallineati rispetto alla configurazione corrente | D |
| **RF-26** | All'installazione deve esistere una **configurazione predefinita funzionante**, così che il sistema sia utilizzabile senza configurazione manuale iniziale | S |

### 3.4 Accesso alle funzionalità

| ID | Requisito | Fonte |
|---|---|---|
| **RF-27** | Le funzionalità devono essere esposte via **API REST**: caricamento documento, stato del documento, interrogazione, elenco delle configurazioni | T (libertà di scelta) |
| **RF-28** | Le stesse operazioni devono essere disponibili come **comandi di gestione**, per prova e automazione | S |
| **RF-29** | Il caricamento dei documenti e la loro reindicizzazione devono essere azionabili **anche dall'admin** | D |
| **RF-30** | L'accesso all'admin deve essere autenticato | D |

**Dal 27/07/2026 la porta d'ingresso è una sola**, `/accedi/`, e smista per
ruolo: chi ha `is_staff` al pannello di gestione, gli altri alla pagina di
interrogazione. È lavoro **fuori piano**, che `BACKLOG.md` traccia come **T-49**
e tiene separato da T-44 → T-48 per non far sembrare pianificato ciò che non lo
è stato. Prima `LOGIN_URL` puntava al login *dell'admin*, che rifiuta chi
non è staff: un utente ordinario **non poteva entrare affatto**, nemmeno per
raggiungere la pagina fatta per lui. Non era una decisione, era una porta
mancante. Lo smistamento è instradamento e non autorizzazione — nessuno guadagna
un permesso che non aveva, l'admin continua a difendersi da sé e **RF-30 non
regredisce**.

**`GET /api/ask/` rimanda ora a `/chiedi/`** invece di rispondere 405: chi
apriva l'endpoint col browser trovava un errore corretto per un client di
un'API e privo di via d'uscita. Il **`POST` è invariato**, ed è l'unico verbo
che risponde a domande.

RNF-01 resta intatto, e **verificato**: nelle pagine rese non c'è alcun
riferimento esterno — nessun CDN, nessun font remoto, nessuna libreria. Il tema
condiviso è **incluso** nel template e non servito come file statico, così ogni
pagina resta una sola richiesta.

## 4. Requisiti non funzionali

| ID | Requisito | Fonte |
|---|---|---|
| **RNF-01** | **Nessun contenuto documentale deve lasciare il perimetro privato**, in nessuna fase: né in generazione, né in calcolo degli embedding, né in eventuale tracciamento | T (esteso, cfr. ARCHITECTURE §1; garanzia e limiti in §9) |
| **RNF-02** | L'ambiente deve essere avviabile in modo riproducibile con un numero minimo di comandi | D |
| **RNF-03** | L'indicizzazione non deve bloccare il ciclo richiesta/risposta HTTP | D |
| **RNF-04** | Gli errori devono essere gestiti, persistiti e ispezionabili, non solo registrati nei log | D |
| **RNF-05** | Le componenti critiche (segmentazione, costruzione della catena dalla configurazione, macchina a stati dell'ingestione, endpoint di interrogazione) devono essere coperte da test automatici | S |
| **RNF-06** | Deve essere fornito un **README** con le istruzioni per avviare e provare il progetto | T |
| **RNF-07** | Devono essere fornite **note sulle scelte architetturali**, con compromessi e limiti | T |

## 5. Vincoli

| ID | Vincolo | Fonte |
|---|---|---|
| **V-01** | Il progetto deve essere sviluppato in **Django** | T |
| **V-02** | Devono essere utilizzate le librerie **LangChain** | T |
| **V-03** | L'LLM deve essere **privato**, con **motivazione della scelta** documentata | T |
| **V-04** | Il **frontend non è richiesto** | T |
| **V-05** | Consegna: codice sorgente, README, note architetturali | T |
| **V-06** | Termine: **lunedì 27, ore 9:30** | T |
| **V-07** | Vector store, tecnica di segmentazione, modello di embedding e restanti componenti sono a libera scelta, purché motivata | T |

## 6. Casi d'uso principali

### UC-1 — Costruire la base di conoscenza

**Attore:** Amministratore
**Precondizione:** esiste una base di conoscenza configurata

1. L'attore carica un PDF (via admin o API).
2. Il sistema registra il documento in stato *in attesa* e restituisce subito il controllo.
3. Il worker estrae il testo pagina per pagina, lo segmenta secondo la configurazione della base di conoscenza, calcola gli embedding e li indicizza.
4. Il sistema porta il documento in stato *indicizzato* e ne registra numero di pagine e di segmenti.

**Estensioni:**
- 3a. Il PDF non contiene testo estraibile → stato *fallito* con motivo esplicito (RF-10).
- 3b. Errore in fase di embedding o scrittura → stato *fallito*, messaggio persistito, documento rielaborabile (RF-06, RF-07).
- 3c. Solo una parte delle pagine contiene testo, sotto la quota configurata → stato *fallito* col conteggio nel motivo (RF-32).
- 1a. Il file è già presente nella stessa base di conoscenza → caricamento rifiutato con segnalazione (RF-09).
- 1b. Il file eccede la dimensione o il numero di pagine ammessi dalla base → caricamento respinto **prima** che la riga esista e che il file sia scritto (RF-31).

### UC-2 — Interrogare la base di conoscenza

**Attore:** Client interrogante
**Precondizione:** almeno un documento in stato *indicizzato*

1. L'attore invia una domanda in linguaggio naturale, opzionalmente indicando la pipeline.
2. Il sistema costruisce la catena a partire dalla configurazione corrente.
3. Recupera dalla base vettoriale i segmenti più pertinenti secondo la strategia configurata.
4. Compone il prompt con i segmenti recuperati e la domanda, e lo sottopone all'LLM locale.
5. Restituisce la risposta con l'elenco delle fonti e i tempi di esecuzione.
6. Registra l'interrogazione.

**Estensioni:**
- 3a. Nessun segmento supera la soglia di pertinenza → il sistema risponde dichiarando di non disporre dell'informazione (RF-14).
- 4a. L'LLM non è raggiungibile → errore esplicito, interrogazione registrata come fallita.

### UC-3 — Modificare il comportamento del sistema

**Attore:** Amministratore
**È il caso d'uso che dimostra il requisito centrale della traccia.**

1. L'attore apre l'admin e modifica un parametro (per esempio la temperatura, il numero di segmenti recuperati o il testo del prompt).
2. Salva. Il sistema valida i valori e rifiuta quelli incoerenti.
3. L'attore ripete l'interrogazione di UC-2.
4. La risposta riflette la nuova configurazione, **senza riavvio dell'applicazione e senza alcuna modifica al codice**.

**Estensioni:**
- 1a. Il parametro modificato incide sulla costruzione dell'indice (segmentazione, modello di embedding) → il sistema segnala che i documenti già indicizzati risultano disallineati e ne propone la reindicizzazione (RF-25).

## 7. Criteri di accettazione

Verifiche dimostrabili a fine lavoro; costituiscono anche la traccia della prova
finale.

La colonna **Esito** riporta lo stato al 26/07/2026, a P6 chiusa: **tutti e dieci
i criteri sono superati**, gli ultimi due dalle prove di consegna T-42 (CA-1) e
T-43 (CA-9). Due esiti vanno letti con la loro riserva, dichiarata in riga e non
in nota: CA-4 è retto dal prompt di sistema e non dalla soglia, e CA-2/CA-8 sono
stati verificati sull'admin servito via HTTP con sessione autenticata, non
guardato in un browser.

**P7 non ha rifatto quelle prove e non ne riscrive gli esiti**: tocca soltanto
CA-10, il cui conteggio sale a 45, e annota su CA-2 ciò che i limiti nuovi *non*
cambiano. Il ciclo di consegna con Ollama vero non è stato rieseguito dopo P7 —
cfr. §9.

Il dettaglio di ciascuna verifica — comando,
uscita, misure — sta nella sezione «Criteri di accettazione» del
[README](README.md#criteri-di-accettazione), che è il documento di consegna;
qui resta il riferimento.

| # | Criterio | Verifica | Esito |
|---|---|---|---|
| **CA-1** | L'ambiente si avvia da zero seguendo il solo README | Esecuzione su macchina pulita | **Superato (T-42, 26/07/2026), al secondo giro.** Il primo ha scoperto tre difetti nei comandi `curl` per Windows, corretti nel README; il secondo, da volume e virtualenv ricreati, è filato senza passi impliciti |
| **CA-2** | Un PDF caricato passa a *indicizzato* e mostra numero di pagine e segmenti | Admin | **Superato** — API e worker (3 pagine, 3 segmenti, T-41 e T-42), test `test_un_pdf_con_testo_arriva_a_indicizzato`, e in T-42 la changelist dell'admin servita dal `runserver` su sessione autenticata («Indicizzato · 3 · 3»). La lettura in un **browser** non è stata fatta e non va data per fatta. *P7 non tocca questo esito:* con `min_text_page_ratio` attivo `page_count` **resta il totale delle pagine del file**, non quelle con testo — contarci solo le seconde renderebbe invisibile proprio la sproporzione che il controllo serve a segnalare |
| **CA-3** | Una domanda sul contenuto del PDF riceve una risposta corretta con le fonti citate | `POST /api/ask/` | **Superato** — 3 fonti citate con pagina e punteggio (T-41), riprodotte identiche in T-42 su database creato da zero, test `test_una_domanda_pertinente_riceve_risposta_e_fonti` |
| **CA-4** | Una domanda **fuori** dal contenuto dei PDF ottiene una dichiarazione di non conoscenza, non una risposta inventata | `POST /api/ask/` | **Superato, ma dal prompt di sistema e non dalla soglia** nella pipeline predefinita: cfr. ARCHITECTURE §7.7. Il filtro di RF-14 è provato dal test, e si attiva scegliendo `similarity_score_threshold` |
| **CA-5** | Modificando la temperatura o il prompt dall'admin, la risposta successiva cambia coerentemente, senza riavvio | Admin + API | **Superato in P3 e ripetuto in T-42** (temperatura 0.0 contro 1.8, terzo processo, pid invariati, nessun riavvio) |
| **CA-6** | Modificando il numero di segmenti recuperati, cambia il numero di fonti restituite | Admin + API | **Superato in P4, P5 e T-42** (in T-42: `top_k` 4 → 2 → 1 → 4 porta le fonti a 3 → 2 → 1 → 3, pid invariati) |
| **CA-7** | Due pipeline distinte sulla stessa base di conoscenza producono risposte diverse, selezionabili per richiesta | API | **Superato in P4 e T-42** (due pipeline che differiscono solo per il prompt: risposte diverse, fonti e punteggi identici) |
| **CA-8** | Un PDF corrotto o solo immagine porta il documento in stato *fallito* con motivo leggibile, senza compromettere il sistema | Admin | **Superato** — P5 e T-42 con `curl` vero (202 poi `failed` con motivo, e il sistema resta operativo), i due casi di `test_un_pdf_non_indicizzabile_…`, e in T-42 la riga «Fallito · 0 · 0» più il motivo per esteso nell'admin servito su sessione autenticata. Nessuna lettura in un **browser** |
| **CA-9** | Nessuna chiamata di rete verso servizi terzi durante ingestione e interrogazione | Ciclo completo a interfacce di rete disattivate (`scripts/prova-rete-staccata.ps1`) | **Superato (T-43, 26/07/2026 ore 12:48).** Esterno irraggiungibile per misura, localhost raggiungibile; ciclo completo riuscito su un PDF mai indicizzato prima, coi tempi pari a quelli a rete attiva; nei log tutte e dodici le richieste HTTP dei due processi vanno a `localhost:11434`. Dettaglio in ARCHITECTURE §9 |
| **CA-10** | La suite di test passa | `pytest` | **Superato** — 29 test, 10,44 s; 10,39 s con `OLLAMA_BASE_URL` su porta chiusa; **29 passed in 7,52 s** sul virtualenv ricostruito di T-42. **Da P7 i test sono 45**, e restano verdi anche con `OLLAMA_BASE_URL` su porta chiusa (misurato il 27/07/2026) |

## 8. Fuori ambito

Escluso esplicitamente, da dichiarare nelle note di consegna:

- Interfaccia utente (esclusa dalla traccia, V-04). Restano fuori ambito
  l'applicazione di frontend e ogni suo corredo; dal 27/07/2026 esistono però
  **due pagine HTML servite da Django** — il login unico `/accedi/` e
  l'interrogazione `/chiedi/` — che non aggiungono endpoint, non duplicano
  regole e non caricano nulla dall'esterno (§3.4)
- Formati diversi dal PDF
- OCR per documenti scansionati. RF-32 non lo introduce: una scansione parziale
  viene **rifiutata**, non recuperata
- Memoria conversazionale multi-turno
- Ricerca ibrida lessicale/vettoriale e riordinamento (reranking)
- Multi-tenancy e controllo degli accessi a livello di documento
- Valutazione quantitativa della qualità delle risposte
- Deployment in produzione, scalabilità orizzontale, alta disponibilità

## 9. Tracciabilità

| Requisiti | Fase di realizzazione | Criteri di accettazione |
|---|---|---|
| RF-17 → RF-26, RF-30 | P1 — Modelli e admin | CA-5, CA-6, CA-7 |
| RF-01 → RF-10, RF-29 | P2 — Ingestione | CA-2, CA-8 |
| RF-11 → RF-16, RF-23 | P3 — Recupero e generazione | CA-3, CA-4, CA-5, CA-6, CA-7 |
| RF-27 | P4 — API | CA-3, CA-7 |
| RF-28 | P2 e P3 — comandi di gestione (`manage.py ingest`, `manage.py ask`) | CA-2, CA-3 |
| RNF-03, RNF-04 | P5 — Asincronia e rifiniture | CA-2, CA-8 |
| RF-22 (ultima costante rimossa) | P6 — `RetrievalProfile.excerpt_length`, migrazione `0005` | — |
| RNF-05 | P6 — Suite pytest, 29 test (T-36 → T-38) | CA-10 |
| RNF-02, RNF-06, RNF-07 | P6 — README di consegna, script di dimostrazione, prove finali (T-39 → T-43) | CA-1, CA-9 |
| RNF-01, V-03 | Trasversale (cfr. ARCHITECTURE §1) | CA-9 |
| RF-31, RF-32 | P7 — Limiti di ammissione, migrazione `0006` (T-44) | Nessuno li copre: RF-32 estende la famiglia di CA-8 |

La colonna indica dove il requisito viene **realizzato**, che non sempre
coincide con dove viene *modellato*. RF-21 e RF-22 stanno nella riga di P1
perché è lì che nascono i campi dell'admin, ma diventano veri in P3: prima di
`build_chain()` non esisteva nulla che rileggesse quella configurazione, quindi
non c'era comportamento da cambiare senza riavvio. CA-5, CA-6 e CA-7 compaiono
per la stessa ragione anche nella riga di P3, dove sono stati dimostrati.

**RNF-03 è realizzato e misurato da P5** (T-32), e non è più il requisito
aperto che era dalla chiusura di P2. L'indicizzazione è passata su una coda
durevole in Postgres (`django-tasks` + `django-tasks-db`) servita da un processo
separato, `manage.py db_worker`. Misure con `curl` contro un `runserver` vero:
`POST /api/documents/` costava **14,53 s** a freddo e **4,25 s** a caldo quando
indicizzava in linea, e ora risponde **202 Accepted** in **0,94 s**, di cui circa
0,9 s sono il sovraccarico costante del client. Il controllo che rende la misura
non ambigua è **negativo**: a worker spento il documento resta «in attesa» —
verificato ancora `pending` dopo 15 s — invece di essere indicizzato di nascosto
nel ciclo richiesta/risposta.

Conseguenza su RF-06 e RF-10: lo stato «in elaborazione» diventa osservabile
davvero, perché lo scrive il worker fuori da ogni transazione di richiesta
(verificato con un `GET /api/documents/{id}/` ogni 150 ms, che ha visto la
sequenza `pending → processing → indexed`), e un PDF senza testo estraibile non
è più scoperto dalla risposta HTTP ma dal worker: la `POST` risponde comunque
**202**, e il documento passa a `failed` con `error_message` leggibile su
`GET /api/documents/{id}/`. È l'unico cambio di contratto dell'API introdotto da
P5 — spariti il **201** e il **422**.

**RNF-05 è realizzato da P6** (T-36 → T-38), e con esso CA-10: **29 test** in
**10,44 s**, ripartiti sulle quattro componenti che il requisito nomina —
segmentazione e costruzione della catena dalla configurazione (11), macchina a
stati dell'ingestione coi casi di errore (9), `POST /api/ask/` con LLM sostituito
(9). I test **non toccano la rete**, e non è un'affermazione: la suite passa
identica col client di inferenza puntato su una porta chiusa (29 passed in
10,39 s). È la conseguenza diretta di ARCHITECTURE §3 — tutto ciò che parla con
Ollama passa da `rag/services/factories.py`, quindi la sostituzione è di quattro
nomi e non di un livello.

**RF-22 è completato da P6.** Fino a P5 sopravviveva una sola costante di
comportamento nel codice, `LUNGHEZZA_ESTRATTO = 300` in `rag/services/query.py`,
dichiarata aperta per iscritto nel report di P5. È diventata
`RetrievalProfile.excerpt_length` (migrazione `0005`, additiva e con lo stesso
predefinito), modificabile dall'admin come `top_k`: cfr. ARCHITECTURE §8.6, che
ne dichiara anche il limite — l'estratto è citazione, non cambia il contesto
passato all'LLM.

**RNF-02, RNF-06 e RNF-07 sono realizzati da P6** con il README di consegna
(T-39), la revisione di questo documento e di `ARCHITECTURE.md` (T-40) e lo
script `scripts/dimostrazione.ps1` (T-41), che percorre il flusso completo
cronometrando ogni passo e fallendo con un messaggio che nomina la causa —
per esempio il worker mai avviato — invece di un timeout muto.

**CA-1 e CA-9 sono stati verificati il 26/07/2026** dalle due prove di consegna,
che richiedevano l'operatore. T-42 ha ricostruito l'ambiente da zero — volume,
`media/` e virtualenv cancellati — seguendo il solo README: **superato al secondo
giro**, dopo che il primo ha scoperto tre difetti nei comandi `curl` per Windows,
il che è l'esito che quella prova esisteva per produrre. T-43 ha rifatto il ciclo
completo a interfacce disattivate: **da qui RNF-01 è verificato e non più
soltanto argomentato**, con l'evidenza in ARCHITECTURE §9 — non l'assenza di
errori di rete, ma l'elenco completo delle richieste HTTP dei due processi, tutte
verso `localhost:11434`. **RNF-02 ha ora la sua prova**, ed è la sequenza del
README rieseguita da capo dopo le correzioni.

**RF-31 e RF-32 sono realizzati da P7** (T-44), con la migrazione `0006` e un
**solo punto di validazione** — `rag/services/validation.py` — chiamato dai tre
inneschi che accettano un file nuovo. È la stessa forma per cui P2 ha un solo
`ingest_document()` e P5 un solo `accoda_indicizzazione()`: se ciascun innesco
validasse per conto proprio, la prima modifica ai limiti si dimenticherebbe in
due punti su tre. La suite passa da 29 a **45 test** — `test_api_ask.py` 9,
`test_ingestione.py` 11, `test_segmentazione_e_factory.py` 11 e
`test_validazione.py` 14, nuovo — e resta verde col client di inferenza puntato
su una porta chiusa, come da P6.

**Cosa di P7 è verificato, e cosa no.** Va detto per intero, perché la fase è
stata chiusa senza il giro end-to-end che le altre hanno avuto.

*Verificato il 27/07/2026:* i 45 test, sia con Ollama raggiungibile sia con
`OLLAMA_BASE_URL` su porta chiusa; `manage.py ingest` con `max_page_count = 2`
su un PDF di tre pagine, che esce con un `CommandError` leggibile e codice 1
senza creare alcuna riga; lo smistamento del login provato su un utente `staff`
e su uno ordinario; `manage.py check` pulito.

*Non verificato:* il ciclo completo dei limiti via HTTP con worker e Ollama
veri — cioè la `POST` respinta con 400, il `min_text_page_ratio` scoperto dal
worker e la controprova a limiti azzerati — e la prova manuale di rifiuto
dall'admin in un browser, che a livello di form è coperta da
`test_il_form_dell_admin_respinge_un_file_oltre_i_limiti`. Finché quel giro non
è fatto, di P7 è dimostrato il comportamento **misurato dai test e da riga di
comando**, non quello osservato in esercizio.
