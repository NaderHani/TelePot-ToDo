"""
handlers/list_tasks.py – عرض المهام مع inline buttons
"""

from __future__ import annotations

from datetime import datetime

import pytz
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import get_tasks, is_premium, count_tasks, FREE_TASK_LIMIT

CAIRO = pytz.timezone("Africa/Cairo")
router = Router(name="list_tasks")


def task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """أزرار done / delete لمهمة معينة"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تم", callback_data=f"done:{task_id}"),
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"del:{task_id}"),
            ]
        ]
    )


def format_task(t: dict, idx: int) -> str:
    """تنسيق مهمة واحدة للعرض"""
    status = "✅" if t["is_done"] else "📌"
    line = f"{status} <b>{idx}. {t['title']}</b>"
    if t["due"]:
        due_dt = datetime.fromisoformat(t["due"])
        now = datetime.now(CAIRO)
        due_str = due_dt.strftime("%Y-%m-%d %I:%M %p")
        if due_dt < now and not t["is_done"]:
            line += f"\n   🔴 <s>{due_str}</s> ⚠️ متأخرة!"
        else:
            line += f"\n   🕐 {due_str}"
    else:
        line += "\n   ⚡ بدون موعد"
    if t.get("recurrence"):
        rec_map = {"daily": "يومي 📅", "weekly": "أسبوعي 📆"}
        line += f"\n   🔄 {rec_map.get(t['recurrence'], t['recurrence'])}"
    return line


@router.message(F.text == "📋 مهامي")
@router.message(Command("tasks"))
async def show_tasks(message: types.Message) -> None:
    """عرض مهام المستخدم"""
    uid = message.from_user.id
    tasks = await get_tasks(uid, include_done=False)

    if not tasks:
        premium = await is_premium(uid)
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📭 <b>لا توجد مهام حاليًا</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 اضغط ➕ لإضافة أول مهمة!\n"
            "أو اكتب مباشرة:\n"
            '<i>"بكرة 9 الصبح ميتنج"</i>'
        )
        if not premium:
            text += "\n\n⭐ ترقَّ لـ Premium: مهام غير محدودة + تكرار!"
        await message.answer(text, parse_mode="HTML")
        return

    # إحصائيات
    total = len(tasks)
    overdue = sum(
        1 for t in tasks
        if t["due"] and datetime.fromisoformat(t["due"]) < datetime.now(CAIRO)
    )
    premium = await is_premium(uid)

    # Header
    header_parts = [
        "━━━━━━━━━━━━━━━━━━━━\n",
        f"📋 <b>مهامك ({total})</b>",
    ]
    if overdue:
        header_parts.append(f" • 🔴 {overdue} متأخرة")
    if not premium:
        limit_count = await count_tasks(uid)
        header_parts.append(f"\n📦 {limit_count}/{FREE_TASK_LIMIT} (مجاني)")
    header_parts.append("\n━━━━━━━━━━━━━━━━━━━━")

    await message.answer("".join(header_parts), parse_mode="HTML")

    for idx, t in enumerate(tasks, 1):
        text = format_task(t, idx)
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=task_keyboard(t["id"]),
        )
