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
| **RF-08** | L'eliminazione di un documento deve rimuovere anche i suoi segmenti e i relativi vettori | D |
| **RF-09** | Il caricamento dello stesso file nella stessa base di conoscenza deve essere rilevato e segnalato, non duplicato | S |
| **RF-10** | Un PDF privo di testo estraibile (scansione senza OCR) deve produrre un errore esplicito, non un documento indicizzato vuoto | S |

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
- 1a. Il file è già presente nella stessa base di conoscenza → caricamento rifiutato con segnalazione (RF-09).

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

| # | Criterio | Verifica |
|---|---|---|
| **CA-1** | L'ambiente si avvia da zero seguendo il solo README | Esecuzione su macchina pulita |
| **CA-2** | Un PDF caricato passa a *indicizzato* e mostra numero di pagine e segmenti | Admin |
| **CA-3** | Una domanda sul contenuto del PDF riceve una risposta corretta con le fonti citate | `POST /api/ask/` |
| **CA-4** | Una domanda **fuori** dal contenuto dei PDF ottiene una dichiarazione di non conoscenza, non una risposta inventata | `POST /api/ask/` |
| **CA-5** | Modificando la temperatura o il prompt dall'admin, la risposta successiva cambia coerentemente, senza riavvio | Admin + API |
| **CA-6** | Modificando il numero di segmenti recuperati, cambia il numero di fonti restituite | Admin + API |
| **CA-7** | Due pipeline distinte sulla stessa base di conoscenza producono risposte diverse, selezionabili per richiesta | API |
| **CA-8** | Un PDF corrotto o solo immagine porta il documento in stato *fallito* con motivo leggibile, senza compromettere il sistema | Admin |
| **CA-9** | Nessuna chiamata di rete verso servizi terzi durante ingestione e interrogazione | Ispezione del traffico / assenza di credenziali esterne |
| **CA-10** | La suite di test passa | `pytest` |

## 8. Fuori ambito

Escluso esplicitamente, da dichiarare nelle note di consegna:

- Interfaccia utente (esclusa dalla traccia, V-04)
- Formati diversi dal PDF
- OCR per documenti scansionati
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
| RF-11 → RF-16 | P3 — Recupero e generazione | CA-3, CA-4 |
| RF-27, RF-28 | P4 — API e comandi | CA-3, CA-7 |
| RNF-03, RNF-04 | P5 — Asincronia e rifiniture | CA-2, CA-8 |
| RNF-02, RNF-05, RNF-06, RNF-07 | P6 — Test e documentazione | CA-1, CA-10 |
| RNF-01, V-03 | Trasversale (cfr. ARCHITECTURE §1) | CA-9 |
