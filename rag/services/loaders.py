"""Estrazione del testo dai PDF (T-14, RF-03, RF-10).

Promosso da load_pdf() dello spike di P0, che ARCHITECTURE §7.10 indicava come
l'unico codice dello spike da non buttare via. Lo spike — scripts/spike_rag.py
— e' stato cancellato alla chiusura di P3, quando manage.py ask lo ha
sostituito: questo modulo e' cio' che ne resta.

Si importa `pymupdf` e non `fitz`: dalla 1.24 il nome canonico del modulo e'
`pymupdf` e `fitz` resta come alias di compatibilita'. Verificato sulla 1.28.0
installata.

Da T-44 il modulo ospita anche conta_pagine() e conta_pagine_da_percorso(),
che aprono il PDF per leggerne il solo catalogo. Stanno qui e non in
validation.py perche' la traduzione delle eccezioni di PyMuPDF in PdfIllegibile
e' delicata — le famiglie da catturare per nome sono le stesse di load_pdf() —
e tenerle in due file le farebbe divergere alla prima aggiunta di un caso.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from langchain_core.documents import Document as LCDocument

from .exceptions import PdfIllegibile, PdfSenzaTesto, PdfTestoInsufficiente


@dataclass(frozen=True)
class PdfEstratto:
    """Esito dell'estrazione.

    page_count e' il totale delle pagine del FILE, non delle pagine con testo:
    un PDF di 50 pagine di cui 3 contengono testo va indicizzato, ma l'admin
    deve mostrare 50 (criterio CA-2).
    """

    pagine: list[LCDocument]
    page_count: int


def load_pdf(
    path: str,
    *,
    metadata_extra: dict | None = None,
    min_text_page_ratio: float = 0.0,
) -> PdfEstratto:
    """Estrae il testo pagina per pagina conservando il numero di pagina.

    Il numero di pagina e' 1-based perche' finisce nelle citazioni mostrate
    all'utente (RF-13): «pagina 0» non si scrive in una risposta.

    min_text_page_ratio (T-44) e' la quota minima di pagine con testo sotto la
    quale il documento viene RIFIUTATO invece che indicizzato a meta'. Il
    default 0.0 NON e' un parametro di comportamento nascosto (RF-22): vale
    «controllo disattivato», ed e' anche il default della colonna. Il valore
    vero arriva sempre dal chiamante, che lo legge da
    KnowledgeBase.min_text_page_ratio — qui non c'e' alcuna soglia scritta nel
    codice.

    page_count RESTA il totale delle pagine del file anche quando il controllo
    scatta: e' cio' che l'admin mostra (CA-2), e contarci solo le pagine con
    testo renderebbe invisibile proprio la sproporzione che il controllo serve
    a segnalare.

    Solleva:
        PdfIllegibile: file inesistente, corrotto, vuoto o protetto.
        PdfSenzaTesto: nessuna pagina contiene testo estraibile (RF-10).
        PdfTestoInsufficiente: ne contengono troppo poche rispetto al totale,
            sotto min_text_page_ratio (T-44).
    """
    try:
        documento = pymupdf.open(path)
    except pymupdf.FileNotFoundError as exc:
        # ATTENZIONE: pymupdf.FileNotFoundError OMBREGGIA l'omonima builtin e
        # NON la sottoclassa — deriva da RuntimeError. Verificato sulla 1.28.0:
        # scrivere `except FileNotFoundError` qui NON la catturerebbe, e
        # l'eccezione sfuggirebbe al servizio come guasto inatteso. L'ordine
        # delle clausole conta: va prima di FileDataError.
        raise PdfIllegibile(f"File non trovato: {path}") from exc
    except pymupdf.FileDataError as exc:
        # EmptyFileError e' sottoclasse di FileDataError (verificato), quindi
        # una sola clausola copre file corrotto e file di zero byte. Entrambe
        # derivano da RuntimeError e non da OSError: catturarle per nome e'
        # l'unico modo di distinguerle da un guasto vero.
        raise PdfIllegibile(
            f"Il file non e' un PDF leggibile ({type(exc).__name__}). "
            "Verificare che non sia corrotto o troncato."
        ) from exc

    with documento:
        if documento.needs_pass:
            raise PdfIllegibile(
                "Il PDF e' protetto da password: non e' possibile estrarne il testo."
            )

        page_count = documento.page_count
        pagine: list[LCDocument] = []
        for numero, pagina in enumerate(documento, start=1):
            testo = pagina.get_text().strip()
            if not testo:
                continue
            metadata = {"page": numero, "source": path}
            if metadata_extra:
                metadata.update(metadata_extra)
            pagine.append(LCDocument(page_content=testo, metadata=metadata))

    if not pagine:
        raise PdfSenzaTesto(
            f"Nessun testo estraibile dalle {page_count} pagine del documento. "
            "E' probabilmente una scansione senza OCR: l'OCR e' dichiarato fuori "
            "ambito (REQUIREMENTS §8), quindi questo file non e' indicizzabile."
        )

    # Scansione PARZIALE (T-44). L'ordine conta: PdfSenzaTesto ha la
    # precedenza, perche' «nessuna pagina» e' una diagnosi piu' precisa di
    # «poche pagine» e ha un requisito suo (RF-10). Il confronto e' `<` e non
    # `<=`: un rapporto esattamente pari alla soglia PASSA (§3.9 del piano).
    # La guardia su page_count non e' difensiva per abitudine — evita la
    # divisione per zero se un PDF senza pagine arrivasse fin qui.
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


def conta_pagine(dati: bytes) -> int:
    """Numero di pagine di un PDF in memoria, senza estrarne il testo.

    Esiste per il controllo SINCRONO di T-44: chi carica deve sapere subito
    se il file eccede il limite, e leggere il catalogo delle pagine costa
    millisecondi contro i secondi dell'estrazione.

    L'apertura da stream — `pymupdf.open(stream=..., filetype="pdf")` — e'
    stata VERIFICATA sulla 1.28.0 installata prima di scrivere questa
    funzione, non data per scontata: su un PDF di una pagina costruito con
    tobytes() restituisce page_count 1.

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
