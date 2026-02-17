"""
handlers/reminder.py – تذكيرات متكررة (كل X دقيقة/ساعة)
- زر "⏰ تذكير متكرر" أو كتابة "ذكرني بـ... كل ..."
- FSM: نص التذكير → الفترة
- عرض + إيقاف + حذف التذكيرات
"""

from __future__ import annotations

import logging
import re

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    add_reminder,
    get_user_reminders,
    count_reminders,
    pause_reminder,
    delete_reminder,
    is_premium,
    ensure_user,
    FREE_REMINDER_LIMIT,
)

log = logging.getLogger(__name__)
router = Router(name="reminder")


# ─── FSM States ───
class ReminderFSM(StatesGroup):
    waiting_text = State()
    waiting_interval = State()


# ─── تحويل الأرقام العربية ───
ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_reminder_message(text: str) -> tuple[str, int] | None:
    """
    تحليل رسالة ذكرني مباشرة:
    "ذكرني بالاستغفار كل 5 دقايق" → ("الاستغفار", 5)
    "ذكرني اشرب ماء كل ساعة" → ("اشرب ماء", 60)
    "ذكرني كل ساعتين اشرب ماء" → ("اشرب ماء", 120)
    "remind me to drink water every 30 minutes" → ("drink water", 30)
    """
    s = text.translate(ARABIC_DIGIT_MAP).strip()

    # ─── Arabic patterns (فصحى + مصري) ───
    verb = r"(?:ذكر|فكر|نبه)(?:ني|نى)"

    # "ذكرني بـ<text> كل <N> <unit>"
    m = re.search(
        rf"{verb}\s+(?:ب|بال|بأ|بإ|بان|بالـ|إن(?:ي|ى)\s+)?(.+?)\s+كل\s+(.+)",
        s,
    )
    if m:
        reminder_text = m.group(1).strip()
        interval = _parse_arabic_interval(m.group(2).strip())
        if interval and reminder_text:
            return reminder_text, interval

    # "ذكرني كل <N> <unit> <text>"
    m = re.search(
        rf"{verb}\s+كل\s+(.+?)\s+([\u0600-\u06FF\w].+)",
        s,
    )
    if m:
        interval = _parse_arabic_interval(m.group(1).strip())
        reminder_text = m.group(2).strip()
        if interval and reminder_text:
            return reminder_text, interval

    # "ذكرني <text> كل <N> <unit>" (بدون باء)
    m = re.search(
        rf"{verb}\s+(.+?)\s+كل\s+(.+)",
        s,
    )
    if m:
        reminder_text = m.group(1).strip()
        interval = _parse_arabic_interval(m.group(2).strip())
        if interval and reminder_text:
            return reminder_text, interval

    # ─── English patterns ───

    # "remind me to <text> every <N> <unit>"
    m = re.search(
        r"remind\s+me\s+(?:to\s+)?(.+?)\s+every\s+(.+)",
        s, re.IGNORECASE,
    )
    if m:
        reminder_text = m.group(1).strip()
        interval = _parse_english_interval(m.group(2).strip())
        if interval and reminder_text:
            return reminder_text, interval

    return None


def _parse_arabic_interval(s: str) -> int | None:
    """تحليل فترة عربية (مصري + فصحى) → دقائق"""
    s = s.translate(ARABIC_DIGIT_MAP).strip()

    # "5 دقايق" / "10 دقائق" / "دقيقة" / "5 دقيقه"
    m = re.match(r"(\d+)\s*(?:دقيق[ةه]|دقايق|دقائق|دقيق|دق)", s)
    if m:
        return int(m.group(1))

    # "دقيقة" / "دقيقتين"
    if re.match(r"دقيق(?:ه|ة|تين)", s):
        return 2 if "تين" in s else 1

    # "X ساعه/ساعة/ساعات"
    m = re.match(r"(\d+)\s*(?:ساع[ةه]|ساعات)", s)
    if m:
        return int(m.group(1)) * 60

    # "ساعة" / "ساعتين"
    if re.match(r"^ساع[ةه]$", s):
        return 60
    if s == "ساعتين":
        return 120

    # "نص ساعه" / "نصف ساعة"
    if re.match(r"نص(?:ف)?\s*ساع[ةه]", s):
        return 30

    # "ربع ساعة"
    if re.match(r"ربع\s*ساع[ةه]", s):
        return 15

    # "تلت ساعة" (ثلث ساعة = 20 دقيقة)
    if re.match(r"(?:تلت|ثلث)\s*ساع[ةه]", s):
        return 20

    # "ساعة و نص" / "ساعه ونص"
    if re.match(r"ساع[ةه]\s*و?\s*نص(?:ف)?", s):
        return 90

    # "ساعة وربع"
    if re.match(r"ساع[ةه]\s*و?\s*ربع", s):
        return 75

    return None


