"""
scheduler.py – APScheduler jobs
1) check_reminders         → كل دقيقة: تذكيرات المهام المستحقة
2) check_interval_reminders → كل دقيقة: التذكيرات المتكررة (كل X دقيقة)
3) daily_summary           → كل يوم 7:00 صباحًا Cairo: ملخص اليوم للـ Premium
4) expire_subs             → كل ساعة: إلغاء الاشتراكات المنتهية
"""

from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import pytz

from database import (
    get_due_tasks,
    mark_reminded,
    handle_recurring_task,
    get_premium_users,
    get_today_tasks,
    check_expired_subscriptions,
    get_due_reminders,
    advance_reminder,
)

CAIRO = pytz.timezone("Africa/Cairo")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
#  Job 1: تذكيرات كل دقيقة
# ══════════════════════════════════════════════════

async def check_reminders(bot: Bot) -> None:
    """تفحص المهام المستحقة وترسل تذكيرات"""
    tasks = await get_due_tasks()
    for t in tasks:
        try:
            due_dt = datetime.fromisoformat(t["due"])
            due_str = due_dt.strftime("%Y-%m-%d %I:%M %p")
            text = (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⏰ <b>حان الموعد!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 <b>{t['title']}</b>\n"
                f"🕐 {due_str}\n\n"
                "💪 يلّا! لا تنسى تنجزها!"
            )
            await bot.send_message(t["user_id"], text, parse_mode="HTML")
            await mark_reminded(t["id"])

            if t.get("recurrence"):
                await handle_recurring_task(t)

        except Exception as e:
            log.error("Reminder error for task %s: %s", t["id"], e)


# ══════════════════════════════════════════════════
#  Job 2: تذكيرات متكررة كل X دقيقة
# ══════════════════════════════════════════════════

async def check_interval_reminders(bot: Bot) -> None:
    """تفحص التذكيرات المتكررة المستحقة وترسلها"""
    reminders = await get_due_reminders()
    for r in reminders:
        try:
            mins = r["interval_mins"]
            if mins < 60:
                interval_str = f"{mins} دقيقة"
            elif mins == 60:
                interval_str = "ساعة"
            elif mins == 120:
                interval_str = "ساعتين"
            else:
                h = mins // 60
                m = mins % 60
                interval_str = f"{h} ساعات"
                if m:
                    interval_str += f" و {m} دقيقة"

            text = (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔔 <b>تذكير!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📿 <b>{r['text']}</b>\n\n"
                f"<i>🔄 كل {interval_str}</i>"
            )
            await bot.send_message(r["user_id"], text, parse_mode="HTML")
            await advance_reminder(r["id"])
        except Exception as e:
            log.error("Interval reminder error for #%s: %s", r["id"], e)


# ══════════════════════════════════════════════════
#  Job 3: ملخص الصباح اليومي (Premium فقط)
# ══════════════════════════════════════════════════

async def daily_summary(bot: Bot) -> None:
    """يُرسل ملخص يومي كل صباح للمستخدمين Premium"""
    premium_users = await get_premium_users()
    for u in premium_users:
        uid = u["user_id"]
        try:
            tasks = await get_today_tasks(uid)
            if not tasks:
                text = (
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "☀️ <b>صباح الخير!</b> 🌅\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ لا توجد مهام لليوم!\n"
                    "🎉 يوم فاضي – استمتع بوقتك!\n\n"
                    "📝 عايز تضيف حاجة؟ اضغط ➕"
                )
            else:
                now = datetime.now(CAIRO)
                overdue = []
                today_list = []
                for t in tasks:
                    due_dt = datetime.fromisoformat(t["due"])
                    due_str = due_dt.strftime("%I:%M %p")
                    if due_dt < now:
                        overdue.append(f"  🔴 <b>{t['title']}</b> ─ <s>{due_str}</s>")
                    else:
                        today_list.append(f"  🔵 <b>{t['title']}</b> ─ {due_str}")

                lines = [
                    "━━━━━━━━━━━━━━━━━━━━\n",
                    f"☀️ <b>صباح الخير! ملخص يومك</b> 🌅\n",
                    f"📊 {len(tasks)} مهمة",
                    "━━━━━━━━━━━━━━━━━━━━\n",
                ]
                if overdue:
                    lines.append(f"\n⚠️ <b>متأخرة ({len(overdue)}):</b>")
                    lines.extend(overdue)
                if today_list:
                    lines.append(f"\n📋 <b>مهام اليوم ({len(today_list)}):</b>")
                    lines.extend(today_list)

                lines.append("\n\n💪 يوم موفق!")
                text = "\n".join(lines)

            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            log.error("Daily summary error for user %s: %s", uid, e)


# ══════════════════════════════════════════════════
#  Job 4: إلغاء الاشتراكات المنتهية
# ══════════════════════════════════════════════════

async def expire_subscriptions(bot: Bot) -> None:
    """تحقق من الاشتراكات المنتهية وأبلغ المستخدمين"""
    expired = await check_expired_subscriptions()
    for uid in expired:
        try:
            text = (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>انتهى اشتراكك Premium!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📦 رجعت للخطة المجانية:\n"
                "  📝 15 مهمة كحد أقصى\n"
                "  🔔 3 تذكيرات كحد أقصى\n\n"
                "⭐ جدّد اشتراكك: /premium\n\n"
                "💙 شكرًا لاستخدامك TelePot!"
            )
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            log.error("Expire notify error for user %s: %s", uid, e)


# ══════════════════════════════════════════════════
#  تسجيل الـ Jobs في الـ Scheduler
# ══════════════════════════════════════════════════

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """إنشاء وتسجيل الـ scheduler"""
    scheduler = AsyncIOScheduler(timezone=CAIRO)

    scheduler.add_job(
        check_reminders,
        "interval",
        minutes=1,
        args=[bot],
        id="check_reminders",
        replace_existing=True,
    )

    scheduler.add_job(
        check_interval_reminders,
        "interval",
        minutes=1,
        args=[bot],
        id="check_interval_reminders",
        replace_existing=True,
    )

    scheduler.add_job(
        daily_summary,
        "cron",
        hour=7,
        minute=0,
        args=[bot],
        id="daily_summary",
        replace_existing=True,
    )

    scheduler.add_job(
        expire_subscriptions,
        "interval",
        hours=1,
        args=[bot],
        id="expire_subscriptions",
        replace_existing=True,
    )

    return scheduler
