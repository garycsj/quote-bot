"""
gdrive.py — Google Drive 上傳報價單 PDF
在報價單資料夾內自動建立客戶子資料夾，並上傳 PDF
"""
import io
import os
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
    """Build folder name matching Notion format: 代號 品牌名."""
    parts = []
    if data.info.code:
        parts.append(data.info.code)
    if data.info.brand_name:
        parts.append(data.info.brand_name)
    if not parts:
        return data.info.title or '未命名客戶'
    return ' '.join(parts)


def _find_folder(service, parent_id: str, folder_name: str) -> str | None:
    """Find a folder by name under parent. Returns folder ID or None."""
    query = (
        f"'{parent_id}' in parents "
        f"and name = '{folder_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id, name)', pageSize=1).execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def _create_folder(service, parent_id: str, folder_name: str) -> str:
    """Create a folder under parent. Returns new folder ID."""
    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']


def upload_quote_pdf(data: QuoteData, pdf_bytes: bytes) -> tuple[str, str]:
    """
    Upload quote PDF to Google Drive.
    Creates folder: 報價單/{代號 品牌名}/品牌名_報價單類型.pdf
    Returns (folder_name, folder_link).
    """
    folder_name = _build_folder_name(data)
    service = _get_drive_service()

    # Find or create customer subfolder
    folder_id = _find_folder(service, QUOTES_FOLDER_ID, folder_name)
    if not folder_id:
        folder_id = _create_folder(service, QUOTES_FOLDER_ID, folder_name)
        logger.info(f'Created Drive folder: {folder_name}')
    else:
        logger.info(f'Drive folder already exists: {folder_name}')

    # Build PDF filename
    customer = data.info.brand_name or data.info.title or '報價單'
    pdf_filename = f'{customer}_{data.doc_title}.pdf'

    # Upload PDF
    file_metadata = {
        'name': pdf_filename,
        'parents': [folder_id],
        'mimeType': 'application/pdf',
    }
    media = MediaIoBaseUpload(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
    )
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    logger.info(f'Uploaded: {folder_name}/{pdf_filename}')

    # Build folder link
    folder_link = f'https://drive.google.com/drive/folders/{folder_id}'

    return folder_name, folder_link
