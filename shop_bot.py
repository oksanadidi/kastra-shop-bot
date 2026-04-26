import os
import logging
import threading
import uuid
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from yookassa import Configuration, Payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SHOP_BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET = os.getenv("YOOKASSA_SECRET")

Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET

# Каталог гайдов — сюда добавляем новые продукты
PRODUCTS = {
    "guide_body_map": {
        "name": "Карта ощущений: где в теле живёт твоя тревога",
        "description": "Практический гайд 10 страниц.\nУпражнения, чек-листы, дыхательная практика.\nНайди где живёт твой страх — и тревога потеряет силу.",
        "price": 490,
        "file_url": os.getenv("FILE_BODY_MAP")  # Ссылка на Яндекс.Диск
    }
}

flask_app = Flask(__name__)
telegram_app = None


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
    return jsonify({"status": "ok"})


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📚 Каталог гайдов", callback_data="catalog")],
        [
            InlineKeyboardButton("📋 Оферта", callback_data="show_offer"),
            InlineKeyboardButton("🔐 Конфиденциальность", callback_data="show_privacy")
        ]
    ]
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Здесь ты найдёшь практические гайды и чек-листы по психологии, астрологии и здоровью.\n\n"
        "Каждый гайд — инструмент для работы с собой. Купил один раз — работаешь всегда.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = []
    for product_id, product in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(
            f"{product['name']} — {product['price']} ₽",
            callback_data=f"product_{product_id}"
        )])

    await query.edit_message_text(
        "Выбери гайд 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


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
        f"📄 *{product['name']}*\n\n"
        f"{product['description']}\n\n"
        f"💰 Цена: *{product['price']} ₽*",
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
        payment = Payment.create({
            "amount": {
                "value": f"{product['price']}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/kastra_shop_bot"
            },
            "description": product["name"],
            "metadata": {
                "chat_id": str(chat_id),
                "product_id": product_id
            },
            "capture": True
        }, str(uuid.uuid4()))

        pay_url = payment.confirmation.confirmation_url

        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", url=pay_url)],
            [InlineKeyboardButton("← Назад", callback_data=f"product_{product_id}")]
        ]

        await query.edit_message_text(
            f"💳 Оплата: *{product['name']}*\n\n"
            f"Сумма: *{product['price']} ₽*\n\n"
            f"После оплаты гайд придёт сюда автоматически. 📥\n\n"
            f"_Нажимая «Перейти к оплате», вы принимаете условия_ /offer",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        await query.edit_message_text(
            "Ошибка при создании платежа. Попробуй позже или напиши @Oksana_Kastra"
        )


OFFER_TEXT = """📋 *ПУБЛИЧНАЯ ОФЕРТА*

Продавец: Дранович Оксана Владимировна (самозанятый)

*Что продаём:* цифровые гайды в формате PDF — практические инструменты по психологии, астрологии и личностному развитию.

*Оплата:* онлайн-картой через ЮКасса. После оплаты ссылка на скачивание приходит сюда автоматически.

*Возврат:* цифровые продукты возврату не подлежат (ст. 26.1 ЗоЗПП, Постановление № 2463). Исключение: гайд не пришёл — пиши @Oksana\\_Kastra, решим в течение 24 часов.

*Авторские права:* все материалы © Оксана Кастра, 2026. Перепродажа и передача третьим лицам запрещены.

По вопросам: @Oksana\\_Kastra"""

PRIVACY_TEXT = """🔐 *ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ*

Оператор: Дранович Оксана Владимировна (самозанятый)

*Что собираем:* Telegram ID и username — только для доставки купленного гайда. Платёжные данные карты мы не видим — они у ЮКасса.

*Не передаём* данные третьим лицам и не используем в рекламных целях.

*Хранение:* сервер Railway, не более 1 года.

*Хочешь удалить данные* — напиши @Oksana\\_Kastra, ответим в течение 30 дней.

Закон: ФЗ-152 «О персональных данных»."""


async def offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(OFFER_TEXT, parse_mode="Markdown")


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")


async def show_offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(OFFER_TEXT, parse_mode="Markdown")


async def show_privacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")


def run_flask():
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def main():
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("offer", offer))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CallbackQueryHandler(catalog, pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(show_offer_callback, pattern="^show_offer$"))
    app.add_handler(CallbackQueryHandler(show_privacy_callback, pattern="^show_privacy$"))
    app.add_handler(CallbackQueryHandler(show_product, pattern="^product_"))
    app.add_handler(CallbackQueryHandler(buy, pattern="^buy_"))

    logger.info("Магазин запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
