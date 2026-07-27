"""Ammissibilita' dei file in ingresso (T-44, RF-22).

UN SOLO PUNTO DI VALIDAZIONE, chiamato da TRE inneschi — quelli che accettano
un file NUOVO: `POST /api/documents/`, `manage.py ingest <path>` e il
salvataggio dall'admin (DocumentAdminForm.clean()). E' la stessa forma per cui
esiste un solo ingest_document() (P2) e un solo accoda_indicizzazione() (P5):
se ciascun innesco validasse per conto proprio, la prima modifica ai limiti si
dimenticherebbe in due punti su tre.

L'admin NON e' un'eccezione, ed e' bene ricordare perche': caricare un
documento nuovo dall'admin carica un file nuovo, ed e' il flusso di CA-2 — la
via che un amministratore usa per prima. Escluderlo lascerebbe scavalcare ogni
limite proprio alla via piu' battuta. Il discriminante lo porta gia'
`DocumentAdminForm.clean()`, che distingue un upload appena caricato da un
FieldFile gia' in archivio.

L'unico innesco che resta FUORI e' l'azione «Reindicizza», che non riceve alcun
file: rilegge dal disco un documento gia' accettato. Abbassare un limite non
deve far fallire il riesame di cio' che e' gia' in archivio.

I limiti sono righe di database (KnowledgeBase), non costanti: RF-22. Qui non
c'e' alcun valore predefinito di comportamento, e non va introdotto.
"""

from __future__ import annotations

from .exceptions import FileTroppoGrande, TroppePagine
from .loaders import conta_pagine, conta_pagine_da_percorso

BYTE_PER_MB = 1024 * 1024
"""Fattore di conversione, non un parametro: 1 MB e' 1 MB. Non e' RF-22."""


def verifica_ammissibilita(file, knowledge_base, *, percorso: str | None = None) -> None:
    """Verifica dimensione e numero di pagine PRIMA di scrivere alcunche'.

    `file` e' un oggetto in stile django.core.files.File: servono `.size` e
    `.read()`. Vale sia per un caricamento HTTP sia per un file aperto da
    disco, ed e' cio' che permette ai tre inneschi di condividere questa
    funzione.

    `percorso` lo passa chi il percorso lo conosce gia' — cioe' `manage.py
    ingest`, che parte proprio da un file di disco. Serve perche' MISURATO in
    esecuzione: django.core.files.File che incarta un file aperto NON espone
    ne' `.path` ne' `.temporary_file_path()` (il suo `.name` e' il percorso, ma
    su un upload e' il nome del client: distinguerli a fiuto sarebbe una
    congettura). Senza questo argomento il comando cadrebbe sul ramo in
    memoria e leggerebbe per intero proprio il file che il limite esiste per
    respingere.

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
        pagine = _conta_pagine_senza_caricare(file, percorso)
        if pagine > limite_pagine:
            raise TroppePagine(
                f"Il documento ha {pagine} pagine e supera il limite di "
                f"{limite_pagine} fissato per la base di conoscenza "
                f"«{knowledge_base.name}». L'indicizzazione costa circa un "
                f"secondo per segmento, e la coda e' seriale."
            )


def _conta_pagine_senza_caricare(file, percorso: str | None = None) -> int:
    """Conta le pagine dalla via meno costosa disponibile (§3.10 del piano).

    Tre rami, in ordine di preferenza:

    1. il `percorso` dichiarato dal chiamante, quando ce l'ha gia' — e' il caso
       di `manage.py ingest`. Il piano dava per scontato che il ramo 2 lo
       coprisse: MISURATO in esecuzione, non lo copre (cfr. verifica_ammissibilita);
    2. temporary_file_path(), che esiste su TemporaryUploadedFile — cioe' sugli
       upload che Django ha spoolato su disco perche' oltre 2,5 MB. NON esiste
       su SimpleUploadedFile ne' su InMemoryUploadedFile (verificato). `.path`
       e' provato con esso perche' lo espone FieldFile, per un domani in cui
       qualcuno validasse un file gia' in archivio;
    3. la lettura in memoria. Ci si arriva solo quando il file in memoria ci
       sta gia' per definizione, e leggerlo non aggiunge occupazione: e' il
       ramo innocuo, non il ramo pigro.
    """
    if percorso:
        return conta_pagine_da_percorso(percorso)

    temporaneo = getattr(file, "temporary_file_path", None)
    if callable(temporaneo):
        return conta_pagine_da_percorso(temporaneo())

    nome = getattr(file, "path", None)  # FieldFile: un file gia' in archivio
    if nome:
        return conta_pagine_da_percorso(nome)

    try:
        return conta_pagine(file.read())
    finally:
        # Nel `finally`: anche se conta_pagine solleva, chi ha chiamato deve
        # ritrovare il file riavvolto. E' il difetto accertato in P2 su
        # compute_checksum().
        file.seek(0)
