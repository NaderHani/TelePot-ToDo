"""
╔══════════════════════════════════════════════════════════╗
║             TelePot – Telegram To-Do Bot                ║
║      مع تذكيرات + Freemium + Telegram Stars             ║
╚══════════════════════════════════════════════════════════╝

التشغيل محليًا:
    1. أنشئ ملف .env (انسخ .env.example) وأضف BOT_TOKEN
    2. pip install -r requirements.txt
    3. python main.py

النشر على Render.com:
    1. أنشئ Web Service جديد على Render
    2. Build Command:  pip install -r requirements.txt
    3. Start Command:  python main.py
    4. أضف Environment Variable:
        - BOT_TOKEN = <your_bot_token>
    5. Plan: Free (يكفي للـ polling)
    6. Render يدعم persistent disk لو تريد حفظ bot.db

ملاحظة: البوت يعمل بـ polling (مناسب محليًا وعلى Render).
لو تريد webhook، غيّر dp.start_polling → webhook setup.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from database import init_db
from scheduler import setup_scheduler

# ─── تحميل .env ───
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN غير موجود! أنشئ ملف .env وأضف التوكن.")
    sys.exit(1)

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


async def main() -> None:
    """نقطة الدخول الرئيسية"""

    # إنشاء البوت
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # إنشاء الـ Dispatcher
    dp = Dispatcher()

    # ── تسجيل الـ Handlers (الترتيب مهم) ──
    from handlers.premium import router as premium_router      # الدفع أولًا
    from handlers.start import router as start_router
    from handlers.add_task import router as add_task_router
    from handlers.list_tasks import router as list_tasks_router
    from handlers.callbacks import router as callbacks_router
    from handlers.reminder import router as reminder_router

    dp.include_routers(
        premium_router,     # pre_checkout + payment يجب أن يكون أولًا
        reminder_router,    # "ذكرني" يجب قبل add_task (عشان الـ regex)
        start_router,
        add_task_router,
        list_tasks_router,
        callbacks_router,
    )

    # ── إنشاء قاعدة البيانات ──
    await init_db()
    log.info("✅ Database initialized.")

    # ── تشغيل الـ Scheduler ──
    scheduler = setup_scheduler(bot)
    scheduler.start()
    log.info("✅ Scheduler started (reminders every 1 min, daily summary 7:00 Cairo).")

    # ── حذف webhook قديم + بدء polling ──
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("🚀 TelePot Bot started! Polling...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()
        log.info("🛑 Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
