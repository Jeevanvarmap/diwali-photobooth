"""Upload finished photos to a Google Drive folder and share the link."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import qrcode
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import CREDENTIALS_PATH, DRIVE_FOLDER_NAME, TOKEN_PATH

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def configured() -> bool:
    return CREDENTIALS_PATH.exists() or TOKEN_PATH.exists()


def upload_session(
    local_dir: Path,
    day: str,
    session_id: str,
    filenames: list[str],
    share: bool = True,
) -> tuple[str, str]:
    service = _service()
    root_id = _folder(service, DRIVE_FOLDER_NAME, parent_id=None)
    day_id = _folder(service, day, parent_id=root_id)
    session_folder = _folder(service, session_id, parent_id=day_id)
    for name in filenames:
        path = local_dir / name
        if not path.exists():
            continue
        media = MediaFileUpload(path, mimetype="image/jpeg", resumable=False)
        service.files().create(
            body={"name": name, "parents": [session_folder]},
            media_body=media,
            fields="id",
        ).execute()
    warning = ""
    if share:
        try:
            service.permissions().create(
                fileId=session_folder,
                body={"type": "anyone", "role": "reader"},
                fields="id",
            ).execute()
        except Exception as exc:
            log.warning("Could not share the Drive folder publicly: %s", exc)
            warning = "Photos are in your Drive, but link sharing was blocked. Share the folder from Drive."
    return f"https://drive.google.com/drive/folders/{session_folder}", warning


def qr_png(url: str) -> bytes:
    image = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif CREDENTIALS_PATH.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError("Add credentials.json to upload photos to Google Drive.")
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _folder(service, name: str, parent_id: str | None) -> str:
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    found = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
        .get("files", [])
    )
    if found:
        return found[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    created = service.files().create(body=body, fields="id").execute()
    return created["id"]
