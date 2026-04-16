"""
pdf_generator.py — 使用 ReportLab 生成 A4 報價單 PDF
排版模擬 index.html 的 A4 預覽
"""
import io
import os
import math
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black

from parser import QuoteData

# ── Page constants ──
PAGE_W, PAGE_H = A4  # 210mm x 297mm
MARGIN_L = 15 * mm
MARGIN_R = 15 * mm
MARGIN_T = 20 * mm
MARGIN_B = 15 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# ── Font setup ──
FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')
FONT_REGULAR = 'NotoSansTC'
FONT_BOLD = 'NotoSansTC-Bold'
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    regular = os.path.join(FONT_DIR, 'NotoSansTC-Regular.ttf')
    bold = os.path.join(FONT_DIR, 'NotoSansTC-Bold.ttf')
    if os.path.exists(regular):
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular))
    if os.path.exists(bold):
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))
    _fonts_registered = True


def _fmt(n) -> str:
    """Format number with 1 decimal and thousands separator."""
    try:
        v = float(n)
        return f'{v:,.1f}'
    except (ValueError, TypeError):
        return ''


def _draw_text(c: canvas.Canvas, x, y, text, font=None, size=14, bold=False, align='left', max_width=None):
    """Draw text with optional auto-scaling if it exceeds max_width."""
    fn = font or (FONT_BOLD if bold else FONT_REGULAR)
    c.setFont(fn, size)
    tw = c.stringWidth(text, fn, size)
    if max_width and tw > max_width and max_width > 0:
        scale = max_width / tw
        c.saveState()
        c.translate(x, y)
        c.scale(scale, 1)
        if align == 'center':
            c.drawCentredString(tw / 2, 0, text)
        elif align == 'right':
            c.drawRightString(tw, 0, text)
        else:
            c.drawString(0, 0, text)
        c.restoreState()
        return size
    if align == 'center':
        c.drawCentredString(x, y, text)
    elif align == 'right':
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)
    return size