def _parse_english_interval(s: str) -> int | None:
    """تحليل فترة إنجليزية → دقائق"""
    s = s.strip().lower()

    m = re.match(r"(\d+)\s*min(?:ute)?s?", s)
    if m:
        return int(m.group(1))

    m = re.match(r"(\d+)\s*hours?", s)
    if m:
        return int(m.group(1)) * 60

    if s in ("hour", "an hour", "1 hour"):
        return 60
    if s in ("half hour", "half an hour", "30 min"):
        return 30

    return None


def format_interval(mins: int) -> str:
    """تنسيق الفترة بالعربي بشكل جميل"""
    if mins < 60:
        return f"{mins} دقيقة"
    hours = mins // 60
    remaining = mins % 60
    if remaining == 0:
        if hours == 1:
            return "ساعة"
        if hours == 2:
            return "ساعتين"
        return f"{hours} ساعات"
    if hours == 1:
        return f"ساعة و {remaining} دقيقة"
    return f"{hours} ساعات و {remaining} دقيقة"


def parse_interval_input(text: str) -> int | None:
    """تحليل إدخال الفترة من المستخدم (في FSM)"""
    s = text.translate(ARABIC_DIGIT_MAP).strip()

    s = re.sub(r"^كل\s*", "", s).strip()
    if "كل" in s:
        s = s.split("كل", 1)[1].strip()
    s = re.sub(r"^every\s*", "", s, flags=re.IGNORECASE).strip()

    result = _parse_arabic_interval(s)
    if result:
        return result

    result = _parse_english_interval(s)
    if result:
        return result

    m = re.match(r"^(\d+)$", s)
    if m:
        val = int(m.group(1))
        if val > 0:
            return val

    return None


# ══════════════════════════════════════════════════
#  Auto-detect: "ذكرني ..." في أي وقت (بدون FSM)
# ══════════════════════════════════════════════════

@router.message(F.text.regexp(r"^(?:ذكر(?:ني|نى)|فكر(?:ني|نى)|نبه(?:ني|نى)|remind\s+me)", flags=re.IGNORECASE))
async def auto_remind(message: types.Message, state: FSMContext) -> None:
    """التقاط رسائل ذكرني التلقائية"""
    from handlers.start import main_keyboard
    await ensure_user(message.from_user.id, message.from_user.username)
    uid = message.from_user.id

    premium = await is_premium(uid)
    if not premium:
        current = await count_reminders(uid)
        if current >= FREE_REMINDER_LIMIT:
            await message.answer(
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>وصلت للحد الأقصى!</b>\n\n"
                f"🔔 تذكيراتك: {current}/{FREE_REMINDER_LIMIT}\n\n"
                "⭐ ترقَّ لـ Premium لتذكيرات غير محدودة!\n"
                "👉 /premium\n"
                "━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
            )
            return

    parsed = parse_reminder_message(message.text)
    if parsed:
        reminder_text, interval = parsed
        rid = await add_reminder(uid, reminder_text, interval)
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تم إنشاء التذكير!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔔 {reminder_text}\n"
            f"🔄 كل {format_interval(interval)}\n"
            f"🔢 #{rid}\n\n"
            "⏰ هذكّرك بانتظام!\n"
            "📋 لإدارة التذكيرات: /reminders",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
    else:
        await state.set_state(ReminderFSM.waiting_text)
        await state.update_data(raw=message.text)
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔔 <b>تذكير جديد!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "✍️ اكتب نص التذكير:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ إلغاء")]],
                resize_keyboard=True,
            ),
        )


# ══════════════════════════════════════════════════
#  زر "⏰ تذكير متكرر" → FSM
# ══════════════════════════════════════════════════

@router.message(F.text == "⏰ تذكير متكرر")
async def start_reminder_fsm(message: types.Message, state: FSMContext) -> None:
    """بدء إنشاء تذكير عبر FSM"""
    await ensure_user(message.from_user.id, message.from_user.username)
    uid = message.from_user.id

    premium = await is_premium(uid)
    if not premium:
        current = await count_reminders(uid)
        if current >= FREE_REMINDER_LIMIT:
            await message.answer(
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <b>وصلت للحد الأقصى!</b>\n\n"
                f"🔔 تذكيراتك: {current}/{FREE_REMINDER_LIMIT}\n\n"
                "⭐ ترقَّ لـ Premium لتذكيرات غير محدودة!\n"
                "👉 /premium\n"
                "━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
            )
            return

    await state.set_state(ReminderFSM.waiting_text)
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔔 <b>تذكير متكرر جديد</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ اكتب النص اللي عايز أذكّرك بيه:\n\n"
        '  💡 <i>"الاستغفار"</i>\n'
        '  💡 <i>"اشرب ماء"</i>\n'
        '  💡 <i>"خذ بريك"</i>',
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ إلغاء")]],
            resize_keyboard=True,
        ),
    )


# ─── FSM: نص التذكير ───

@router.message(ReminderFSM.waiting_text, F.text == "❌ إلغاء")
async def cancel_reminder(message: types.Message, state: FSMContext) -> None:
    from handlers.start import main_keyboard
    await state.clear()
    await message.answer("🚫 تم إلغاء التذكير.", reply_markup=main_keyboard())


