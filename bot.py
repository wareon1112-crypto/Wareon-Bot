import os
import sys
import logging
import asyncio
import aiosqlite
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("wareon-bot")

DB_PATH = os.getenv("USERS_DB", "users.db")

GUIDE_MESSAGE = (
    "ГАЙД НА ПОИСК КЛИЕНТОВ.\n"
    "ПРАЙМОВАЯ СТАТЬЯ О ТОМ, КАК ПЕРЕСТАТЬ ЖИТЬ ОТ ЗАКАЗА ДО ЗАКАЗА"
)
GUIDE_FILE_PATH = os.getenv("GUIDE_FILE", "Праймовый_гайд.html")

ADMIN_ID = None


# -------------------- БАЗА ДАННЫХ --------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()


async def add_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()


async def user_exists(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return await cur.fetchone() is not None


async def list_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
        return row[0] if row else 0


# -------------------- КОМАНДЫ --------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    uid = user.id

    if not await user_exists(uid):
        await add_user(uid)
        
        # Отправляем документ вместо текста
        try:
            with open(GUIDE_FILE_PATH, "rb") as file:
                await update.message.reply_document(
                    document=file,
                    filename="Праймовый гайд Wareon.html",
                    caption=GUIDE_MESSAGE,
                )
        except FileNotFoundError:
            # Если файл забыли положить в папку, бот отправит просто текст и предупреждение
            await update.message.reply_text(
                f"{GUIDE_MESSAGE}\n\n[Ошибка: Файл '{GUIDE_FILE_PATH}' не найден на сервере]"
            )
            logger.error(f"Файл {GUIDE_FILE_PATH} не найден!")
            
        logger.info("Добавлен новый пользователь %s", uid)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = await count_users()
    await update.message.reply_text(f"👥 Пользователей в базе: {total}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("ℹ️ Использование: /broadcast <текст>")
        return

    users = await list_users()
    sent = 0

    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error("Ошибка отправки %s: %s", uid, e)

    await update.message.reply_text(f"✅ Рассылка завершена. Отправлено {sent} из {len(users)}.")


async def admin_copy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    msg = update.effective_message

    if msg.text and msg.text.startswith("/"):
        return

    users = await list_users()
    sent = 0

    for uid in users:
        try:
            await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error("Ошибка копирования %s: %s", uid, e)

    await msg.reply_text(f"📤 Отправлено {sent} пользователям.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Ошибка: %s", context.error)


# -------------------- ЗАПУСК --------------------
async def _post_init(app: Application) -> None:
    await init_db()
    logger.info("✅ База данных инициализирована")


def main():
    global ADMIN_ID

    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_env = os.getenv("ADMIN_ID")

    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан")
        sys.exit(1)

    if not admin_env:
        logger.error("❌ ADMIN_ID не задан")
        sys.exit(1)

    try:
        ADMIN_ID = int(admin_env)
    except ValueError:
        logger.error("❌ ADMIN_ID должен быть числом")
        sys.exit(1)

    app = Application.builder().token(TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(
        MessageHandler(filters.User(user_id=ADMIN_ID) & ~filters.COMMAND, admin_copy_handler)
    )

    app.add_error_handler(error_handler)

    logger.info("🚀 Запуск бота...")
    print("🤖 Бот запущен и готов к работе!")

    app.run_polling()


if __name__ == "__main__":
    main()
