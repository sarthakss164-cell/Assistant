"""
Authoritative Playlist Configuration Loader for LIGHT AI V1.0.
Loads, validates, and serves named playlists from config/playlist.json.
Guarantees project-root-relative path resolution, strict schema validation,
and order preservation without silent fallbacks.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from utils.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAYLIST_PATH = PROJECT_ROOT / "config" / "playlist.json"


def load_playlists(file_path: Optional[Union[str, Path]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Loads and strictly validates playlists from the specified JSON file or config/playlist.json.

    Returns:
        Dict[str, Dict[str, Any]]: Validated dictionary mapping playlist_id -> { "name": str, "songs": list }
    Raises:
        FileNotFoundError: If the configuration file cannot be found.
        ValueError: If JSON is malformed, missing required fields, or structurally invalid.
    """
    target_path = Path(file_path).resolve() if file_path else DEFAULT_PLAYLIST_PATH

    if not target_path.is_file():
        err_msg = f"Playlist configuration file does not exist: {target_path.name}"
        logger.error(f"[PLAYLIST_LOADER] {err_msg}")
        raise FileNotFoundError(err_msg)

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as jde:
        err_msg = f"Malformed JSON in playlist file: {jde.msg} (line {jde.lineno}, col {jde.colno})"
        logger.error(f"[PLAYLIST_LOADER] {err_msg}")
        raise ValueError(err_msg)
    except Exception as e:
        err_msg = f"Unable to read playlist file: {type(e).__name__}"
        logger.error(f"[PLAYLIST_LOADER] {err_msg}")
        raise ValueError(err_msg)

    if not isinstance(data, dict):
        raise ValueError("Root playlist configuration must be a JSON object.")

    playlists = data.get("playlists")
    if not isinstance(playlists, dict):
        raise ValueError("Configuration must contain a 'playlists' object.")

    if not playlists:
        raise ValueError("Playlist configuration is empty: 'playlists' object contains no entries.")

    validated: Dict[str, Dict[str, Any]] = {}

    for pl_id, pl_data in playlists.items():
        if not isinstance(pl_id, str) or not pl_id.strip():
            raise ValueError(f"Invalid playlist identifier: '{pl_id}'. Identifier must be a non-empty string.")

        clean_id = pl_id.strip().lower()

        if not isinstance(pl_data, dict):
            raise ValueError(f"Playlist entry for '{clean_id}' must be an object.")

        name = pl_data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Playlist '{clean_id}' missing required string field 'name'.")

        raw_songs = pl_data.get("songs")
        if not isinstance(raw_songs, list) or len(raw_songs) == 0:
            raise ValueError(f"Playlist '{clean_id}' must contain a non-empty 'songs' list.")

        validated_songs: List[Dict[str, str]] = []
        for idx, s in enumerate(raw_songs):
            if not isinstance(s, dict):
                raise ValueError(f"Song entry at index {idx} in playlist '{clean_id}' must be an object.")

            title = s.get("title")
            query = s.get("query")

            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"Song at index {idx} in playlist '{clean_id}' missing required 'title'.")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"Song at index {idx} in playlist '{clean_id}' missing required 'query'.")

            validated_songs.append({
                "title": title.strip(),
                "query": query.strip(),
            })

        validated[clean_id] = {
            "name": name.strip(),
            "songs": validated_songs,
        }

    return validated


def get_legacy_playlists_dict(file_path: Optional[Union[str, Path]] = None) -> Dict[str, List[str]]:
    """
    Returns a backward-compatible mapping of playlist_id -> list of queries (strings)
    derived directly from config/playlist.json.
    """
    try:
        data = load_playlists(file_path=file_path)
        legacy: Dict[str, List[str]] = {}
        for pl_id, pl_obj in data.items():
            legacy[pl_id] = [s["query"] for s in pl_obj["songs"]]
        return legacy
    except Exception as e:
        logger.warning(f"[PLAYLIST_LOADER] Fallback notice for legacy loader: {e}")
        return {}

