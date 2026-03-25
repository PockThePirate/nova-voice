import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Optional full WebSocket URL for Nova mic (e.g. wss://ws.novamission.cloud/ws/audio/nova).
# If unset, the browser uses same host + data-nova-ws-path (/ws/audio/nova).
_nova_ws_env = os.environ.get("NOVA_WS_URL", "").strip()
NOVA_WS_URL = _nova_ws_env if _nova_ws_env.startswith(("ws://", "wss://")) else None

SECRET_KEY = "change-this-in-prod"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1","localhost","100.107.120.111","147.93.113.71","novamission.cloud","www.novamission.cloud"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard",
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

ROOT_URLCONF = "mission_control.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.nova_ws_url",
            ],
        },
    },
]

WSGI_APPLICATION = "mission_control.wsgi.application"
ASGI_APPLICATION = "mission_control.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
CSRF_TRUSTED_ORIGINS = ["https://novamission.cloud","https://www.novamission.cloud"]

# Directory for Nova TTS audio files (served via nginx/static)
NOVA_AUDIO_DIR = BASE_DIR / "static" / "nova_audio"
NOVA_VOSK_MODEL_PATH = os.environ.get(
    "NOVA_VOSK_MODEL_PATH",
    str(BASE_DIR / "static" / "vosk" / "model-en" / "vosk-model-small-en-us-0.15"),
)
NOVA_VOSK_SAMPLE_RATE = int(os.environ.get("NOVA_VOSK_SAMPLE_RATE", "16000"))
NOVA_VOSK_MIN_AUDIO_BYTES = int(os.environ.get("NOVA_VOSK_MIN_AUDIO_BYTES", "3200"))
NOVA_GATEWAY_INTERNAL_TOKEN = os.environ.get("NOVA_GATEWAY_INTERNAL_TOKEN", "")
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "openclaw")

# Provider capability toggles mapped to OpenClaw-style capability boundaries.
NOVA_PROVIDER_CAPABILITIES = {
    "text_inference": True,
    "speech_synthesis": True,
    "media_understanding": False,
    "web_search": False,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "nova_file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "nova_errors.log",
            "level": "ERROR",
        },
    },
    "loggers": {
        "nova": {
            "handlers": ["nova_file"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
