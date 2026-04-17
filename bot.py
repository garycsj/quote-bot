"""
bot.py — Telegram 報價單 PDF 生成 Bot
傳送報價文字 → 生成 PDF → 上傳 Google Drive → 寫入 Notion
"""
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes,
)

from parser import parse_raw, QuoteData
from pdf_generator import generate_pdf

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation states
CONFIRM_DRIVE_FOLDER = 1
CONFIRM_SAME_CUSTOMER = 2
CONFIRM_OVERWRITE = 3

HELP_TEXT = """📄 *報價單 PDF 生成 Bot*
興霖事業有限公司

*使用方式：*
直接貼上報價資訊文字，Bot 會自動：
1\\. 生成 PDF 報價單
2\\. 上傳至 Google Drive
3\\. 將客戶資訊寫入 Notion

*格式範例：*
```
新品報價單
抬頭：○○股份有限公司
品牌名稱：○○餐廳
代號：A99
聯絡人：王小明 先生
聯絡電話：02-1234-5678
地址：台北市大安區○○路123號
統一編號：12345678
日期：115/4/13

客用小方巾 (20*20cm)
單價80
數量100
```
"""

YES_NO_KEYBOARD = ReplyKeyboardMarkup(
    [['✅ 是', '❌ 否']], one_time_keyboard=True, resize_keyboard=True,
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='MarkdownV2')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode='MarkdownV2')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or len(text.strip()) < 5:
        await update.message.reply_text('請貼上報價資訊文字，我會幫你生成 PDF 報價單。')
        return ConversationHandler.END

    try:
        # Step 1: Parse and generate PDF
        await update.message.reply_text('⏳ 正在生成報價單 PDF...')
        data = parse_raw(text)

        if not data.items:
            await update.message.reply_text(
                '⚠️ 沒有偵測到品項資訊。\n請確認品項格式。'
            )
            return ConversationHandler.END

        pdf_bytes = generate_pdf(data)
        customer = data.info.brand_name or data.info.title or '報價單'
        filename = f'{customer}_{data.doc_title}.pdf'

        await update.message.reply_document(
            document=pdf_bytes,
            filename=filename,
            caption=f'✅ {data.doc_title} — {customer}\n共 {len(data.items)} 項品項',
        )

        # Store in context for later steps
        context.user_data['quote_data'] = data
        context.user_data['pdf_bytes'] = pdf_bytes

        # Step 2: Google Drive — find matching folder
        try:
            from gdrive import find_matching_folder, _build_folder_name
            folder_result = find_matching_folder(data)
            context.user_data['drive_folder_result'] = folder_result

            if folder_result['match_type'] == 'exact':
                # Exact match — upload directly
                await _upload_to_drive(update, context, folder_result['folder_id'])
                await _proceed_to_notion(update, context)
                return context.user_data.get('_next_state', ConversationHandler.END)

            elif folder_result['match_type'] == 'similar':
                # Similar match — ask user
                target_name = _build_folder_name(data)
                await update.message.reply_text(
                    f'📁 Google Drive 找到相似資料夾：\n'
                    f'現有：「{folder_result["folder_name"]}」\n'
                    f'新名：「{target_name}」\n\n'
                    f'是否放入現有資料夾？',
                    reply_markup=YES_NO_KEYBOARD,
                )
                return CONFIRM_DRIVE_FOLDER

            else:
                # No match — create new folder
                await _create_drive_folder_and_upload(update, context)
                await _proceed_to_notion(update, context)
                return context.user_data.get('_next_state', ConversationHandler.END)

        except Exception as e:
            logger.error(f'Google Drive error: {e}', exc_info=True)
            await update.message.reply_text(f'⚠️ Google Drive 上傳失敗：{e}')
            context.user_data['drive_link'] = ''
            await _proceed_to_notion(update, context)
            return context.user_data.get('_next_state', ConversationHandler.END)

    except Exception as e:
        logger.error(f'Error: {e}', exc_info=True)
        await update.message.reply_text(f'❌ 發生錯誤：{e}')
        return ConversationHandler.END


async def confirm_drive_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle response to 'use existing similar folder?' question."""
    answer = update.message.text

    if '是' in answer:
        # Use existing folder
        folder_result = context.user_data.get('drive_folder_result', {})
        await _upload_to_drive(update, context, folder_result['folder_id'])
    else:
        # Create new folder
        await _create_drive_folder_and_upload(update, context)

    await _proceed_to_notion(update, context)
    return context.user_data.get('_next_state', ConversationHandler.END)


async def confirm_same_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle response to 'is this the same customer?' question."""
    answer = update.message.text
    data = context.user_data.get('quote_data')
    drive_link = context.user_data.get('drive_link', '')

    if '是' in answer:
        await update.message.reply_text(
            '確認為同一客戶。是否要覆蓋更新資料？',
            reply_markup=YES_NO_KEYBOARD,
        )
        return CONFIRM_OVERWRITE
    else:
        await _create_new_customer(update, data, drive_link)
        return ConversationHandler.END


