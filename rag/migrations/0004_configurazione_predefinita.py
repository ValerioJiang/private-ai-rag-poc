"""Configurazione predefinita funzionante (RF-26).

Senza questa migrazione un'installazione pulita richiederebbe di creare a mano
sei righe prima di poter fare la prima domanda, e il criterio CA-1 («l'ambiente
si avvia da zero seguendo il solo README») non sarebbe soddisfatto.

I valori non sono scelti a tavolino: sono quelli misurati e verificati durante
lo spike di P0. Il prompt di sistema, in particolare, e' quello con cui il
modello ha dichiarato di non sapere invece di inventare (criterio CA-4).

Ripetuti qui per esteso di proposito: una migrazione non deve dipendere da
costanti del codice vivo, che possono cambiare.
"""

from django.db import migrations

RISPOSTA_NON_DISPONIBILE = "Non dispongo di questa informazione nei documenti forniti."

SYSTEM_PROMPT = (
    "Sei un assistente che risponde ESCLUSIVAMENTE sulla base del contesto fornito. "
    "Se il contesto non contiene l'informazione, rispondi esattamente: "
    f"'{RISPOSTA_NON_DISPONIBILE}' "
    "Rispondi in italiano, in modo conciso."
)

TEMPLATE = "Contesto:\n{context}\n\nDomanda: {question}"

NOMI = {
    "llm": "Predefinito — qwen2.5 7B",
    "embedding": "Predefinito — bge-m3",
    "chunking": "Predefinito — recursive 800/120",
    "retrieval": "Predefinito — similarita' k=4",
    "prompt": "Predefinito — risposta ancorata al contesto",
    "kb": "Base di conoscenza predefinita",
    "pipeline": "Pipeline predefinita",
}


def crea_configurazione(apps, schema_editor):
    LLMProfile = apps.get_model("rag", "LLMProfile")
    EmbeddingProfile = apps.get_model("rag", "EmbeddingProfile")
    ChunkingProfile = apps.get_model("rag", "ChunkingProfile")
    RetrievalProfile = apps.get_model("rag", "RetrievalProfile")
    PromptTemplate = apps.get_model("rag", "PromptTemplate")
    KnowledgeBase = apps.get_model("rag", "KnowledgeBase")
    RagPipeline = apps.get_model("rag", "RagPipeline")

    llm, _ = LLMProfile.objects.get_or_create(
        name=NOMI["llm"],
        defaults={
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model_name": "qwen2.5:7b-instruct",
            "temperature": 0.0,
            "top_p": 0.9,
            "top_k": 40,
            "max_tokens": 1024,
            "timeout_s": 180,
            "is_default": True,
        },
    )
    embedding, _ = EmbeddingProfile.objects.get_or_create(
        name=NOMI["embedding"],
        defaults={
            "provider": "ollama",
            "model_name": "bge-m3",
            "dimension": 1024,
            "normalize": True,
            "batch_size": 16,
        },
    )
    chunking, _ = ChunkingProfile.objects.get_or_create(
        name=NOMI["chunking"],
        defaults={
            "splitter": "recursive",
            "chunk_size": 800,
            "chunk_overlap": 120,
            "separators": [],
        },
    )
    retrieval, _ = RetrievalProfile.objects.get_or_create(
        name=NOMI["retrieval"],
        defaults={
            "search_type": "similarity",
            "top_k": 4,
            "fetch_k": 20,
            "lambda_mult": 0.5,
            "score_threshold": 0.5,
        },
    )
    prompt, _ = PromptTemplate.objects.get_or_create(
        name=NOMI["prompt"],
        defaults={"system_prompt": SYSTEM_PROMPT, "template": TEMPLATE},
    )
    kb, _ = KnowledgeBase.objects.get_or_create(
        name=NOMI["kb"],
        defaults={
            "collection_name": "default",
            "description": (
                "Creata dalla migrazione iniziale: il sistema e' utilizzabile "
                "subito dopo l'installazione, senza configurazione manuale."
            ),
            "embedding_profile": embedding,
            "chunking_profile": chunking,
        },
    )
    RagPipeline.objects.get_or_create(
        name=NOMI["pipeline"],
        defaults={
            "knowledge_base": kb,
            "llm_profile": llm,
            "retrieval_profile": retrieval,
            "prompt_template": prompt,
            "is_active": True,
            "is_default": True,
        },
    )


def elimina_configurazione(apps, schema_editor):
    """Reversibile, ma senza distruggere lavoro altrui.

    Le righe si cancellano nell'ordine inverso delle dipendenze, e la base di
    conoscenza solo se e' rimasta vuota: se contiene documenti, disfare la
    migrazione ne cancellerebbe l'indicizzazione a cascata.
    """
    RagPipeline = apps.get_model("rag", "RagPipeline")
    KnowledgeBase = apps.get_model("rag", "KnowledgeBase")

    RagPipeline.objects.filter(name=NOMI["pipeline"]).delete()

    kb = KnowledgeBase.objects.filter(name=NOMI["kb"]).first()
    if kb is not None and not kb.documents.exists():
        kb.delete()
        for modello, chiave in (
            ("LLMProfile", "llm"),
            ("EmbeddingProfile", "embedding"),
            ("ChunkingProfile", "chunking"),
            ("RetrievalProfile", "retrieval"),
            ("PromptTemplate", "prompt"),
        ):
            apps.get_model("rag", modello).objects.filter(name=NOMI[chiave]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rag", "0003_dominio_e_log"),
    ]

    operations = [
        migrations.RunPython(crea_configurazione, elimina_configurazione),
    ]