@router.message(ReminderFSM.waiting_text)
async def receive_reminder_text(message: types.Message, state: FSMContext) -> None:
    """استقبال نص التذكير"""
    text = message.text.strip()
    await state.update_data(reminder_text=text)
    await state.set_state(ReminderFSM.waiting_interval)
    await message.answer(
        f'🔔 التذكير: <b>"{text}"</b>\n\n'
        "⏱ <b>كل كام؟</b>\n\n"
        "اكتب الفترة:\n"
        '  💡 <i>"5 دقايق"</i>\n'
        '  💡 <i>"نص ساعة"</i>\n'
        '  💡 <i>"ساعة"</i>\n'
        '  💡 <i>"ساعتين"</i>\n\n'
        "أو رقم فقط بالدقايق: <i>15</i>",
        parse_mode="HTML",
    )


# ─── FSM: الفترة ───

@router.message(ReminderFSM.waiting_interval, F.text == "❌ إلغاء")
async def cancel_interval(message: types.Message, state: FSMContext) -> None:
    from handlers.start import main_keyboard
    await state.clear()
    await message.answer("🚫 تم إلغاء التذكير.", reply_markup=main_keyboard())


@router.message(ReminderFSM.waiting_interval)
async def receive_interval(message: types.Message, state: FSMContext) -> None:
    """استقبال الفترة وحفظ التذكير"""
    from handlers.start import main_keyboard

    interval = parse_interval_input(message.text)
    if not interval:
        await message.answer(
            "🤔 <b>مش فاهم الفترة دي!</b>\n\n"
            "💡 جرّب كده:\n"
            '  ⏱ <i>"5 دقايق"</i>\n'
            '  ⏱ <i>"ساعة"</i>\n'
            '  ⏱ <i>"نص ساعة"</i>\n'
            '  ⏱ <i>"30"</i> (دقيقة)',
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    reminder_text = data["reminder_text"]
    uid = message.from_user.id

    rid = await add_reminder(uid, reminder_text, interval)
    await state.clear()

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>تم إنشاء التذكير!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔔 {reminder_text}\n"
        f"🔄 كل {format_interval(interval)}\n"
        f"🔢 #{rid}\n\n"
        "⏰ هذكّرك بانتظام!\n"
        "📋 لإدارة التذكيرات: /reminders",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


# ══════════════════════════════════════════════════
#  عرض التذكيرات /reminders
# ══════════════════════════════════════════════════

@router.message(Command("reminders"))
@router.message(F.text == "🔔 تذكيراتي")
async def show_reminders(message: types.Message) -> None:
    """عرض التذكيرات النشطة"""
    uid = message.from_user.id
    reminders = await get_user_reminders(uid)

    if not reminders:
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📭 <b>لا توجد تذكيرات نشطة</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 اضغط ⏰ لإنشاء تذكير!\n"
            "أو اكتب مباشرة:\n"
            '<i>"ذكرني بالاستغفار كل 5 دقايق"</i>',
            parse_mode="HTML",
        )
        return

    premium = await is_premium(uid)
    count = len(reminders)
    limit_text = ""
    if not premium:
        limit_text = f" • 📦 {count}/{FREE_REMINDER_LIMIT}"

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔔 <b>تذكيراتك ({count})</b>{limit_text}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

    for r in reminders:
        status = "🟢 نشط" if r.get("is_active", 1) else "⏸ متوقف"
        text = (
            f"🔔 <b>{r['text']}</b>\n"
            f"🔄 كل {format_interval(r['interval_mins'])}\n"
            f"📊 {status}"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⏸ إيقاف", callback_data=f"rpause:{r['id']}"
                    ),
                    InlineKeyboardButton(
                        text="🗑 حذف", callback_data=f"rdel:{r['id']}"
                    ),
                ]
            ]
        )
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ══════════════════════════════════════════════════
#  Callback: إيقاف / حذف تذكير
# ══════════════════════════════════════════════════

@router.callback_query(F.data.startswith("rpause:"))
async def cb_pause_reminder(callback: types.CallbackQuery) -> None:
    """إيقاف تذكير"""
    rid = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    success = await pause_reminder(rid, uid)
    if success:
        await callback.message.edit_text(
            "⏸ <i>تم إيقاف التذكير.</i>\n\n"
            "💡 لإنشاء تذكير جديد: ⏰ تذكير متكرر",
            parse_mode="HTML",
        )
        await callback.answer("⏸ تم الإيقاف.")
    else:
        await callback.answer("❌ التذكير مش موجود أو اتحذف.", show_alert=True)


@router.callback_query(F.data.startswith("rdel:"))
async def cb_delete_reminder(callback: types.CallbackQuery) -> None:
    """حذف تذكير"""
    rid = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    success = await delete_reminder(rid, uid)
    if success:
        await callback.message.edit_text(
            "🗑 <i>تم حذف التذكير نهائيًا.</i>",
            parse_mode="HTML",
        )
        await callback.answer("🗑 تم الحذف.")
    else:
        await callback.answer("❌ التذكير مش موجود أو اتحذف.", show_alert=True)
