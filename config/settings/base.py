"""Impostazioni comuni a tutti gli ambienti.

Nota: qui NON vive alcun parametro di comportamento del sistema RAG. Modello,
temperatura, chunking e retrieval sono righe di database gestite dall'admin
(cfr. ARCHITECTURE.md §3). Qui c'è solo l'indirizzo del servizio di inferenza.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-cambiami")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rag",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "ragdb"),
        "USER": os.getenv("POSTGRES_USER", "rag"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "rag"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5434"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"   # era "media/": un URL relativo, che dalle pagine
                        # dell'admin si risolverebbe in /admin/rag/document/1/media/...
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ATTENZIONE — questa cache NON è quella degli oggetti LangChain, e il commento
# che stava qui diceva il contrario.
#
# L'intento originale era memorizzare qui la catena costruita da build_chain().
# Non è realizzabile: LocMemCache serializza con pickle anche restando
# in-process, e né ChatOllama né PGVector attraversano pickle — contengono un
# client httpx e un engine SQLAlchemy, cioè lock di thread. Verificato in P3:
# `cache.set()` solleva «TypeError: cannot pickle '_thread.RLock' object» per
# entrambi. La memoizzazione vive quindi in un dizionario di modulo dentro
# rag/services/factories.py, che ne spiega la chiave; e non è la catena a essere
# memorizzata, ma le sue due parti costose, perché build_chain() deve rileggere
# la configurazione a ogni richiesta (RF-22).
#
# Il backend resta configurato perché è la cache generica di Django, utile a
# sessioni e throttling: è il suo scopo, non il nostro.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "django-generica",
    }
}

# --- Servizio di inferenza locale ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Osservabilità opzionale (T-35) ---
LANGFUSE_ENABLED = env_bool("LANGFUSE_ENABLED", False)

# LangChain invia tracce a LangSmith (servizio cloud) se trova queste variabili
# nell'ambiente. Una traccia contiene il prompt completo, quindi i chunk
# estratti dai PDF: sarebbe esattamente l'esfiltrazione che il progetto
# promette di escludere. Non basta non impostarle — se la macchina le ha già
# per altri progetti, il tracing si accende da solo. Vanno forzate a spento.
# Cfr. ARCHITECTURE.md §9.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"  # nome legacy, ancora letto

# Autenticazione delle API (T-31, RF-27). L'ordine delle classi NON e'
# indifferente, ed e' stato scelto su una misura.
#
# BasicAuthentication sta per PRIMA per due ragioni:
#
# 1. senza di essa, `curl -u utente:password` non funzionerebbe affatto.
#    SessionAuthentication impone il CSRF, ma SOLO quando esiste gia' un utente
#    di sessione (verificato sul sorgente di DRF 3.17.1: enforce_csrf() e'
#    chiamata dopo aver trovato l'utente). Un client da riga di comando
#    dovrebbe quindi prima ottenere un cookie di sessione e poi accompagnarlo
#    con il token: la verifica di fase del backlog chiede invece un flusso
#    completo via curl;
# 2. DRF costruisce l'header WWW-Authenticate dal PRIMO autenticatore, e da
#    quello dipende se una richiesta senza credenziali riceva 401 (con header)
#    o 403 (senza). Per un'API 401 e' il codice giusto.
#
# SessionAuthentication resta seconda perche' e' cio' che rende utilizzabile
# l'API navigabile di DRF a chi ha gia' fatto login nell'admin.
#
# Non si usa rest_framework.authtoken: porterebbe QUATTRO migrazioni e una
# tabella di token che in questa prova nessuno emette ne' ruota. Basic su HTTP
# locale e' adeguato allo scopo; su rete pubblica servirebbe TLS, ed e'
# dichiarato nel README.
#
# /health resta AllowAny per decorazione esplicita: e' la sonda del
# docker-compose, e metterla dietro autenticazione romperebbe l'health check.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "rag": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
