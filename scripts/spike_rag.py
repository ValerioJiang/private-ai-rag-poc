"""SPIKE — codice usa-e-getta (T-06).

Scopo: dimostrare end-to-end che PyMuPDF, bge-m3, pgvector e qwen2.5 si
parlano, e misurare i tempi reali sulla macchina.

NON è codice di produzione: i parametri sono scritti a mano apposta. In P1
diventeranno righe di database gestite dall'admin. Questo file va cancellato
quando la fase P2 è completa.

Uso:
    .venv/Scripts/python.exe scripts/spike_rag.py samples/manuale-dipendenti.pdf
"""

import os
import sys
import time
from pathlib import Path

import django

# Lo script vive in scripts/, quindi sys.path[0] e' scripts/ e non la radice del
# progetto: senza questa riga `import config.settings.dev` fallisce.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.conf import settings  # noqa: E402

import fitz  # noqa: E402  (PyMuPDF)
from langchain_core.documents import Document  # noqa: E402
from langchain_core.output_parsers import StrOutputParser  # noqa: E402
from langchain_core.prompts import ChatPromptTemplate  # noqa: E402
from langchain_ollama import ChatOllama, OllamaEmbeddings  # noqa: E402
from langchain_postgres import PGVector  # noqa: E402
from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402

# --- parametri scritti a mano: in P1 diventano righe di DB ---
LLM_MODEL = "qwen2.5:7b-instruct"
EMBED_MODEL = "bge-m3"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
TOP_K = 4
COLLECTION = "spike"


def connection_string() -> str:
    return (
        f"postgresql+psycopg://{settings.DATABASES['default']['USER']}:"
        f"{settings.DATABASES['default']['PASSWORD']}@"
        f"{settings.DATABASES['default']['HOST']}:"
        f"{settings.DATABASES['default']['PORT']}/"
        f"{settings.DATABASES['default']['NAME']}"
    )


def load_pdf(path: str) -> list[Document]:
    """Estrae il testo pagina per pagina, conservando il numero di pagina."""
    doc = fitz.open(path)
    docs = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            docs.append(Document(page_content=text, metadata={"source": path, "page": i}))
    if not docs:
        raise SystemExit(
            f"ERRORE: nessun testo estraibile da {path}. "
            "Probabile PDF scansionato senza OCR (caso RF-10)."
        )
    print(f"[load] {len(docs)} pagine con testo su {doc.page_count} totali")
    return docs


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "samples/manuale-dipendenti.pdf"

    pages = load_pdf(path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(pages)
    print(f"[split] {len(chunks)} chunk")

    embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=settings.OLLAMA_BASE_URL)

    t0 = time.perf_counter()
    store = PGVector.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION,
        connection=connection_string(),
        pre_delete_collection=True,
    )
    print(f"[index] {len(chunks)} chunk indicizzati in {time.perf_counter() - t0:.1f}s")

    retriever = store.as_retriever(search_kwargs={"k": TOP_K})

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "Sei un assistente che risponde ESCLUSIVAMENTE sulla base del contesto fornito. "
            "Se il contesto non contiene l'informazione, rispondi esattamente: "
            "'Non dispongo di questa informazione nei documenti forniti.' "
            "Rispondi in italiano, in modo conciso.",
        ),
        ("human", "Contesto:\n{context}\n\nDomanda: {question}"),
    ])

    llm = ChatOllama(model=LLM_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0)

    def format_docs(docs: list[Document]) -> str:
        return "\n\n".join(f"[pagina {d.metadata.get('page')}] {d.page_content}" for d in docs)

    domande = [
        "Quanti giorni di ferie si maturano all'anno?",          # atteso: nel documento
        "Qual e il rimborso chilometrico?",                       # atteso: nel documento
        "Qual e la capitale del Madagascar?",                     # atteso: non lo so (CA-4)
    ]

    for domanda in domande:
        t0 = time.perf_counter()
        docs = retriever.invoke(domanda)
        t_ret = time.perf_counter() - t0

        t0 = time.perf_counter()
        chain = prompt | llm | StrOutputParser()
        risposta = chain.invoke({"context": format_docs(docs), "question": domanda})
        t_gen = time.perf_counter() - t0

        print("\n" + "=" * 70)
        print(f"D: {domanda}")
        print(f"R: {risposta.strip()}")
        print(f"   fonti: pagine {[d.metadata.get('page') for d in docs]}")
        print(f"   tempi: retrieval {t_ret:.2f}s · generazione {t_gen:.2f}s")


if __name__ == "__main__":
    main()
