import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from core.config import CONFIG_FILE, COOLDOWN_FILE, DEFAULT_CONFIG

logger = logging.getLogger("youtube-verifier.database")


class DatabaseManager:
    """
    Manages persistent storage for guild configurations and user cooldowns
    using atomic JSON file operations.
    """

    def __init__(self, config_path: str = CONFIG_FILE, cooldown_path: str = COOLDOWN_FILE):
        self.config_path = config_path
        self.cooldown_path = cooldown_path
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._cooldowns: Dict[str, Dict[str, str]] = {}  # {guild_id: {user_id: iso_timestamp}}
        self.load_all()

    def _atomic_write_json(self, file_path: str, data: Any) -> bool:
        """Writes data to a temporary file then replaces target to guarantee atomic writes."""
        temp_path = f"{file_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_path, file_path)
            return True
        except Exception as e:
            logger.error(f"Failed to atomically write '{file_path}': {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return False

    def load_all(self) -> None:
        """Loads both configurations and cooldown files from disk."""
        # Load Guild Configs
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._configs = json.load(f)
                logger.info(f"Loaded configurations for {len(self._configs)} guild(s).")
            except Exception as e:
                logger.error(f"Error loading '{self.config_path}': {e}")
                self._configs = {}
        else:
            self._configs = {}

        # Load Cooldowns
        if os.path.exists(self.cooldown_path):
            try:
                with open(self.cooldown_path, "r", encoding="utf-8") as f:
                    self._cooldowns = json.load(f)
                logger.info(f"Loaded cooldown records for {len(self._cooldowns)} guild(s).")
            except Exception as e:
                logger.error(f"Error loading '{self.cooldown_path}': {e}")
                self._cooldowns = {}
        else:
            self._cooldowns = {}

    def save_configs(self) -> bool:
        """Saves current configurations to disk."""
        return self._atomic_write_json(self.config_path, self._configs)

    def save_cooldowns(self) -> bool:
        """Saves current cooldown records to disk."""
        return self._atomic_write_json(self.cooldown_path, self._cooldowns)

    def save_all(self) -> None:
        """Persists all state to disk."""
        self.save_configs()
        self.save_cooldowns()

    # --- Guild Configuration Methods ---

    def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """
        Retrieves the configuration for a guild, filling in defaults for any missing keys.
        """
        guild_id_str = str(guild_id)
        if guild_id_str not in self._configs:
            self._configs[guild_id_str] = DEFAULT_CONFIG.copy()
            self.save_configs()
        else:
            # Ensure any newly added default keys exist
            updated = False
            for key, default_val in DEFAULT_CONFIG.items():
                if key not in self._configs[guild_id_str]:
                    self._configs[guild_id_str][key] = default_val
                    updated = True
            if updated:
                self.save_configs()

        return self._configs[guild_id_str]

    def update_guild_config(self, guild_id: int, key: str, value: Any) -> Dict[str, Any]:
        """Updates a specific configuration setting for a guild."""
        cfg = self.get_guild_config(guild_id)
        cfg[key] = value
        self.save_configs()
        return cfg

    def get_all_guild_configs(self) -> Dict[str, Dict[str, Any]]:
        """Returns all guild configurations."""
        return self._configs

    # --- User Cooldown Methods ---

    def check_user_cooldown(
        self, guild_id: int, user_id: int, cooldown_hours: float
    ) -> Tuple[bool, Optional[timedelta], Optional[datetime]]:
        """
        Checks whether a user is currently on verification cooldown.

        Returns:
            Tuple[is_on_cooldown, remaining_timedelta, expiry_datetime]
        """
        if cooldown_hours <= 0:
            return False, None, None

        guild_id_str = str(guild_id)
        user_id_str = str(user_id)

        guild_cooldowns = self._cooldowns.get(guild_id_str, {})
        last_attempt_str = guild_cooldowns.get(user_id_str)

        if not last_attempt_str:
            return False, None, None

        try:
            last_attempt = datetime.fromisoformat(last_attempt_str)
        except (ValueError, TypeError):
            return False, None, None

        expiry = last_attempt + timedelta(hours=cooldown_hours)
        now = datetime.now()

        if now < expiry:
            remaining = expiry - now
            return True, remaining, expiry
        else:
            return False, None, None

    def record_attempt(self, guild_id: int, user_id: int) -> None:
        """Records a verification attempt timestamp for a user."""
        guild_id_str = str(guild_id)
        user_id_str = str(user_id)

        if guild_id_str not in self._cooldowns:
            self._cooldowns[guild_id_str] = {}

        self._cooldowns[guild_id_str][user_id_str] = datetime.now().isoformat()
        self.save_cooldowns()

    def clear_user_cooldown(self, guild_id: int, user_id: int) -> bool:
        """
        Clears the cooldown for a specific user in a guild.
        Returns True if cooldown was cleared, False if none existed.
        """
        guild_id_str = str(guild_id)
        user_id_str = str(user_id)

        if guild_id_str in self._cooldowns and user_id_str in self._cooldowns[guild_id_str]:
            del self._cooldowns[guild_id_str][user_id_str]
            self.save_cooldowns()
            return True
        return False


# Global singleton instance
db = DatabaseManager()

