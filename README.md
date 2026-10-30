# 📺 YouTube Subscription Verifier - Discord Bot

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-v2.x-5865F2.svg)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://www.docker.com/)

An open-source, production-ready Discord bot that automatically grants verified roles to members who subscribe to your YouTube channel by analyzing screenshot evidence using **Computer Vision (OpenCV)** and **Optical Character Recognition (Tesseract OCR)**.

---

## ✨ Features

- ⚡ **Dual Command Interface:** Native support for both **Slash Commands (`/`)** and traditional **Prefix Commands (`!`)** across all commands.
- 👁️ **Advanced Image Pipeline:** Multi-stage image enhancement, adaptive Gaussian thresholding, and UI region-of-interest extraction for maximum OCR accuracy.
- 🌍 **Multilingual OCR Support:** Detects YouTube interfaces in **English, Arabic, French, Spanish, German, Turkish, Portuguese**, and more.
- 🛡️ **Anti-Spoofing Heuristics:** Intelligently differentiates between confirmed subscriptions (*"Subscribed"* / *"مشترك"*) and un-subscribed buttons (*"Subscribe"* / *"اشترك"*), avoiding false positives on raw profile pages.
- ⚙️ **Per-Server Customization:** Admins can configure the channel name, verified role, cooldown periods, confidence thresholds, and audit logging per server.
- 🔒 **Atomic Data Persistence:** Thread-safe, atomic JSON data storage with zero SQL database setup required.
- 🐳 **Docker & Production Ready:** Includes pre-configured `Dockerfile` and `docker-compose.yml` with all OCR libraries and language packs pre-installed.

---

## 📁 Project Architecture

```
YoutubeCheckerImagePython/
├── cogs/
│   ├── admin.py            # /setup, /stats, /clear_cooldown, !sync
│   ├── general.py          # /help, /ping, /about
│   └── verification.py     # /verify screenshot OCR pipeline
├── core/
│   ├── config.py           # Environment loading & smart Tesseract discovery
│   ├── database.py         # Thread-safe atomic JSON storage
│   └── ocr.py              # OpenCV preprocessing & Tesseract evaluation
├── .env.example            # Template environment variables
├── .gitignore              # Git ignore rules for bots and secrets
├── Dockerfile              # Container image with Debian, Tesseract & language packs
├── docker-compose.yml      # 1-click Docker Compose service
├── LICENSE                 # MIT License
├── README.md               # Documentation
├── requirements.txt        # Python package dependencies
└── main.py                 # Application entrypoint & bot client
```

---

## 🚀 Quick Start Guide

### Prerequisites

- **Python 3.10+**
- **Tesseract OCR Engine** installed on your host system (or run via Docker).

---

### Method A: Local Setup (Windows / Linux / macOS)

#### 1. Clone the repository
```bash
git clone https://github.com/MohammedDev69/discord-youtube-subscriber-verifier.git
cd discord-youtube-subscriber-verifier
```

#### 2. Create and activate a virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Python dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Install Tesseract OCR Engine

- **Windows:**
  1. Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
  2. During installation, select additional script and language data (including Arabic if needed).
  3. The bot automatically discovers `C:\Program Files\Tesseract-OCR\tesseract.exe`.

- **Ubuntu / Debian:**
  ```bash
  sudo apt-get update
  sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ara
  ```

- **macOS (Homebrew):**
  ```bash
  brew install tesseract
  brew install tesseract-lang
  ```

#### 5. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your Discord Bot Token:
```env
DISCORD_TOKEN=your_bot_token_here
COMMAND_PREFIX=!
YOUTUBE_CHANNEL_NAME=Mohamed Hemdan
VERIFIED_ROLE_NAME=Subscriber
```

#### 6. Run the Bot
```bash
python main.py
```

---

### Method B: Docker Deployment (Recommended)

Running with Docker includes all Tesseract binaries, language packages, and system dependencies automatically:

```bash
# 1. Clone and configure .env
cp .env.example .env
# Edit .env with your DISCORD_TOKEN

# 2. Build and launch with Docker Compose
docker compose up -d

# 3. View live logs
docker compose logs -f
```

---

## 🤖 Discord Developer Portal Configuration

