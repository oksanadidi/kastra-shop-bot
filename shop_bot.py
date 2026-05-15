import os
import logging
import threading
import requests as http_requests
from flask import Flask, request, jsonify, Response
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SHOP_BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
BASE_URL = f"https://{RAILWAY_DOMAIN}" if RAILWAY_DOMAIN else ""

# Цены в Telegram Stars (1 Star ≈ $0.013-0.02)
# 500 Stars ≈ 490-550 руб по текущему курсу
PRODUCTS = {
    "guide_body_map": {
        "name": "Карта ощущений: где в теле живёт твоя тревога",
        "description": "Практический гайд 10 страниц. Упражнения, чек-листы, дыхательная практика. Найди где живёт твой страх — и тревога потеряет силу.",
        "stars": 500,
        "file_url": os.getenv("FILE_BODY_MAP")
    },
    "guide_solyar_12": {
        "name": "12 дней, которые решают год",
        "description": "Пошаговая инструкция как провести 12 дней после дня рождения. Каждый день закладывает один месяц твоей жизни. Знай что делать — и запусти именно тот год, который хочешь.",
        "stars": 500,
        "file_url": os.getenv("FILE_SOLYAR_12")
    },
    "guide_investments": {
        "name": "5 инвестиций в своё восстановление",
        "description": "Сон — важнейший фундамент восстановления. 5 шагов как нормализовать сон и получить больше энергии на дела, эмоции, любовь и перемены. PDF, 10 слайдов. Начать можно сегодня вечером.",
        "stars": 500,
        "file_url": "https://disk.yandex.ru/i/7CEkK0ILykYWow",
        "yadisk": True
    }
}


