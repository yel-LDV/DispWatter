import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import aiohttp

from backend.config import settings

logger = logging.getLogger(__name__)

OTA_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "ota_config.json"

GITHUB_REPO = "yel-LDV/DispWatter"
GITHUB_API_BASE = "https://api.github.com/repos/yel-LDV/DispWatter"


def _load_ota_config() -> dict[str, Any]:
    try:
        return json.loads(OTA_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load ota_config.json: %s", exc)
        return {
            "verified_branches": ["main", "stable"],
            "unverified_branches": ["develop", "feature/*"],
            "fork_detection": True,
            "original_repository": GITHUB_REPO,
        }


async def list_versions() -> list[dict[str, Any]]:
    releases = await _fetch_releases()
    config = _load_ota_config()
    versions = []
    for release in releases:
        tag = release.get("tag_name", "").lstrip("v")
        metadata = release.get("metadata", {})
        branch = metadata.get("branch", release.get("target_commitish", ""))
        is_fork = metadata.get("is_fork", False)
        release_type = metadata.get("type", _classify_branch(branch, config, is_fork))
        firmware_asset = _find_firmware_asset(release.get("assets", []))
        versions.append({
            "tag": tag,
            "name": release.get("name", tag),
            "type": release_type,
            "branch": branch,
            "commit": release.get("commit", ""),
            "is_fork": is_fork,
            "created_at": release.get("created_at", ""),
            "published_at": release.get("published_at", ""),
            "body": release.get("body", ""),
            "download_url": firmware_asset.get("url") if firmware_asset else None,
            "size": firmware_asset.get("size") if firmware_asset else None,
        })
    versions.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    return versions


async def get_version(version_tag: str) -> Optional[dict[str, Any]]:
    release = await _fetch_release(version_tag)
    if not release:
        return None
    metadata = release.get("metadata", {})
    branch = metadata.get("branch", release.get("target_commitish", ""))
    is_fork = metadata.get("is_fork", False)
    config = _load_ota_config()
    release_type = metadata.get("type", _classify_branch(branch, config, is_fork))
    firmware_asset = _find_firmware_asset(release.get("assets", []))
    return {
        "tag": version_tag.lstrip("v"),
        "name": release.get("name", version_tag),
        "type": release_type,
        "branch": branch,
        "commit": release.get("commit", ""),
        "is_fork": is_fork,
        "created_at": release.get("created_at", ""),
        "published_at": release.get("published_at", ""),
        "body": release.get("body", ""),
        "download_url": firmware_asset.get("url") if firmware_asset else None,
        "size": firmware_asset.get("size") if firmware_asset else None,
    }


async def download_binary(version_tag: str) -> Optional[bytes]:
    asset_url = await _get_firmware_url(version_tag)
    if not asset_url:
        logger.error("No firmware binary found for %s", version_tag)
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(asset_url) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.error("Download failed for %s: HTTP %d", version_tag, resp.status)
                return None
    except Exception as exc:
        logger.error("Download error for %s: %s", version_tag, exc)
        return None


async def verify_binary(binary: bytes, version_tag: str) -> bool:
    checksum_file = await _download_checksum(version_tag)
    if not checksum_file:
        logger.warning("No checksum file for %s, skipping verification", version_tag)
        return True
    expected = checksum_file.split()[0] if checksum_file else ""
    actual = hashlib.sha256(binary).hexdigest()
    if actual != expected:
        logger.error("Checksum mismatch for %s: expected %s, got %s", version_tag, expected, actual)
        return False
    return True


async def push_to_device(
    websocket: Any,
    version_tag: str,
    chunk_size: int = 4096,
) -> bool:
    binary = await download_binary(version_tag)
    if not binary:
        await _send_ota_event(websocket, "ota_error", {"message": "Download failed"})
        return False
    if not await verify_binary(binary, version_tag):
        await _send_ota_event(websocket, "ota_error", {"message": "Checksum verification failed"})
        return False
    total = len(binary)
    await _send_ota_event(websocket, "ota_start", {
        "version": version_tag.lstrip("v"),
        "size": total,
    })
    offset = 0
    while offset < total:
        chunk = binary[offset:offset + chunk_size]
        await _send_ota_event(websocket, "ota_chunk", {
            "data": chunk.hex(),
            "offset": offset,
            "total": total,
        })
        offset += len(chunk)
    await _send_ota_event(websocket, "ota_complete", {
        "version": version_tag.lstrip("v"),
        "size": total,
    })
    return True


async def _fetch_releases() -> list[dict[str, Any]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GITHUB_API_BASE}/releases") as resp:
                if resp.status == 200:
                    releases = await resp.json()
                    enriched = []
                    for release in releases:
                        meta = await _fetch_metadata(release.get("assets", []))
                        release["metadata"] = meta
                        enriched.append(release)
                    return enriched
    except Exception as exc:
        logger.error("Failed to fetch releases: %s", exc)
    return []


async def _fetch_release(version_tag: str) -> Optional[dict[str, Any]]:
    tag = version_tag if version_tag.startswith("v") else f"v{version_tag}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GITHUB_API_BASE}/releases/tags/{tag}") as resp:
                if resp.status == 200:
                    release = await resp.json()
                    meta = await _fetch_metadata(release.get("assets", []))
                    release["metadata"] = meta
                    return release
    except Exception as exc:
        logger.error("Failed to fetch release %s: %s", version_tag, exc)
    return None


async def _fetch_metadata(assets: list[dict]) -> dict[str, Any]:
    meta_asset = None
    for asset in assets:
        if asset.get("name") == "metadata.json":
            meta_asset = asset
            break
    if not meta_asset:
        return {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(meta_asset["url"]) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch metadata: %s", exc)
    return {}


async def _get_firmware_url(version_tag: str) -> Optional[str]:
    release = await _fetch_release(version_tag)
    if not release:
        return None
    firmware_asset = _find_firmware_asset(release.get("assets", []))
    return firmware_asset.get("url") if firmware_asset else None


async def _download_checksum(version_tag: str) -> Optional[str]:
    release = await _fetch_release(version_tag)
    if not release:
        return None
    checksum_asset = None
    for asset in release.get("assets", []):
        if asset.get("name") == "checksum.sha256":
            checksum_asset = asset
            break
    if not checksum_asset:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(checksum_asset["url"]) as resp:
                if resp.status == 200:
                    return (await resp.text()).strip()
    except Exception as exc:
        logger.warning("Failed to download checksum: %s", exc)
    return None


def _find_firmware_asset(assets: list[dict]) -> Optional[dict]:
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".bin") and "firmware" in name:
            return asset
    return None


def _classify_branch(
    branch: str,
    config: dict[str, Any],
    is_fork: bool,
) -> str:
    if is_fork and config.get("fork_detection"):
        return "insecure"
    verified = config.get("verified_branches", [])
    for pattern in verified:
        if _match_branch_pattern(branch, pattern):
            return "stable"
    return "experimental"


def _match_branch_pattern(branch: str, pattern: str) -> bool:
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return branch.startswith(prefix + "/")
    return branch == pattern


async def _send_ota_event(websocket: Any, event: str, data: dict) -> None:
    try:
        await websocket.send(json.dumps({"event": event, **data}))
    except Exception as exc:
        logger.error("Failed to send OTA event %s: %s", event, exc)