def generate_pdf(data: QuoteData) -> bytes:
    """Generate A4 PDF from QuoteData and return bytes."""
    _register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    is_new = '新品' in data.doc_title
    y = PAGE_H - MARGIN_T

    # ── Fixed footer area (always at bottom) ──
    FOOTER_SLOGAN_Y = MARGIN_B + 6
    FOOTER_STAMP_Y = MARGIN_B + 50
    FOOTER_LINE_Y = FOOTER_STAMP_Y + 16
    # Reserve space: content must not go below this
    CONTENT_BOTTOM = FOOTER_LINE_Y + 100  # 100pt for stamp area

    # ── Company header (centered) ──
    _draw_text(c, PAGE_W / 2, y, data.company.name, bold=True, size=20, align='center',
               max_width=CONTENT_W)
    y -= 24
    _draw_text(c, PAGE_W / 2, y, data.company.address, bold=True, size=13, align='center',
               max_width=CONTENT_W)
    y -= 20
    contact_line = f'{data.company.phone}    聯絡人 {data.company.contact}'
    _draw_text(c, PAGE_W / 2, y, contact_line, bold=True, size=12, align='center',
               max_width=CONTENT_W)
    y -= 32

    # ── Document title ──
    _draw_text(c, PAGE_W / 2, y, data.doc_title, bold=True, size=16, align='center')
    y -= 30

    # ── Customer info ──
    info = data.info
    line_h = 22
    left_x = MARGIN_L
    right_x = MARGIN_L + CONTENT_W * 0.52
    half_w = CONTENT_W * 0.48

    # Brand name + code
    if info.brand_name or info.code:
        if info.brand_name:
            _draw_text(c, left_x, y, f'店名：{info.brand_name}', bold=True, size=12,
                       max_width=half_w)
        if info.code:
            _draw_text(c, right_x, y, f'代號：{info.code}', bold=True, size=12,
                       max_width=half_w)
        y -= line_h

    # Title (company name)
    _draw_text(c, left_x, y, f'抬頭：{info.title}', bold=True, size=12, max_width=CONTENT_W)
    y -= line_h

    # Contact + phone
    _draw_text(c, left_x, y, f'聯絡人：{info.contact_name}', bold=True, size=12,
               max_width=half_w)
    phones = [p.strip() for p in info.phone.split('/') if p.strip()] if info.phone else []
    if phones:
        first = phones[0]
        if not any(kw in first.upper() for kw in ['TEL', 'MOB', 'PHONE', '手機', '電話']):
            first = f'TEL : {first}'
        _draw_text(c, right_x, y, first, bold=True, size=12, max_width=half_w)
        for extra_phone in phones[1:]:
            y -= line_h
            _draw_text(c, right_x, y, extra_phone, bold=True, size=12, max_width=half_w)
    y -= line_h

    # Address + tax ID
    addr_label = '店鋪地址' if info.invoice_address else '地址'
    _draw_text(c, left_x, y, f'{addr_label}：{info.address}', bold=True, size=12,
               max_width=half_w)
    _draw_text(c, right_x, y, f'統一編號：{info.tax_id}', bold=True, size=12,
               max_width=half_w)
    y -= line_h

    if info.invoice_address:
        _draw_text(c, left_x, y, f'發票地址：{info.invoice_address}', bold=True, size=12,
                   max_width=half_w)
        y -= line_h

    # Unit + date
    _draw_text(c, left_x, y, '單位：條 / 幣別：新台幣', bold=True, size=12, max_width=half_w)
    _draw_text(c, right_x, y, f'日期：{info.date}', bold=True, size=12, max_width=half_w)
    y -= 28

    # ── Items table ──
    if is_new:
        y = _draw_new_product_table(c, data.items, y)
    else:
        y = _draw_rental_table(c, data.items, y)

    # ── Table note ──
    if data.table_note:
        y -= 20
        for note_line in data.table_note.split('\n'):
            if not note_line.strip():
                continue
            _draw_text(c, MARGIN_L, y, note_line, bold=True, size=12, max_width=CONTENT_W)
            y -= 18

    # ── Remarks ──
    y -= 16
    for remark_line in data.remarks.split('\n'):
        if not remark_line.strip():
            continue
        _draw_text(c, MARGIN_L, y, remark_line, bold=True, size=12, max_width=CONTENT_W)
        y -= 18

    # ── Footer (fixed position at bottom of A4) ──
    # Horizontal line
    c.setLineWidth(0.8)
    c.line(MARGIN_L, FOOTER_LINE_Y, PAGE_W - MARGIN_R, FOOTER_LINE_Y)

    # Stamp text
    _draw_text(c, MARGIN_L, FOOTER_STAMP_Y, '確認後請蓋章回傳，謝謝您。', bold=True, size=12)

    # Bottom slogan (always at the very bottom)
    _draw_text(c, PAGE_W / 2, FOOTER_SLOGAN_Y,
               '專 業 洗 衣 管 理 · 衣 物 財 產 編 列',
               bold=True, size=14, align='center')

    c.save()
    return buf.getvalue()


