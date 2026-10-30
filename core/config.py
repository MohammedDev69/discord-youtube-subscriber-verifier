import os
import sys
import shutil
import logging
from pathlib import Path
from typing import Tuple, List, Optional
from dotenv import load_dotenv
import pytesseract

# Load environment variables from .env file
load_dotenv()

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "bot.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("youtube-verifier")

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
SYNC_SLASH_COMMANDS_GLOBALLY = os.getenv("SYNC_SLASH_COMMANDS_GLOBALLY", "true").lower() in ("true", "1", "yes")

# Default Guild Settings
DEFAULT_CONFIG = {
    "youtube_channel_name": os.getenv("YOUTUBE_CHANNEL_NAME", "Mohamed Hemdan"),
    "verified_role_name": os.getenv("VERIFIED_ROLE_NAME", "Subscriber"),
    "cooldown_hours": float(os.getenv("DEFAULT_COOLDOWN_HOURS", "24")),
    "verification_threshold": float(os.getenv("DEFAULT_CONFIDENCE_THRESHOLD", "0.7")),
    "alternative_channel_names": [],
    "admin_users": [],
    "admin_roles": [],
    "log_channel_id": None,
    "language_detection": True,
}

# File Paths
DATA_DIR = Path("data")
CONFIG_FILE = "server_configs.json"
COOLDOWN_FILE = "user_cooldowns.json"


def find_and_configure_tesseract() -> Tuple[bool, str]:
    """
    Locates the Tesseract OCR executable across common paths or system PATH
    and configures pytesseract.
    
    Returns:
        tuple: (is_configured: bool, status_message_or_path: str)
    """
    env_path = os.getenv("TESSERACT_PATH")
    candidate_paths: List[Path] = []

    # 1. Custom ENV path
    if env_path:
        candidate_paths.append(Path(env_path))

    # 2. Check PATH executable
    which_path = shutil.which("tesseract")
    if which_path:
        candidate_paths.append(Path(which_path))

    # 3. Common Windows paths
    if sys.platform.startswith("win"):
        candidate_paths.extend([
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")),
        ])
    else:
        # Common Linux / Unix paths
        candidate_paths.extend([
            Path("/usr/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
            Path("/opt/homebrew/bin/tesseract"),
        ])

    for candidate in candidate_paths:
        if candidate.is_file():
            try:
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
                version = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract OCR found and configured at '{candidate}' (v{version})")
                return True, str(candidate)
            except Exception as exc:
                logger.warning(f"Found candidate '{candidate}' but failed to verify: {exc}")

    # Fallback attempt if tesseract is simply on PATH
    try:
        version = pytesseract.get_tesseract_version()
        logger.info(f"Tesseract OCR detected on default system PATH (v{version})")
        return True, "system_path"
    except Exception:
        pass

    msg = (
        "Tesseract OCR executable was not found. OCR features will not work until Tesseract is installed.\n"
        "- Windows: Download installer from https://github.com/UB-Mannheim/tesseract/wiki\n"
        "- Ubuntu/Debian: Run 'sudo apt-get install tesseract-ocr tesseract-ocr-ara'\n"
        "- Or set TESSERACT_PATH in your .env file."
    )
    logger.warning(msg)
    return False, msg


def get_available_ocr_languages() -> List[str]:
    """
    Retrieves the list of installed Tesseract languages.
    Returns empty list if Tesseract is not configured.
    """
    try:
        return pytesseract.get_languages()
    except Exception:
        return []