async def confirm_overwrite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle response to 'overwrite existing data?' question."""
    answer = update.message.text
    data = context.user_data.get('quote_data')
    drive_link = context.user_data.get('drive_link', '')
    search_result = context.user_data.get('search_result', {})

    if '是' in answer:
        try:
            from notion_client import update_customer
            update_customer(search_result['page_id'], data, drive_link)
            await update.message.reply_text(
                f'✅ 已更新 Notion 客戶資料：{search_result["existing_name"]}',
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
            logger.error(f'Notion update error: {e}', exc_info=True)
            await update.message.reply_text(
                f'❌ Notion 更新失敗：{e}',
                reply_markup=ReplyKeyboardRemove(),
            )
    else:
        if drive_link and search_result.get('page_id'):
            try:
                from notion_client import update_drive_link
                update_drive_link(search_result['page_id'], drive_link)
                await update.message.reply_text(
                    '📎 已將 Google Drive 連結更新至 Notion（其他資料未變更）',
                    reply_markup=ReplyKeyboardRemove(),
                )
            except Exception as e:
                logger.error(f'Notion link update error: {e}', exc_info=True)
                await update.message.reply_text(
                    f'⚠️ 不覆蓋資料，但 Drive 連結更新失敗：{e}',
                    reply_markup=ReplyKeyboardRemove(),
                )
        else:
            await update.message.reply_text(
                '👌 不覆蓋，保留原有資料。',
                reply_markup=ReplyKeyboardRemove(),
            )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('已取消。', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── Helper functions ──

async def _upload_to_drive(update: Update, context: ContextTypes.DEFAULT_TYPE, folder_id: str):
    """Upload PDF to an existing Drive folder."""
    from gdrive import upload_pdf_to_folder, get_folder_link
    data = context.user_data['quote_data']
    pdf_bytes = context.user_data['pdf_bytes']

    upload_pdf_to_folder(folder_id, data, pdf_bytes)
    drive_link = get_folder_link(folder_id)
    context.user_data['drive_link'] = drive_link
    await update.message.reply_text(
        f'📁 報價單已上傳至 Google Drive',
        reply_markup=ReplyKeyboardRemove(),
    )


async def _create_drive_folder_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create new Drive folder and upload PDF."""
    from gdrive import create_folder_and_upload
    data = context.user_data['quote_data']
    pdf_bytes = context.user_data['pdf_bytes']

    folder_name, drive_link = create_folder_and_upload(data, pdf_bytes)
    context.user_data['drive_link'] = drive_link
    await update.message.reply_text(
        f'📁 已建立資料夾「{folder_name}」並上傳報價單',
        reply_markup=ReplyKeyboardRemove(),
    )


async def _proceed_to_notion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Notion and either create customer or ask for confirmation."""
    data = context.user_data['quote_data']
    drive_link = context.user_data.get('drive_link', '')

    try:
        from notion_client import search_customer
        search_result = search_customer(data)
        context.user_data['search_result'] = search_result

        match_type = search_result['match_type']

        if match_type == 'both':
            await update.message.reply_text(
                f'🔍 Notion 中已有相同客戶：\n'
                f'客戶名稱：{search_result["existing_name"]}\n'
                f'統一編號：{search_result["existing_tax_id"]}\n\n'
                f'是否要覆蓋更新資料？',
                reply_markup=YES_NO_KEYBOARD,
            )
            context.user_data['_next_state'] = CONFIRM_OVERWRITE

        elif match_type in ('name_only', 'tax_id_only'):
            if match_type == 'name_only':
                msg = (
                    f'🔍 Notion 中找到相同客戶名稱：\n'
                    f'客戶名稱：{search_result["existing_name"]}\n'
                    f'統一編號：{search_result["existing_tax_id"]}\n\n'
                    f'但統一編號不同。這是同一個客戶嗎？'
                )
            else:
                msg = (
                    f'🔍 Notion 中找到相同統一編號：\n'
                    f'客戶名稱：{search_result["existing_name"]}\n'
                    f'統一編號：{search_result["existing_tax_id"]}\n\n'
                    f'但客戶名稱不同。這是同一個客戶嗎？'
                )
            await update.message.reply_text(msg, reply_markup=YES_NO_KEYBOARD)
            context.user_data['_next_state'] = CONFIRM_SAME_CUSTOMER

        else:
            await _create_new_customer(update, data, drive_link)
            context.user_data['_next_state'] = ConversationHandler.END

    except Exception as e:
        logger.error(f'Notion error: {e}', exc_info=True)
        await update.message.reply_text(f'⚠️ Notion 操作失敗：{e}')
        context.user_data['_next_state'] = ConversationHandler.END


async def _create_new_customer(update: Update, data: QuoteData, drive_link: str):
    """Create a new customer in Notion."""
    try:
        from notion_client import create_customer, _build_customer_name
        page_id = create_customer(data, drive_link)
        name = _build_customer_name(data)
        await update.message.reply_text(
            f'✅ 已新增 Notion 客戶：{name}',
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.error(f'Notion create error: {e}', exc_info=True)
        await update.message.reply_text(
            f'❌ Notion 新增客戶失敗：{e}',
            reply_markup=ReplyKeyboardRemove(),
        )


def main():
    token = os.environ.get('BOT_TOKEN')
    if not token:
        raise RuntimeError('請設定 BOT_TOKEN 環境變數')

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        ],
        states={
            CONFIRM_DRIVE_FOLDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_drive_folder),
            ],
            CONFIRM_SAME_CUSTOMER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_same_customer),
            ],
            CONFIRM_OVERWRITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_overwrite),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
        ],
    )

    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(conv_handler)

    logger.info('Bot started, polling...')
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
