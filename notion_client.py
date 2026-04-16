"""
notion_client.py — Notion 客戶資料庫操作
查詢、新增、更新客戶資料
"""
import os
import logging
import requests

from parser import QuoteData

logger = logging.getLogger(__name__)

NOTION_API = 'https://api.notion.com/v1'
NOTION_VERSION = '2022-06-28'
# Notion 資料庫 ID (從 URL 取得)
DATABASE_ID = '2008471adf428056b5f4cf615beab52b'


def _headers():
    token = os.environ.get('NOTION_TOKEN')
    if not token:
        raise RuntimeError('Missing NOTION_TOKEN environment variable')
    return {
        'Authorization': f'Bearer {token}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
    }


def _build_customer_name(data: QuoteData) -> str:
    """Build customer name in format: 代號 品牌名."""
    parts = []
    if data.info.code:
        parts.append(data.info.code)
    if data.info.brand_name:
        parts.append(data.info.brand_name)
    if not parts:
        return data.info.title or '未命名客戶'
    return ' '.join(parts)


def search_customer(data: QuoteData) -> dict:
    """
    Search for existing customer in Notion database.
    Returns dict with keys:
      - match_type: 'both', 'name_only', 'tax_id_only', 'none'
      - page_id: Notion page ID if found
      - existing_name: existing customer name
      - existing_tax_id: existing tax ID
    """
    customer_name = _build_customer_name(data)
    tax_id = data.info.tax_id

    results = {'match_type': 'none', 'page_id': None, 'existing_name': '', 'existing_tax_id': ''}

    # Search by customer name
    name_match = _query_by_name(customer_name)
    # Search by tax ID
    tax_match = _query_by_tax_id(tax_id) if tax_id else None

    if name_match and tax_match:
        # Check if they point to the same page
        if name_match['id'] == tax_match['id']:
            results['match_type'] = 'both'
            results['page_id'] = name_match['id']
            results['existing_name'] = _get_page_name(name_match)
            results['existing_tax_id'] = _get_page_tax_id(name_match)
        else:
            # Name matches one record, tax ID matches another — treat as name_only
            results['match_type'] = 'name_only'
            results['page_id'] = name_match['id']
            results['existing_name'] = _get_page_name(name_match)
            results['existing_tax_id'] = _get_page_tax_id(name_match)
    elif name_match:
        results['match_type'] = 'name_only'
        results['page_id'] = name_match['id']
        results['existing_name'] = _get_page_name(name_match)
        results['existing_tax_id'] = _get_page_tax_id(name_match)
    elif tax_match:
        results['match_type'] = 'tax_id_only'
        results['page_id'] = tax_match['id']
        results['existing_name'] = _get_page_name(tax_match)
        results['existing_tax_id'] = _get_page_tax_id(tax_match)

    return results


def _query_by_name(name: str) -> dict | None:
    """Query Notion database by customer name."""
    body = {
        'filter': {
            'property': '客戶名稱',
            'title': {'equals': name},
        },
        'page_size': 1,
    }
    resp = requests.post(f'{NOTION_API}/databases/{DATABASE_ID}/query', headers=_headers(), json=body)
    resp.raise_for_status()
    results = resp.json().get('results', [])
    return results[0] if results else None


def _query_by_tax_id(tax_id: str) -> dict | None:
    """Query Notion database by tax ID (統一編號)."""
    if not tax_id:
        return None
    body = {
        'filter': {
            'property': '統一編號',
            'rich_text': {'equals': tax_id},
        },
        'page_size': 1,
    }
    resp = requests.post(f'{NOTION_API}/databases/{DATABASE_ID}/query', headers=_headers(), json=body)
    resp.raise_for_status()
    results = resp.json().get('results', [])
    return results[0] if results else None


def _get_page_name(page: dict) -> str:
    """Extract customer name from a Notion page."""
    try:
        title_prop = page['properties']['客戶名稱']['title']
        return ''.join(t['plain_text'] for t in title_prop) if title_prop else ''
    except (KeyError, IndexError):
        return ''


def _get_page_tax_id(page: dict) -> str:
    """Extract tax ID from a Notion page."""
    try:
        rt = page['properties']['統一編號']['rich_text']
        return ''.join(t['plain_text'] for t in rt) if rt else ''
    except (KeyError, IndexError):
        return ''


def _build_properties(data: QuoteData, drive_link: str = '') -> dict:
    """Build Notion page properties from QuoteData."""
    customer_name = _build_customer_name(data)
    props = {
        '客戶名稱': {
            'title': [{'text': {'content': customer_name}}],
        },
        '聯絡電話': {
            'rich_text': [{'text': {'content': data.info.phone or ''}}],
        },
        '統一編號': {
            'rich_text': [{'text': {'content': data.info.tax_id or ''}}],
        },
    }
    if drive_link:
        props['雲端報價單連結'] = {
            'url': drive_link,
        }
    return props


def create_customer(data: QuoteData, drive_link: str = '') -> str:
    """Create a new customer page in Notion. Returns page ID."""
    body = {
        'parent': {'database_id': DATABASE_ID},
        'properties': _build_properties(data, drive_link),
    }
    resp = requests.post(f'{NOTION_API}/pages', headers=_headers(), json=body)
    resp.raise_for_status()
    page_id = resp.json()['id']
    logger.info(f'Created Notion customer: {_build_customer_name(data)}')
    return page_id


def update_customer(page_id: str, data: QuoteData, drive_link: str = '') -> None:
    """Update an existing customer page in Notion."""
    body = {
        'properties': _build_properties(data, drive_link),
    }
    resp = requests.patch(f'{NOTION_API}/pages/{page_id}', headers=_headers(), json=body)
    resp.raise_for_status()
    logger.info(f'Updated Notion customer: {_build_customer_name(data)}')


def update_drive_link(page_id: str, drive_link: str) -> None:
    """Update only the Google Drive link for a customer."""
    body = {
        'properties': {
            '雲端報價單連結': {
                'url': drive_link,
            },
        },
    }
    resp = requests.patch(f'{NOTION_API}/pages/{page_id}', headers=_headers(), json=body)
    resp.raise_for_status()
    logger.info(f'Updated drive link for page {page_id}')
