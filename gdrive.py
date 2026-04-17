"""
gdrive.py — Google Drive 上傳報價單 PDF
在報價單資料夾內自動建立客戶子資料夾，並上傳 PDF
"""
import io
import os
import re
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from parser import QuoteData

logger = logging.getLogger(__name__)

# 報價單根資料夾 ID
QUOTES_FOLDER_ID = '1mkbxuPzrw7hg2ovIa4O8skguJPyHGKK5'


def _get_drive_service():
    """Build Google Drive service using OAuth refresh token."""
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError('Missing Google OAuth environment variables')

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri='https://oauth2.googleapis.com/token',
    )
    return build('drive', 'v3', credentials=creds)


def _build_folder_name(data: QuoteData) -> str:
    """Build folder name: 代號-品牌名."""
    parts = []
    if data.info.code:
        parts.append(data.info.code)
    if data.info.brand_name:
        parts.append(data.info.brand_name)
    if not parts:
        return data.info.title or '未命名客戶'
    return '-'.join(parts)


def _normalize_name(name: str) -> str:
    """Normalize folder name: remove spaces around dashes for comparison."""
    return re.sub(r'\s*-\s*', '-', name).strip()


def _list_subfolders(service, parent_id: str) -> list[dict]:
    """List all subfolders under parent. Returns list of {id, name}."""
    query = (
        f"'{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    all_folders = []
    page_token = None
    while True:
        results = service.files().list(
            q=query, fields='nextPageToken, files(id, name)', pageSize=100,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageToken=page_token,
        ).execute()
        all_folders.extend(results.get('files', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return all_folders


def find_matching_folder(data: QuoteData) -> dict:
    """
    Search for matching customer folder in Google Drive.
    Returns dict with keys:
      - match_type: 'exact', 'similar', 'none'
      - folder_id: Drive folder ID (if found)
      - folder_name: existing folder name (if found)
    """
    target_name = _build_folder_name(data)
    target_normalized = _normalize_name(target_name)
    service = _get_drive_service()

    subfolders = _list_subfolders(service, QUOTES_FOLDER_ID)

    for folder in subfolders:
        existing_name = folder['name']
        if existing_name == target_name:
            return {'match_type': 'exact', 'folder_id': folder['id'], 'folder_name': existing_name}

    # No exact match — check for similar (normalized match)
    for folder in subfolders:
        existing_name = folder['name']
        existing_normalized = _normalize_name(existing_name)
        if existing_normalized == target_normalized:
            return {'match_type': 'similar', 'folder_id': folder['id'], 'folder_name': existing_name}

    return {'match_type': 'none', 'folder_id': None, 'folder_name': None}


def _create_folder(service, parent_id: str, folder_name: str) -> str:
    """Create a folder under parent. Returns new folder ID."""
    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    folder = service.files().create(
        body=metadata, fields='id', supportsAllDrives=True,
    ).execute()
    return folder['id']


def upload_pdf_to_folder(folder_id: str, data: QuoteData, pdf_bytes: bytes) -> None:
    """Upload PDF to an existing folder."""
    service = _get_drive_service()
    customer = data.info.brand_name or data.info.title or '報價單'
    pdf_filename = f'{customer}_{data.doc_title}.pdf'

    file_metadata = {
        'name': pdf_filename,
        'parents': [folder_id],
        'mimeType': 'application/pdf',
    }
    media = MediaIoBaseUpload(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
    )
    service.files().create(
        body=file_metadata, media_body=media, fields='id', supportsAllDrives=True,
    ).execute()
    logger.info(f'Uploaded PDF to folder {folder_id}: {pdf_filename}')


def create_folder_and_upload(data: QuoteData, pdf_bytes: bytes) -> tuple[str, str]:
    """Create new customer folder and upload PDF. Returns (folder_name, folder_link)."""
    folder_name = _build_folder_name(data)
    service = _get_drive_service()
    folder_id = _create_folder(service, QUOTES_FOLDER_ID, folder_name)
    logger.info(f'Created Drive folder: {folder_name}')

    upload_pdf_to_folder(folder_id, data, pdf_bytes)

    folder_link = f'https://drive.google.com/drive/folders/{folder_id}'
    return folder_name, folder_link


def get_folder_link(folder_id: str) -> str:
    """Build Google Drive folder link."""
    return f'https://drive.google.com/drive/folders/{folder_id}'
