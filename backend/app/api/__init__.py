import base64
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Tuple
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()

SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_SCOPES = (
    "user-read-playback-state user-modify-playback-state "
    "user-read-currently-playing user-library-modify"
)

spotify_state: dict[str, Any] = {
    "oauth_state": None,
    "access_token": None,
    "refresh_token": None,
    "expires_at": 0,
}


class ActionResponse(BaseModel):
    ok: bool
    message: str


@router.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok"}


def get_env_required(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing env var: {key}")
    return value


def spotify_request(
    method: str,
    url: str,
    token: str,
    data: Optional[bytes] = None,
    content_type: Optional[str] = "application/json",
) -> Tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def token_request(payload: dict[str, str]) -> dict[str, Any]:
    client_id = get_env_required("SPOTIFY_CLIENT_ID")
    client_secret = get_env_required("SPOTIFY_CLIENT_SECRET")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{SPOTIFY_ACCOUNTS}/api/token",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=400, detail=f"Spotify token error: {detail}") from exc
    import json

    return json.loads(raw)


def refresh_if_needed() -> str:
    access = spotify_state.get("access_token")
    refresh = spotify_state.get("refresh_token")
    exp = int(spotify_state.get("expires_at") or 0)
    if access and exp > int(time.time()) + 60:
        return str(access)
    if not refresh:
        raise HTTPException(status_code=401, detail="Spotify not connected")
    token_data = token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": str(refresh),
        }
    )
    spotify_state["access_token"] = token_data.get("access_token")
    if token_data.get("refresh_token"):
        spotify_state["refresh_token"] = token_data.get("refresh_token")
    spotify_state["expires_at"] = int(time.time()) + int(token_data.get("expires_in", 3600))
    return str(spotify_state["access_token"])


def get_player_state(token: str) -> dict[str, Any]:
    import json

    status, data = spotify_request("GET", f"{SPOTIFY_API}/me/player", token, data=None, content_type=None)
    if status == 204:
        return {"is_playing": False, "device": None, "item": None}
    if status >= 400:
        raise HTTPException(status_code=400, detail=f"Spotify player error ({status})")
    return json.loads(data.decode("utf-8"))

def get_current_track_id(token: str) -> Optional[str]:
    import json

    # More reliable for "like" than /me/player on some devices/sessions.
    status, data = spotify_request(
        "GET",
        f"{SPOTIFY_API}/me/player/currently-playing",
        token,
        data=None,
        content_type=None,
    )
    if status == 200:
        payload = json.loads(data.decode("utf-8"))
        item = payload.get("item") or {}
        if payload.get("currently_playing_type") == "track" and item.get("id"):
            return str(item.get("id"))
    elif status not in (204, 202):
        # Don't hard-fail; fall back to /me/player.
        pass

    player = get_player_state(token)
    item = player.get("item") or {}
    if item.get("type") == "track" and item.get("id"):
        return str(item.get("id"))
    return None


@router.get("/spotify/login", tags=["spotify"])
async def spotify_login() -> RedirectResponse:
    client_id = get_env_required("SPOTIFY_CLIENT_ID")
    redirect_uri = get_env_required("SPOTIFY_REDIRECT_URI")
    state = secrets.token_urlsafe(24)
    spotify_state["oauth_state"] = state
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": SPOTIFY_SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
            # Force consent prompt so updated scopes are always applied.
            "show_dialog": "true",
        }
    )
    return RedirectResponse(url=f"{SPOTIFY_ACCOUNTS}/authorize?{params}", status_code=307)


@router.get("/spotify/callback", tags=["spotify"])
async def spotify_callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:8080").rstrip("/")
    if error:
        return RedirectResponse(url=f"{frontend_url}/?spotify=error", status_code=307)
    if not code:
        return RedirectResponse(url=f"{frontend_url}/?spotify=missing_code", status_code=307)
    expected_state = spotify_state.get("oauth_state")
    if not expected_state or state != expected_state:
        return RedirectResponse(url=f"{frontend_url}/?spotify=state_mismatch", status_code=307)
    token_data = token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_env_required("SPOTIFY_REDIRECT_URI"),
        }
    )
    spotify_state["access_token"] = token_data.get("access_token")
    spotify_state["refresh_token"] = token_data.get("refresh_token")
    spotify_state["expires_at"] = int(time.time()) + int(token_data.get("expires_in", 3600))
    return RedirectResponse(url=f"{frontend_url}/?spotify=connected", status_code=307)


