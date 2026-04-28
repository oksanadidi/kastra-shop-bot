import os
import logging
import threading
import uuid
from flask import Flask, request, jsonify, Response
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from yookassa import Configuration, Payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SHOP_BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET = os.getenv("YOOKASSA_SECRET")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET

RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
BASE_URL = f"https://{RAILWAY_DOMAIN}" if RAILWAY_DOMAIN else ""

PRODUCTS = {
    "guide_body_map": {
        "name": "Карта ощущений: где в теле живёт твоя тревога",
        "description": "Практический гайд 10 страниц.\nУпражнения, чек-листы, дыхательная практика.\nНайди где живёт твой страх — и тревога потеряет силу.",
        "price": 490,
        "file_url": os.getenv("FILE_BODY_MAP")
    }
}

flask_app = Flask(__name__)
telegram_app = None

OFFER_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Публичная оферта — Оксана Кастра</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.7; }
  h1 { color: #4a4a8a; }
  h2 { color: #4a4a8a; font-size: 1.1em; margin-top: 1.5em; }
</style>
</head>
<body>
<h1>📋 Публичная оферта</h1>
<p><strong>Продавец:</strong> Дранович Оксана Владимировна (самозанятый), ИНН: 143500361802</p>

<h2>Предмет</h2>
<p>Цифровые гайды в формате PDF — практические инструменты по психологии, астрологии и личностному развитию.</p>

<h2>Оплата</h2>
<p>Онлайн-картой через сервис ЮКасса. После успешной оплаты ссылка на скачивание приходит в Telegram-бот автоматически.</p>

<h2>Возврат</h2>
<p>Цифровые продукты возврату не подлежат (ст. 26.1 ЗоЗПП, Постановление № 2463).<br>
Исключение: гайд не пришёл — напишите <a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a>, решим в течение 24 часов.</p>

<h2>Авторские права</h2>
<p>Все материалы © Оксана Кастра, 2026. Перепродажа и передача третьим лицам запрещены.</p>

<h2>Акцепт оферты</h2>
<p>Нажатие кнопки «Перейти к оплате» означает полное согласие с условиями настоящей оферты.</p>

<h2>Контакт</h2>
<p><a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a></p>
</body>
</html>"""

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Политика конфиденциальности — Оксана Кастра</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.7; }
  h1 { color: #4a4a8a; }
  h2 { color: #4a4a8a; font-size: 1.1em; margin-top: 1.5em; }
</style>
</head>
<body>
<h1>🔐 Политика конфиденциальности</h1>
<p><strong>Оператор:</strong> Дранович Оксана Владимировна (самозанятый), ИНН: 143500361802</p>

<h2>Что собираем</h2>
<p>Telegram ID и username — только для доставки купленного гайда.<br>
Платёжные данные карты мы не видим — они обрабатываются ЮКасса.</p>

<h2>Как используем</h2>
<p>Исключительно для доставки приобретённых материалов. Не передаём данные третьим лицам, не используем в рекламных целях.</p>

<h2>Хранение</h2>
<p>Сервер Railway (ЕС). Срок хранения — не более 1 года с момента последней покупки.</p>

<h2>Ваши права</h2>
<p>Хотите удалить данные — напишите <a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a>, ответим в течение 30 дней.</p>

<h2>Правовая основа</h2>
<p>ФЗ-152 «О персональных данных».</p>
</body>
</html>"""


@flask_app.route("/offer")
def offer_page():
    return Response(OFFER_HTML, mimetype="text/html; charset=utf-8")


@flask_app.route("/privacy")
def privacy_page():
    return Response(PRIVACY_HTML, mimetype="text/html; charset=utf-8")


@flask_app.route("/yookassa_webhook", methods=["POST"])
def yookassa_webhook():
    data = request.json
    if not data:
        return jsonify({"status": "ok"})

    if data.get("event") == "payment.succeeded":
        obj = data.get("object", {})
        metadata = obj.get("metadata", {})
        chat_id = metadata.get("chat_id")
        product_id = metadata.get("product_id")

        if chat_id and product_id:
            product = PRODUCTS.get(product_id)
            if product:
                import asyncio
                asyncio.run(send_product(int(chat_id), product))

    return jsonify({"status": "ok"})


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "yookassa_shop_id": bool(YOOKASSA_SHOP_ID),
        "yookassa_secret": bool(YOOKASSA_SECRET),
        "bot_token": bool(BOT_TOKEN),
        "base_url": BASE_URL
    })


