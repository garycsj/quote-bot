"""
parser.py — 報價單文字解析器
移植自 index.html 的 parseRaw() JavaScript 邏輯
"""
import re
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class QuoteItem:
    name: str = ''
    price: str = ''
    quantity: str = '1'


@dataclass
class CompanyInfo:
    name: str = '興 霖 事 業 有 限 公 司'
    address: str = '新北市汐止區福德一路 392 巷 45 號'
    phone: str = '(T)02-2694-1431  (F)02-26931491'
    contact: str = '劉睦丞'


@dataclass
class CustomerInfo:
    brand_name: str = ''
    code: str = ''
    title: str = ''
    contact_name: str = ''
    phone: str = ''
    address: str = ''
    invoice_address: str = ''
    tax_id: str = ''
    date: str = ''


@dataclass
class QuoteData:
    doc_title: str = '報價單'
    table_note: str = ''
    info: CustomerInfo = field(default_factory=CustomerInfo)
    company: CompanyInfo = field(default_factory=CompanyInfo)
    items: list = field(default_factory=list)
    remarks: str = ''


DEFAULT_REMARKS = (
    "●以上單價未稅，營業稅 5%外加，付款票期 30 天。\n"
    "●新品提供財產編列管理及車縫線加強服務，以延長使用年限。\n"
    "●提供更換鈕扣、拉鍊及修補等服務，將酌收修補費。\n"
    "●提供客用口布、台布、服務巾、擦拭口布、廚房專用抹布等布品租賃服務。\n"
    "●提供廚衣、圍裙、客用口布、服務巾、擦拭口布及廚房專用抹布等客製化製作。\n"
    "●全程使用負離子磁化軟水洗滌。\n"
    "●服務滿一年可享免費製作店號布標、各項衣物之流水編號及車縫線加強等服務，未滿一年者將酌收服務費。"
)