def _draw_new_product_table(c: canvas.Canvas, items, y) -> float:
    """Draw table for 新品報價單: 品項 / 數量 / 單價 / 金額 + tax + total."""
    table_w = CONTENT_W * 0.70
    col_w = [table_w * 0.50, table_w * 0.15, table_w * 0.15, table_w * 0.20]
    x0 = MARGIN_L
    row_h = 24

    # Header
    _draw_table_rect(c, x0, y, col_w, row_h)
    headers = ['品項', '數量', '單價', '金額']
    aligns = ['left', 'center', 'center', 'center']
    for j, (header, align) in enumerate(zip(headers, aligns)):
        cx = sum(col_w[:j]) + x0
        if align == 'center':
            cx += col_w[j] / 2
            _draw_text(c, cx, y - 16, header, bold=True, size=12, align='center')
        else:
            _draw_text(c, cx + 6, y - 16, header, bold=True, size=12)
    y -= row_h

    # Items
    subtotal = 0
    for item in items:
        _draw_table_rect(c, x0, y, col_w, row_h)
        q = _safe_float(item.quantity)
        p = _safe_float(item.price)
        amount = q * p
        subtotal += amount

        _draw_text(c, x0 + 6, y - 16, item.name, size=12, max_width=col_w[0] - 12)
        _draw_text(c, x0 + col_w[0] + col_w[1] / 2, y - 16, item.quantity, size=12, align='center')
        _draw_text(c, x0 + col_w[0] + col_w[1] + col_w[2] - 8, y - 16, _fmt(p), size=12, align='right')
        _draw_text(c, x0 + sum(col_w[:3]) + col_w[3] - 8, y - 16, _fmt(amount), size=12, align='right')
        y -= row_h

    # Tax row
    tax = subtotal * 0.05
    _draw_table_rect(c, x0, y, col_w, row_h)
    _draw_text(c, x0 + col_w[0] + col_w[1] + col_w[2] - 8, y - 16, '稅金 5%', bold=True, size=12, align='right')
    _draw_text(c, x0 + sum(col_w[:3]) + col_w[3] - 8, y - 16, _fmt(tax), size=12, align='right')
    y -= row_h

    # Total row
    total = subtotal + tax
    _draw_table_rect(c, x0, y, col_w, row_h)
    _draw_text(c, x0 + col_w[0] + col_w[1] + col_w[2] - 8, y - 16, '總計', bold=True, size=12, align='right')
    _draw_text(c, x0 + sum(col_w[:3]) + col_w[3] - 8, y - 16, _fmt(total), bold=True, size=12, align='right')
    y -= row_h

    return y


def _draw_rental_table(c: canvas.Canvas, items, y) -> float:
    """Draw table for 租賃洗滌報價單: two-column layout with 品項 / 單價."""
    mid = len(items)
    half = math.ceil(mid / 2)
    left_items = items[:half]
    right_items = items[half:]

    col_pair_w = CONTENT_W * 0.48
    col_name_w = col_pair_w * 0.75
    col_price_w = col_pair_w * 0.25
    row_h = 24
    gap = CONTENT_W * 0.04

    max_rows = max(len(left_items), len(right_items))

    for side, side_items in enumerate([left_items, right_items]):
        if not side_items:
            continue
        x0 = MARGIN_L + side * (col_pair_w + gap)
        cur_y = y

        # Header
        _draw_table_rect(c, x0, cur_y, [col_name_w, col_price_w], row_h)
        _draw_text(c, x0 + 6, cur_y - 16, '品項', bold=True, size=12)
        _draw_text(c, x0 + col_name_w + col_price_w / 2, cur_y - 16, '單價', bold=True, size=12, align='center')
        cur_y -= row_h

        for item in side_items:
            _draw_table_rect(c, x0, cur_y, [col_name_w, col_price_w], row_h)
            _draw_text(c, x0 + 6, cur_y - 16, item.name, size=12, max_width=col_name_w - 12)
            _draw_text(c, x0 + col_name_w + col_price_w - 8, cur_y - 16, item.price, size=12, align='right')
            cur_y -= row_h

    y -= row_h * (1 + max_rows)
    return y


def _draw_table_rect(c: canvas.Canvas, x, y, col_widths, row_h):
    """Draw a row of table cells."""
    c.setLineWidth(0.5)
    cx = x
    total_w = sum(col_widths)
    # Outer rect
    c.rect(x, y - row_h, total_w, row_h)
    # Inner column lines
    for w in col_widths[:-1]:
        cx += w
        c.line(cx, y, cx, y - row_h)


def _safe_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0