async def send_product(chat_id: int, product: dict):
    from telegram import Bot
    bot = Bot(token=BOT_TOKEN)
    file_url = product.get("file_url")
    if file_url:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Оплата прошла!\n\n"
                f"📄 *{product['name']}*\n\n"
                f"📥 Скачать гайд:\n{file_url}\n\n"
                f"Благодарю за доверие 🙏\n"
                f"Если будут вопросы — пиши @Oksana_Kastra"
            ),
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="✅ Оплата прошла! Гайд скоро пришлём — в течение 24 часов."
        )


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["📚 Каталог гайдов"], ["📋 Оферта", "🔐 Конфиденциальность"], ["▶️ Главное меню"]],
        resize_keyboard=True
    )


def get_start_inline(offer_url: str, privacy_url: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Каталог гайдов", callback_data="catalog")],
        [
            InlineKeyboardButton("📋 Оферта", url=offer_url),
            InlineKeyboardButton("🔐 Конфиденциальность", url=privacy_url)
        ]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offer_url = f"{BASE_URL}/offer" if BASE_URL else None
    privacy_url = f"{BASE_URL}/privacy" if BASE_URL else None

    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Здесь ты найдёшь практические гайды и чек-листы по психологии, астрологии и здоровью.\n\n"
        "Каждый гайд — инструмент для работы с собой. Купил один раз — работаешь всегда.",
        reply_markup=get_main_keyboard()
    )

    if offer_url and privacy_url:
        await update.message.reply_text(
            "Выбери раздел:",
            reply_markup=get_start_inline(offer_url, privacy_url)
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Каталог гайдов", callback_data="catalog")],
            [
                InlineKeyboardButton("📋 Оферта", callback_data="show_offer"),
                InlineKeyboardButton("🔐 Конфиденциальность", callback_data="show_privacy")
            ]
        ])
        await update.message.reply_text("Выбери раздел:", reply_markup=keyboard)


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📚 Каталог гайдов":
        await show_catalog_message(update.message)
    elif text == "📋 Оферта":
        url = f"{BASE_URL}/offer" if BASE_URL else None
        if url:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть оферту", url=url)]])
            await update.message.reply_text("Публичная оферта:", reply_markup=kb)
        else:
            await update.message.reply_text(OFFER_TEXT, parse_mode="Markdown")
    elif text == "🔐 Конфиденциальность":
        url = f"{BASE_URL}/privacy" if BASE_URL else None
        if url:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть политику", url=url)]])
            await update.message.reply_text("Политика конфиденциальности:", reply_markup=kb)
        else:
            await update.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")
    elif text == "▶️ Главное меню":
        await start(update, context)
    else:
        # Любое другое сообщение — показать меню
        await update.message.reply_text(
            "Выбери раздел 👇",
            reply_markup=get_main_keyboard()
        )


