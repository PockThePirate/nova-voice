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
    "nova_calendar",
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
# Django 6 removed StaticFilesMiddleware; serve /static via nginx (or runserver dev automatic handling).
CSRF_TRUSTED_ORIGINS = ["https://novamission.cloud","https://www.novamission.cloud"]

# Nova TTS output and ``nova_audio_file`` reads: default ``static/nova_audio`` (same tree VoiceOrchestrator writes to).
# Production often had DEBUG=False → STATIC_ROOT/nova_audio while TTS still wrote under static/nova_audio → API 404.
# Override absolute path with NOVA_AUDIO_DIR only if you relocate the folder.
_nova_audio_dir_override = os.environ.get("NOVA_AUDIO_DIR", "").strip()
if _nova_audio_dir_override:
    NOVA_AUDIO_DIR = Path(_nova_audio_dir_override)
else:
    NOVA_AUDIO_DIR = BASE_DIR / "static" / "nova_audio"

# ``NOVA_AUDIO_URL_PREFIX`` is only used when NOVA_AUDIO_LEGACY_STATIC_URL=1 (see ``dashboard.views._nova_audio_output_url_prefix``).
# Otherwise JSON ``audio_url`` is always built as /api/nova/audio/<uuid>.mp3.
_nova_force_api_audio = os.environ.get("NOVA_FORCE_AUDIO_API_URL", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
if _nova_force_api_audio:
    NOVA_AUDIO_URL_PREFIX = "/api/nova/audio/"
else:
    _nova_audio_url_prefix_env = os.environ.get("NOVA_AUDIO_URL_PREFIX", "").strip()
    if _nova_audio_url_prefix_env:
        NOVA_AUDIO_URL_PREFIX = (
            _nova_audio_url_prefix_env
            if _nova_audio_url_prefix_env.endswith("/")
            else _nova_audio_url_prefix_env + "/"
        )
    else:
        NOVA_AUDIO_URL_PREFIX = "/api/nova/audio/"
NOVA_VOSK_MODEL_PATH = os.environ.get(
    "NOVA_VOSK_MODEL_PATH",
    str(BASE_DIR / "static" / "vosk" / "model-en" / "vosk-model-small-en-us-0.15"),
)
NOVA_VOSK_SAMPLE_RATE = int(os.environ.get("NOVA_VOSK_SAMPLE_RATE", "16000"))
NOVA_VOSK_MIN_AUDIO_BYTES = int(os.environ.get("NOVA_VOSK_MIN_AUDIO_BYTES", "3200"))
NOVA_GATEWAY_INTERNAL_TOKEN = os.environ.get("NOVA_GATEWAY_INTERNAL_TOKEN", "")
# Optional fallback for headless devices when ``NOVA_GATEWAY_INTERNAL_TOKEN`` is empty:
# ``I@mWho1$@yIam`` + current UTC MMDD.
NOVA_DEVICE_TOKEN_DERIVED = os.environ.get("NOVA_DEVICE_TOKEN_DERIVED", "").strip().lower() in (
    "1",
    "true",
    "yes",
)
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
