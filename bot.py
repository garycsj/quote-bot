"""
bot.py — Telegram 報價單 PDF 生成 Bot
傳送報價文字即自動生成 PDF 回傳
"""
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from parser import parse_raw
from pdf_generator import generate_pdf

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HELP_TEXT = """📄 *報價單 PDF 生成 Bot*
興霖事業有限公司

*使用方式：*
直接貼上報價資訊文字，Bot 會自動解析並生成 PDF 報價單。

*格式範例：*
```
新品報價單
抬頭：○○股份有限公司
品牌名稱：○○餐廳
聯絡人：王小明 先生
聯絡電話：02-1234-5678
地址：台北市大安區○○路123號
統一編號：12345678
日期：115/4/13

客用小方巾 (20*20cm)
單價80
數量100
```

*支援格式：*
• 第一行寫「新品報價單」→ 含數量/金額/稅金
• 第一行寫「租賃洗滌報價單」→ 品項/單價雙欄
• 品項可一行寫完（品名 單價）或分行寫
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or len(text.strip()) < 5:
        await update.message.reply_text('請貼上報價資訊文字，我會幫你生成 PDF 報價單。')
        return

    try:
        await update.message.reply_text('⏳ 正在生成報價單 PDF...')

        data = parse_raw(text)

        if not data.items:
            await update.message.reply_text(
                '⚠️ 沒有偵測到品項資訊。\n'
                '請確認品項格式，例如：\n'
                '```\n客用小方巾 (20*20cm)\n單價80\n數量100\n```',
                parse_mode='Markdown',
            )
            return

        pdf_bytes = generate_pdf(data)

        # Build filename
        customer = data.info.brand_name or data.info.title or '報價單'
        filename = f'{customer}_{data.doc_title}.pdf'

        await update.message.reply_document(
            document=pdf_bytes,
            filename=filename,
            caption=f'✅ {data.doc_title} — {customer}\n共 {len(data.items)} 項品項',
        )

        # Upload customer info to Google Drive
        try:
            from gdrive import upload_customer_info
            folder_name = upload_customer_info(data)
            await update.message.reply_text(
                f'📁 客戶資料已上傳至 Google Drive\n'
                f'資料夾：客戶資料/{folder_name}/'
            )
        except Exception as gdrive_err:
            logger.error(f'Google Drive upload error: {gdrive_err}', exc_info=True)
            await update.message.reply_text(f'⚠️ PDF 已生成，但客戶資料上傳 Google Drive 失敗：{gdrive_err}')

    except Exception as e:
        logger.error(f'Error generating PDF: {e}', exc_info=True)
        await update.message.reply_text(f'❌ 生成 PDF 時發生錯誤：{e}')


def main():
    token = os.environ.get('BOT_TOKEN')
    if not token:
        raise RuntimeError('請設定 BOT_TOKEN 環境變數')

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info('Bot started, polling...')
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