async def show_catalog_message(message):
    keyboard = []
    for product_id, product in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {product['price']} ₽",
            callback_data=f"product_{product_id}"
        )])
    await message.reply_text("Выбери гайд 👇", reply_markup=InlineKeyboardMarkup(keyboard))


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for product_id, product in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {product['price']} ₽",
            callback_data=f"product_{product_id}"
        )])
    await query.edit_message_text("Выбери гайд 👇", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("product_", "")
    product = PRODUCTS.get(product_id)
    if not product:
        await query.edit_message_text("Гайд не найден.")
        return
    keyboard = [
        [InlineKeyboardButton("💳 Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton("← Назад", callback_data="catalog")]
    ]
    await query.edit_message_text(
        f"📄 *{product['name']}*\n\n{product['description']}\n\n💰 Цена: *{product['price']} ₽*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("buy_", "")
    product = PRODUCTS.get(product_id)
    if not product:
        await query.edit_message_text("Гайд не найден.")
        return

    chat_id = query.message.chat_id
    offer_url = f"{BASE_URL}/offer" if BASE_URL else None

    try:
        payment = Payment.create({
            "amount": {"value": f"{product['price']}.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "https://t.me/kastra_shop_bot"},
            "description": product["name"],
            "metadata": {"chat_id": str(chat_id), "product_id": product_id},
            "capture": True
        }, str(uuid.uuid4()))

        pay_url = payment.confirmation.confirmation_url
        offer_line = f"\n_Нажимая «Перейти к оплате», вы принимаете [условия оферты]({offer_url})_" if offer_url else ""

        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", url=pay_url)],
            [InlineKeyboardButton("← Назад", callback_data=f"product_{product_id}")]
        ]
        await query.edit_message_text(
            f"💳 Оплата: *{product['name']}*\n\nСумма: *{product['price']} ₽*\n\n"
            f"После оплаты гайд придёт сюда автоматически. 📥{offer_line}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        # Уведомить владельца с реальной ошибкой
        if OWNER_CHAT_ID:
            try:
                from telegram import Bot
                bot = Bot(token=BOT_TOKEN)
                await bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=f"⚠️ Ошибка платежа в магазине:\n\n{e}"
                )
            except Exception:
                pass
        await query.edit_message_text(
            "Ошибка при создании платежа. Напиши @Oksana_Kastra — помогут в течение 24 часов."
        )


OFFER_TEXT = """📋 *ПУБЛИЧНАЯ ОФЕРТА*

Продавец: Дранович Оксана Владимировна (самозанятый)

*Что продаём:* цифровые гайды в формате PDF.

*Оплата:* онлайн-картой через ЮКасса. После оплаты ссылка на скачивание приходит автоматически.

*Возврат:* цифровые продукты возврату не подлежат (ст. 26.1 ЗоЗПП). Исключение: гайд не пришёл — пиши @Oksana\\_Kastra.

*Авторские права:* © Оксана Кастра, 2026. Перепродажа запрещена.

По вопросам: @Oksana\\_Kastra"""

PRIVACY_TEXT = """🔐 *ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ*

Оператор: Дранович Оксана Владимировна (самозанятый)

*Что собираем:* Telegram ID и username — только для доставки гайда. Платёжные данные карты мы не видим.

*Не передаём* данные третьим лицам и не используем в рекламных целях.

*Хранение:* сервер Railway, не более 1 года.

*Удалить данные* — напиши @Oksana\\_Kastra.

Закон: ФЗ-152 «О персональных данных»."""


async def offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/offer" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть оферту", url=url)]])
        await update.message.reply_text("Публичная оферта:", reply_markup=kb)
    else:
        await update.message.reply_text(OFFER_TEXT, parse_mode="Markdown")


async def privacy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/privacy" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть политику", url=url)]])
        await update.message.reply_text("Политика конфиденциальности:", reply_markup=kb)
    else:
        await update.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")


async def show_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(OFFER_TEXT, parse_mode="Markdown")


async def show_privacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("offer", "Публичная оферта"),
        BotCommand("privacy", "Политика конфиденциальности"),
    ])


def run_flask():
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def main():
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("offer", offer_cmd))
    app.add_handler(CommandHandler("privacy", privacy_cmd))
    app.add_handler(CallbackQueryHandler(catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(show_offer_callback, pattern="^show_offer$"))
    app.add_handler(CallbackQueryHandler(show_privacy_callback, pattern="^show_privacy$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(buy, pattern="^buy_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))

    logger.info("Магазин запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