To ensure the bot operates properly, enable the following in the [Discord Developer Portal](https://discord.com/developers/applications):

1. **Privileged Gateway Intents:**
   - ✅ **Server Members Intent** (required to view members and assign roles)
   - ✅ **Message Content Intent** (required to process prefix commands and message attachments)

2. **Bot Permissions:**
   When generating the invite link under **OAuth2 -> URL Generator**, select:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions:
     - `Manage Roles`
     - `Send Messages`
     - `Embed Links`
     - `Attach Files`
     - `Read Message History`
     - `Use Slash Commands`

3. **Role Hierarchy (Important!):**
   In your Discord Server Settings under **Roles**, ensure the **Bot's highest role is positioned above the Verified role**. Discord does not permit bots to grant roles that are higher than or equal to their own position in the hierarchy.

---

## 📋 Commands Reference

### Member Commands

| Slash Command | Prefix Command | Description |
|---|---|---|
| `/verify [image] [url]` | `!verify` | Analyzes screenshot evidence and grants the verified subscriber role. |
| `/ping` | `!ping` | Displays API roundtrip and websocket heartbeat latency. |
| `/about` | `!about` | Shows information about the bot and system specifications. |
| `/help` | `!help` | Displays the interactive help manual. |

### Administrator Commands (`Administrator` Permission Required)

| Slash Command | Prefix Command | Description |
|---|---|---|
| `/setup show` | `!setup show` | Shows the server's current verification settings. |
| `/setup channel <name>` | `!setup channel <name>` | Sets the target YouTube channel name or handle. |
| `/setup role <@role>` | `!setup role <@role>` | Sets the Discord role given to verified subscribers. |
| `/setup cooldown <hours>` | `!setup cooldown <hours>` | Sets cooldown period between verification attempts. |
| `/setup threshold <score>` | `!setup threshold <score>` | Sets the minimum confidence threshold (0.1 - 1.0). |
| `/setup add_alt <name>` | `!setup add_alt <name>` | Adds an alternative channel name or alias. |
| `/setup remove_alt <name>`| `!setup remove_alt <name>` | Removes an alternative channel name. |
| `/setup log_channel [#ch]`| `!setup log_channel [#ch]` | Sets a channel to receive verification audit logs. |
| `/stats` | `!stats` | Displays verified member statistics and OCR engine status. |
| `/clear_cooldown <@user>` | `!clear_cooldown <@user>` | Resets a member's verification attempt cooldown. |
| — | `!sync [global]` | Forces synchronization of slash commands with Discord. |

---

## 💡 How Verification Works

1. **Submission:** A user runs `/verify` and attaches a screenshot of their YouTube subscription (or sends `!verify` with an attachment).
2. **Preprocessing:** The image is processed through contrast enhancement, bilateral filtering, and adaptive Gaussian thresholding.
3. **Region Extraction:** The engine focuses on key interface areas (channel header, subscribe button bounding box, mobile layouts).
4. **OCR Parsing:** Text is extracted using Tesseract with trained models across multiple languages.
5. **Subscription Evaluation:**
   - Detects confirmed status (`"Subscribed"`, `"مشترك"`, `"Abonné"`, `"Suscrito"`, etc.).
   - Discards un-subscribed states (`"Subscribe"` button).
   - Validates the target channel name and registered aliases.
   - Computes a weighted confidence score.
6. **Role Assignment:** If the confidence meets the configured threshold, the role is granted automatically, and an audit entry is logged.

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | String | *Required* | Discord Bot Token from Developer Portal. |
| `COMMAND_PREFIX` | String | `!` | Prefix for message-based commands. |
| `YOUTUBE_CHANNEL_NAME` | String | `Mohamed Hemdan` | Default channel name for new servers. |
| `VERIFIED_ROLE_NAME` | String | `Subscriber` | Default role name granted to verified subscribers. |
| `DEFAULT_COOLDOWN_HOURS` | Float | `24` | Default cooldown period in hours. |
| `DEFAULT_CONFIDENCE_THRESHOLD` | Float | `0.7` | Minimum OCR confidence score required. |
| `SYNC_SLASH_COMMANDS_GLOBALLY` | Boolean | `true` | Automatically register slash commands globally. |
| `TESSERACT_PATH` | String | *Auto-detected* | Custom path to Tesseract binary if not on PATH. |
| `LOG_LEVEL` | String | `INFO` | Console and file logging verbosity. |

---

## ❓ FAQ & Troubleshooting

#### 1. Why are slash commands not showing up in my server?
Discord can take up to an hour to propagate global slash commands to all servers. To force an immediate synchronization to your current server, run:
```
!sync
```
Or to sync globally:
```
!sync global
```

#### 2. The bot says "Missing Role Permissions" when verifying members.
Ensure that:
1. The bot has the **Manage Roles** permission enabled.
2. In `Server Settings -> Roles`, drag the bot's highest role **above** the verified role.

#### 3. "Tesseract OCR executable was not found" error on startup.
Ensure Tesseract is installed and added to your system PATH, or specify its exact path in `.env`:
```env
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). Feel free to use, modify, and distribute it in your own Discord servers or commercial communities.