@router.get("/spotify/status", tags=["spotify"])
async def spotify_status() -> dict[str, Any]:
    if not spotify_state.get("refresh_token"):
        return {"connected": False}
    token = refresh_if_needed()
    player = get_player_state(token)
    item = player.get("item") or {}
    artists = ", ".join(a.get("name", "") for a in (item.get("artists") or []) if a.get("name"))
    album = item.get("album") or {}
    images = album.get("images") or []
    album_cover_url = images[0].get("url") if images and isinstance(images[0], dict) else None
    device = player.get("device") or {}
    return {
        "connected": True,
        "is_playing": bool(player.get("is_playing")),
        "device_id": device.get("id"),
        "device_name": device.get("name"),
        "track_id": item.get("id"),
        "track_name": item.get("name"),
        "artist_name": artists,
        "album_cover_url": album_cover_url,
    }


@router.post("/spotify/play-pause", tags=["spotify"], response_model=ActionResponse)
async def spotify_play_pause() -> ActionResponse:
    token = refresh_if_needed()
    player = get_player_state(token)
    is_playing = bool(player.get("is_playing"))
    target = "pause" if is_playing else "play"
    status, _ = spotify_request("PUT", f"{SPOTIFY_API}/me/player/{target}", token, data=b"")
    if status >= 400:
        raise HTTPException(status_code=400, detail=f"Spotify {target} failed ({status})")
    return ActionResponse(ok=True, message=f"{'Paused' if is_playing else 'Playing'}")


@router.post("/spotify/next", tags=["spotify"], response_model=ActionResponse)
async def spotify_next() -> ActionResponse:
    token = refresh_if_needed()
    status, _ = spotify_request("POST", f"{SPOTIFY_API}/me/player/next", token, data=b"")
    if status >= 400:
        raise HTTPException(status_code=400, detail=f"Spotify next failed ({status})")
    return ActionResponse(ok=True, message="Skipped to next")


@router.post("/spotify/previous", tags=["spotify"], response_model=ActionResponse)
async def spotify_previous() -> ActionResponse:
    token = refresh_if_needed()
    status, _ = spotify_request("POST", f"{SPOTIFY_API}/me/player/previous", token, data=b"")
    if status >= 400:
        raise HTTPException(status_code=400, detail=f"Spotify previous failed ({status})")
    return ActionResponse(ok=True, message="Went to previous")


@router.post("/spotify/like-current", tags=["spotify"], response_model=ActionResponse)
async def spotify_like_current() -> ActionResponse:
    token = refresh_if_needed()
    track_id = get_current_track_id(token)
    if not track_id:
        raise HTTPException(status_code=400, detail="No active music track to save")
    # Try both supported formats (query and JSON body) for broader compatibility.
    query = urllib.parse.urlencode({"ids": track_id})
    status, body = spotify_request(
        "PUT",
        f"{SPOTIFY_API}/me/tracks?{query}",
        token,
        data=b"",
        content_type=None,
    )
    if status >= 400:
        alt_payload = json.dumps({"ids": [track_id]}).encode("utf-8")
        alt_status, alt_body = spotify_request(
            "PUT",
            f"{SPOTIFY_API}/me/tracks",
            token,
            data=alt_payload,
            content_type="application/json",
        )
        if alt_status >= 400:
            detail = body.decode("utf-8", errors="ignore")
            alt_detail = alt_body.decode("utf-8", errors="ignore")
            if status == 403 or alt_status == 403:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Spotify denied save. This is usually missing library scope or track type restriction. "
                        f"raw={detail or '<empty>'}; alt={alt_detail or '<empty>'}"
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail=f"Spotify like failed ({status}/{alt_status}): {detail} | {alt_detail}",
            )
    return ActionResponse(ok=True, message="Saved track")