def resolve_file_url(product: dict) -> str:
    if not product.get("yadisk"):
        return product.get("file_url", "")
    public_key = product.get("file_url", "")
    try:
        resp = http_requests.get(
            "https://cloud-api.yandex.net/v1/disk/public/resources/download",
            params={"public_key": public_key},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("href", public_key)
    except Exception as e:
        logger.error(f"Ошибка получения ссылки Яндекс.Диска: {e}")
        return public_key


flask_app = Flask(__name__)

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
<p>Оплата производится через Telegram Stars — официальную платёжную систему Telegram. После успешной оплаты ссылка на скачивание приходит в бот автоматически.</p>

<h2>Возврат</h2>
<p>Цифровые продукты возврату не подлежат (ст. 26.1 ЗоЗПП, Постановление № 2463).<br>
Исключение: гайд не пришёл — напишите <a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a>, решим в течение 24 часов.</p>

<h2>Авторские права</h2>
<p>Все материалы © Оксана Кастра, 2026. Перепродажа и передача третьим лицам запрещены.</p>

<h2>Срок исполнения</h2>
<p>Ссылка на скачивание гайда направляется автоматически в течение 5 минут после оплаты. В случае технического сбоя — в течение 24 часов после обращения к продавцу.</p>

<h2>Акцепт оферты</h2>
<p>Нажатие кнопки оплаты в Telegram означает полное согласие с условиями настоящей оферты.</p>

<h2>Контакт</h2>
<p>Telegram: <a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a><br>
Email: <a href="mailto:oksadran@yandex.ru">oksadran@yandex.ru</a></p>

<p style="color:#999; font-size:0.9em; margin-top:2em;">Оферта действует с 15 мая 2026 г.</p>
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
<p>Telegram ID и username — только для доставки купленного гайда. Платёжные данные обрабатываются Telegram.</p>

<h2>Как используем</h2>
<p>Исключительно для доставки приобретённых материалов. Не передаём данные третьим лицам.</p>

<h2>Хранение</h2>
<p>Сервер Railway (ЕС). Срок хранения — не более 1 года с момента последней покупки.</p>

<h2>Ваши права</h2>
<p>Хотите удалить данные — напишите <a href="https://t.me/Oksana_Kastra">@Oksana_Kastra</a> или на <a href="mailto:oksadran@yandex.ru">oksadran@yandex.ru</a>, ответим в течение 30 дней.</p>

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


@flask_app.route("/health")
def health():
    return jsonify({"status": "ok", "bot_token": bool(BOT_TOKEN)})


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
        "Каждый гайд — инструмент для работы с собой. Купил один раз — работаешь всегда.\n\n"
        "💫 Оплата через Telegram Stars.",
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
    elif text == "🔐 Конфиденциальность":
        url = f"{BASE_URL}/privacy" if BASE_URL else None
        if url:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть политику", url=url)]])
            await update.message.reply_text("Политика конфиденциальности:", reply_markup=kb)
    elif text == "▶️ Главное меню":
        await start(update, context)
    else:
        await update.message.reply_text("Выбери раздел 👇", reply_markup=get_main_keyboard())


async def show_catalog_message(message):
    keyboard = []
    for product_id, product in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {product['stars']} ⭐",
            callback_data=f"product_{product_id}"
        )])
    await message.reply_text("Выбери гайд 👇", reply_markup=InlineKeyboardMarkup(keyboard))


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for product_id, product in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {product['stars']} ⭐",
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
        [InlineKeyboardButton(f"⭐ Купить за {product['stars']} Stars", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton("← Назад", callback_data="catalog")]
    ]
    await query.edit_message_text(
        f"📄 *{product['name']}*\n\n{product['description']}\n\n💫 Цена: *{product['stars']} Telegram Stars*",
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

    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=product["name"],
            description=product["description"],
            payload=product_id,
            currency="XTR",
            prices=[LabeledPrice(label=product["name"], amount=product["stars"])],
            provider_token=""
        )
    except Exception as e:
        logger.error(f"Ошибка создания инвойса Stars: {e}")
        if OWNER_CHAT_ID:
            try:
                await context.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=f"⚠️ Ошибка инвойса Stars:\n\n{e}"
                )
            except Exception:
                pass
        await query.edit_message_text(
            "Ошибка при создании платежа. Напиши @Oksana_Kastra — помогут в течение 24 часов."
        )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    product_id = payment.invoice_payload
    chat_id = update.message.chat_id

    product = PRODUCTS.get(product_id)
    if not product:
        await update.message.reply_text("Оплата получена! Гайд скоро пришлём — в течение 24 часов.")
        return

    file_url = resolve_file_url(product)
    if file_url:
        await update.message.reply_text(
            f"✅ Оплата прошла!\n\n"
            f"📄 *{product['name']}*\n\n"
            f"📥 Скачать гайд:\n{file_url}\n\n"
            f"Благодарю за доверие 🙏\n"
            f"Если будут вопросы — пиши @Oksana\\_Kastra",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("✅ Оплата прошла! Гайд пришлём в течение 24 часов.")

    if OWNER_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=f"⭐ Новая покупка!\nГайд: {product['name']}\nПокупатель: {chat_id}\nStars: {payment.total_amount}"
            )
        except Exception:
            pass


async def show_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = f"{BASE_URL}/offer" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть оферту", url=url)]])
        await query.edit_message_text("Публичная оферта:", reply_markup=kb)


async def show_privacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = f"{BASE_URL}/privacy" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть политику", url=url)]])
        await query.edit_message_text("Политика конфиденциальности:", reply_markup=kb)


async def offer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/offer" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть оферту", url=url)]])
        await update.message.reply_text("Публичная оферта:", reply_markup=kb)


async def privacy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = f"{BASE_URL}/privacy" if BASE_URL else None
    if url:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть политику", url=url)]])
        await update.message.reply_text("Политика конфиденциальности:", reply_markup=kb)


async def paysupport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "По вопросам оплаты пишите @Oksana_Kastra — ответим в течение 24 часов."
    )


async def post_init(application: Application):
    from telegram import BotCommand
    await application.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("offer", "Публичная оферта"),
        BotCommand("privacy", "Политика конфиденциальности"),
        BotCommand("paysupport", "Вопросы по оплате"),
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
    app.add_handler(CommandHandler("paysupport", paysupport_cmd))
    app.add_handler(CallbackQueryHandler(catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(show_offer_callback, pattern="^show_offer$"))
    app.add_handler(CallbackQueryHandler(show_privacy_callback, pattern="^show_privacy$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(buy, pattern="^buy_"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))

    logger.info("Магазин запущен (Telegram Stars)")
    app.run_polling()


if __name__ == "__main__":
    main()