def parse_raw(raw: str) -> QuoteData:
    lines = raw.split('\n')
    info = CustomerInfo()
    company = CompanyInfo()
    items: list[QuoteItem] = []
    remarks_arr: list[str] = []
    table_note = ''
    doc_title = '報價單'
    mode = 'normal'
    roc_y = datetime.now().year - 1911

    # First line determines doc type
    if lines:
        f = lines[0].strip()
        if '新品報價單' in f:
            doc_title = '新品報價單'
            table_note = '*因布匹有縮率，故尺寸誤差 3-5%屬合理範圍。'
        elif '洗滌報價單' in f or '租賃' in f:
            doc_title = '租賃洗滌報價單'
            table_note = '*每趟最低消費為$500/趟。'
        elif f and '：' not in f and ':' not in f:
            doc_title = f

    for i, line in enumerate(lines):
        t = line.strip()
        if not t:
            continue
        if i == 0 and (t == doc_title or '報價單' in t):
            continue

        # Mode switches
        if re.match(r'^品項[：:\s]', t) or t == '品項':
            mode = 'items'
            continue
        if re.match(r'^備註[：:\s]', t) or t == '備註':
            mode = 'remarks'
            r = re.sub(r'^備註[：:\s]*', '', t).strip()
            if r:
                remarks_arr.append(r)
            continue
        if t.startswith('●'):
            mode = 'remarks'
            remarks_arr.append(t)
            continue
        if t.startswith('*') or t.startswith('＊'):
            table_note += ('\n' if table_note else '') + t
            continue

        is_item = (mode == 'items')

        if not is_item and mode == 'normal':
            # Our company info
            if re.search(r'(我方|我司)(公司|抬頭)[：:\s]', t):
                company.name = re.sub(r'.*(我方|我司)(公司|抬頭)[：:\s]*', '', t)
            elif re.search(r'(我方|我司)地址[：:\s]', t):
                company.address = re.sub(r'.*(我方|我司)地址[：:\s]*', '', t)
            elif re.search(r'(我方|我司)電話[：:\s]', t):
                company.phone = re.sub(r'.*(我方|我司)電話[：:\s]*', '', t)
            elif re.search(r'(我方|我司)聯絡人[：:\s]', t):
                company.contact = re.sub(r'.*(我方|我司)聯絡人[：:\s]*', '', t)
            # Customer info
            elif re.match(r'^((客戶)?品牌(名稱)?|客戶名稱|店名)[：:\s]', t):
                info.brand_name = re.sub(r'.*((客戶)?品牌(名稱)?|客戶名稱|店名)[：:\s]*', '', t)
            elif re.match(r'^(客戶)?代號[：:\s]', t):
                info.code = re.sub(r'.*(客戶)?代號[：:\s]*', '', t)
            elif re.match(r'^(客戶)?抬頭[：:\s]', t):
                info.title = re.sub(r'.*(客戶)?抬頭[：:\s]*', '', t)
            elif re.match(r'^(客戶)?聯絡人[：:\s]', t):
                info.contact_name = re.sub(r'.*(客戶)?聯絡人[：:\s]*', '', t)
            elif re.match(r'^(客戶)?(聯絡電話|電話|手機|TEL|Tel|Phone)[：:\s]', t, re.IGNORECASE):
                info.phone = re.sub(r'.*(客戶)?(聯絡電話|電話|手機|TEL|Tel|Phone)[：:\s]*', '', t, flags=re.IGNORECASE)
            elif re.match(r'^(客戶)?(店鋪)?地址[：:\s]', t):
                info.address = re.sub(r'.*(客戶)?(店鋪)?地址[：:\s]*', '', t)
            elif re.match(r'^(客戶)?發票地址[：:\s]', t):
                info.invoice_address = re.sub(r'.*(客戶)?發票地址[：:\s]*', '', t)
            elif re.match(r'^(客戶)?(統編|統一編號)[：:\s]', t):
                info.tax_id = re.sub(r'.*(客戶)?(統編|統一編號)[：:\s]*', '', t)
            elif re.match(r'^日期[：:\s]', t):
                d = re.sub(r'.*日期[：:\s]*', '', t).strip()
                fm = re.match(r'^(\d{1,4})\s*[/\-]\s*(\d{1,2})\s*[/\-]\s*(\d{1,2})$', d)
                sm = re.match(r'^(\d{1,2})\s*[/\-]\s*(\d{1,2})$', d)
                mm = re.match(r'^(\d{1,4})?\s*年?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?$', d)
                if fm:
                    y = int(fm.group(1))
                    if y > 1911:
                        y -= 1911
                    info.date = f'{y} 年 {int(fm.group(2))} 月 {int(fm.group(3))} 日'
                elif sm:
                    info.date = f'{roc_y} 年 {int(sm.group(1))} 月 {int(sm.group(2))} 日'
                elif mm:
                    y = int(mm.group(1)) if mm.group(1) else roc_y
                    if y > 1911:
                        y -= 1911
                    info.date = f'{y} 年 {int(mm.group(2))} 月 {int(mm.group(3))} 日'
                else:
                    info.date = d
            elif '：' not in t and ':' not in t:
                is_item = True

        if is_item:
            po = re.match(r'^單價\s*\$?([\d.]+)$', t)
            qo = re.match(r'^數量\s*([\d.]+)$', t)
            if po and items:
                items[-1].price = po.group(1)
            elif qo and items:
                items[-1].quantity = qo.group(1)
            else:
                pm = re.search(r'單價\s*\$?([\d.]+)', t)
                qm = re.search(r'數量\s*([\d.]+)', t)
                mp = re.match(r'^(.*?)\s+\$?([\d.]+)\s*\+\s*\$?([\d.]+)$', t)
                ms = re.match(r'^(.*?)\s+\$?([\d.]+)$', t)
                if pm and qm:
                    n = re.sub(r'單價\s*\$?[\d.]+', '', t)
                    n = re.sub(r'數量\s*[\d.]+', '', n).strip()
                    items.append(QuoteItem(name=n, price=pm.group(1), quantity=qm.group(1)))
                elif mp:
                    items.append(QuoteItem(name=mp.group(1).strip(), price=mp.group(2).strip(), quantity='1'))
                    items.append(QuoteItem(name=f'{mp.group(1).strip()}租金', price=mp.group(3).strip(), quantity='1'))
                elif ms:
                    items.append(QuoteItem(name=ms.group(1).strip(), price=ms.group(2).strip(), quantity='1'))
                else:
                    items.append(QuoteItem(name=t, price='', quantity='1'))
        elif mode == 'remarks':
            remarks_arr.append(t)

    remarks_text = '\n'.join(remarks_arr) if remarks_arr else DEFAULT_REMARKS

    return QuoteData(
        doc_title=doc_title,
        table_note=table_note,
        info=info,
        company=company,
        items=items,
        remarks=remarks_text,
    )
