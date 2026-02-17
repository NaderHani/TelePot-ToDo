"""
handlers/add_task.py – إضافة مهمة بـ FSM + dateparser (عربي/إنجليزي)
يدعم الإدخال المباشر (رسالة واحدة) أو خطوات FSM.
+ normalize_arabic: تحويل التعبيرات العربية لصيغة يفهمها dateparser
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import dateparser
import pytz
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from database import (
    add_task,
    count_tasks,
    is_premium,
    ensure_user,
    FREE_TASK_LIMIT,
)

CAIRO = pytz.timezone("Africa/Cairo")
log = logging.getLogger(__name__)

router = Router(name="add_task")


# ─── FSM States ───
class AddTaskFSM(StatesGroup):
    waiting_title = State()
    waiting_due = State()
    waiting_recurrence = State()


# ─── dateparser settings ───
DATEPARSER_SETTINGS = {
    "TIMEZONE": "Africa/Cairo",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "PREFER_DATES_FROM": "future",
    "DATE_ORDER": "DMY",
}

# ─── تحويل الأرقام العربية للإنجليزية ───
ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ─── أرقام عربية مكتوبة (فصحى + مصري) ───
ARABIC_NUMBERS = {
    "واحده": "1", "واحدة": "1", "واحد": "1",
    "اتنين": "2", "تنين": "2", "اثنين": "2", "اثنتين": "2",
    "تلاته": "3", "تلاتة": "3", "ثلاثة": "3", "ثلاث": "3", "تلات": "3",
    "اربعه": "4", "اربعة": "4", "أربعة": "4", "أربع": "4", "اربع": "4",
    "خمسه": "5", "خمسة": "5", "خمس": "5",
    "سته": "6", "ستة": "6", "ست": "6",
    "سبعه": "7", "سبعة": "7", "سبع": "7",
    "تمانيه": "8", "تمانية": "8", "تمنيه": "8", "تمنية": "8",
    "ثمانية": "8", "ثماني": "8",
    "تسعه": "9", "تسعة": "9", "تسع": "9",
    "عشره": "10", "عشرة": "10", "عشر": "10",
    "احداشر": "11", "حداشر": "11", "إحدى عشر": "11",
    "اتناشر": "12", "اثنا عشر": "12", "اثنى عشر": "12", "تناشر": "12",
}

# ─── تعبيرات الوقت العربية → إنجليزية ───
AM_WORDS = [
    "الصبح", "صباحا", "صباحًا", "الصباح", "صباح", "صبح", "الصبحيه", "الصبحية",
    "الفجر", "فجرا", "فجرًا", "فجر",
    "ص",
]
PM_WORDS = [
    # الظهر
    "الضهر", "الظهر", "ضهر", "ظهر", "ظهرا", "ظهرًا",
    "الضهرية", "الظهرية", "ضهرية", "بعد الضهر", "بعد الظهر",
    # العصر
    "العصر", "عصر", "عصرا", "عصرًا", "العصريه", "العصرية",
    # المساء
    "المساء", "المسا", "مساء", "مساءا", "مساءً", "مسا",
    # المغرب
    "المغرب", "مغرب",
    # العشاء
    "العشاء", "العشا", "عشاء", "عشا",
    # الليل
    "بالليل", "الليل", "بليل", "بلليل", "ليلا", "ليلًا", "ليل",
    "م",
]
RELATIVE_AR = {
    # بعد + وقت
    "بعد ساعه": "in 1 hour", "بعد ساعة": "in 1 hour",
    "بعد ساعتين": "in 2 hours",
    "بعد نص ساعه": "in 30 minutes", "بعد نص ساعة": "in 30 minutes",
    "بعد نصف ساعة": "in 30 minutes", "بعد نص ساعه": "in 30 minutes",
    "بعد ربع ساعه": "in 15 minutes", "بعد ربع ساعة": "in 15 minutes",
    "بعد تلت ساعه": "in 20 minutes", "بعد تلت ساعة": "in 20 minutes",
    "بعد ثلث ساعة": "in 20 minutes",
    "بعد شويه": "in 15 minutes", "بعد شوية": "in 15 minutes",
    "بعد شوي": "in 15 minutes",
    # كمان + وقت (مصري)
    "كمان ساعه": "in 1 hour", "كمان ساعة": "in 1 hour",
    "كمان ساعتين": "in 2 hours",
    "كمان نص ساعه": "in 30 minutes", "كمان نص ساعة": "in 30 minutes",
    "كمان ربع ساعه": "in 15 minutes", "كمان ربع ساعة": "in 15 minutes",
    "كمان شويه": "in 15 minutes", "كمان شوية": "in 15 minutes",
}
DAY_AR = {
    # النهاردة / بكرة
    "النهارده": "today", "النهاردة": "today", "انهارده": "today",
    "انهاردة": "today", "اليوم": "today", "دلوقتي": "now", "دلوقت": "now",
    "بكره": "tomorrow", "بكرة": "tomorrow", "بكرا": "tomorrow",
    "بعد بكره": "in 2 days", "بعد بكرة": "in 2 days", "بعد بكرا": "in 2 days",
    "بعدبكره": "in 2 days", "بعدبكرة": "in 2 days",
    # أيام الأسبوع (مصري + فصحى)
    "الحد": "sunday", "الأحد": "sunday", "الاحد": "sunday", "يوم الحد": "sunday",
    "الاتنين": "monday", "الإتنين": "monday", "الاثنين": "monday",
    "يوم الاتنين": "monday",
    "التلات": "tuesday", "الثلاثاء": "tuesday", "الثلاث": "tuesday",
    "التلاتاء": "tuesday", "يوم التلات": "tuesday",
    "الاربع": "wednesday", "الأربعاء": "wednesday", "الاربعاء": "wednesday",
    "الأربع": "wednesday", "يوم الاربع": "wednesday",
    "الخميس": "thursday", "يوم الخميس": "thursday",
    "الجمعه": "friday", "الجمعة": "friday", "يوم الجمعه": "friday",
    "السبت": "saturday", "يوم السبت": "saturday",
}


def normalize_arabic(text: str) -> str:
    """تحويل التعبيرات العربية (مصري + فصحى) لصيغة يفهمها dateparser"""
    s = text.strip()

    # أرقام عربية ← إنجليزية (٧ → 7)
    s = s.translate(ARABIC_DIGIT_MAP)

    # تعبيرات نسبية (بعد ساعة، كمان ساعتين...)
    for ar, en in RELATIVE_AR.items():
        if ar in s:
            s = s.replace(ar, en)
            return s

    # أيام (بكرة، النهاردة، الخميس...)
    for ar, en in DAY_AR.items():
        if ar in s:
            s = s.replace(ar, en)

    # أرقام مكتوبة بالعربي (سبعه → 7)
    for ar, digit in ARABIC_NUMBERS.items():
        s = re.sub(rf"(?:^|\s){ar}(?:\s|$)", f" {digit} ", s)

    # "X و نص/نصف" → "X:30" (مصري: "تلاته و نص" → "3:30")
    s = re.sub(r"(\d+)\s*(?:و\s*نص(?:ف)?)", r"\1:30", s)
    # "X إلا ربع" → ساعة - 15 دقيقة (مثال: "4 إلا ربع" → "3:45")
    s = re.sub(r"(\d+)\s*(?:الا|إلا)\s*ربع", lambda m: f"{int(m.group(1))-1}:45", s)
    # "X و ربع" → "X:15"
    s = re.sub(r"(\d+)\s*و\s*ربع", r"\1:15", s)
    # "X و تلت" → "X:20"
    s = re.sub(r"(\d+)\s*و\s*(?:تلت|ثلث)", r"\1:20", s)

    # تعبيرات AM/PM: "7 الصبح" → "7 AM" ، "3 العصر" → "3 PM"
    for w in AM_WORDS:
        s = s.replace(w, "AM")
    for w in PM_WORDS:
        s = s.replace(w, "PM")

    # "بعد/كمان X ساعه/ساعات" → "in X hours"
    s = re.sub(r"(?:بعد|كمان)\s+(\d+)\s*(?:ساعه|ساعة|ساعات)", r"in \1 hours", s)

    # "بعد/كمان X دقيقه/دقايق" → "in X minutes"
    s = re.sub(r"(?:بعد|كمان)\s+(\d+)\s*(?:دقيقه|دقيقة|دقايق|دقائق|دقيق)", r"in \1 minutes", s)

    # "الساعه 7" / "الساعة 7" → "7:00"
    s = re.sub(r"الساع[ةه]\s*(\d+)", r"\1:00", s)

    # "صحيني" / "نبهني" / "فكرني" / "قومني" → شيلهم (هم العنوان مش الوقت)
    s = re.sub(r"^(?:صحيني|صحني|نبهني|فكرني|قومني|وريني)\s*", "", s)

    # تنظيف مسافات زيادة
    s = re.sub(r"\s+", " ", s).strip()

    return s


def smart_parse(text: str) -> datetime | None:
    """تحليل نص بعد التحويل العربي ← إنجليزي"""
    normalized = normalize_arabic(text)
    log.debug("Normalized: %r → %r", text, normalized)

    parsed = dateparser.parse(normalized, settings=DATEPARSER_SETTINGS)
    if parsed:
        return parsed.astimezone(CAIRO)

    # fallback: جرب النص الأصلي
    parsed = dateparser.parse(text, settings=DATEPARSER_SETTINGS)
    if parsed:
        return parsed.astimezone(CAIRO)

    return None


def parse_natural_date(text: str) -> tuple[str, datetime | None]:
    """
    محاولة استخراج التاريخ من النص الطبيعي.
    يرجع (العنوان_النظيف, التاريخ أو None).
    """
    # حاول تحليل النص كامل كتاريخ
    parsed = smart_parse(text)
    if parsed:
        return text.strip(), parsed

    # حاول تقسيم النص واستخراج التاريخ من أجزاء مختلفة
    words = text.split()
    best_date = None
    best_title = text.strip()

    # جرب من آخر كلمة (التاريخ غالبًا في الآخر: "اشتري هدية بكرة 3 الصبح")
    for i in range(len(words) - 1, max(len(words) - 6, 0) - 1, -1):
        date_part = " ".join(words[i:])
        title_part = " ".join(words[:i])
        parsed = smart_parse(date_part)
        if parsed and title_part:
            best_date = parsed
            best_title = title_part.strip()
            break

    # جرب من أول كلمة (التاريخ في الأول: "بكرة 3:30 اشتري هدية")
    if not best_date:
        for i in range(2, min(len(words) + 1, 6)):
            date_part = " ".join(words[:i])
            title_part = " ".join(words[i:])
            parsed = smart_parse(date_part)
            if parsed and title_part:
                best_date = parsed
                best_title = title_part.strip()
                break

    # جرب أول كلمة فقط
    if not best_date and len(words) > 1:
        parsed = smart_parse(words[0])
        if parsed:
            best_date = parsed
            best_title = " ".join(words[1:]).strip()

    return best_title, best_date


def is_past(dt: datetime) -> bool:
    """هل التاريخ في الماضي؟"""
    return dt < datetime.now(CAIRO)


def format_due(dt: datetime) -> str:
    """تنسيق التاريخ بشكل جميل"""
    now = datetime.now(CAIRO)
    diff = dt - now

    date_str = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%I:%M %p")

    # لو اليوم
    if dt.date() == now.date():
        return f"النهاردة {time_str}"
    # لو بكرة
    if (dt.date() - now.date()).days == 1:
        return f"بكرة {time_str}"
    # لو أقل من أسبوع
    if diff.days < 7:
        days_ar = ["الاتنين", "التلات", "الاربع", "الخميس", "الجمعة", "السبت", "الحد"]
        day_name = days_ar[dt.weekday()]
        return f"{day_name} {time_str}"

    return f"{date_str} {time_str}"


# ══════════════════════════════════════════════════
#  زر / أمر بدء الإضافة
# ══════════════════════════════════════════════════

@router.message(F.text == "➕ إضافة مهمة")
async def start_add_task(message: types.Message, state: FSMContext) -> None:
    """بدء عملية إضافة مهمة عبر FSM"""
    await ensure_user(message.from_user.id, message.from_user.username)
    uid = message.from_user.id

    # تحقق من الحد للمجاني
    if not await is_premium(uid):
        current = await count_tasks(uid)
        if current >= FREE_TASK_LIMIT:
            remaining = FREE_TASK_LIMIT - current
            await message.answer(
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>وصلت للحد الأقصى!</b>\n\n"
                f"📦 خطتك: مجاني ({FREE_TASK_LIMIT} مهمة)\n"
                f"📝 مهامك: {current}/{FREE_TASK_LIMIT}\n\n"
                "⭐ <b>ترقَّ لـ Premium:</b>\n"
                "  ♾ مهام غير محدودة\n"
                "  🔄 تكرار يومي/أسبوعي\n"
                "  ☀️ ملخص صباحي\n\n"
                "👉 اضغط /premium للترقية\n"
                "━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
            )
            return

    await state.set_state(AddTaskFSM.waiting_title)
    await message.answer(
        "📝 <b>مهمة جديدة</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ اكتب المهمة مع الوقت في رسالة واحدة:\n\n"
        '  💡 <i>"بكرة 3 العصر اشتري هدية"</i>\n'
        '  💡 <i>"بعد ساعتين كلم الدكتور"</i>\n'
        '  💡 <i>"الخميس 9 الصبح ميتنج"</i>\n\n'
        "أو اكتب العنوان فقط وهسألك عن الوقت 🕐",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ إلغاء")]],
            resize_keyboard=True,
        ),
    )


# ══════════════════════════════════════════════════
#  استقبال العنوان (أو عنوان + تاريخ)
# ══════════════════════════════════════════════════

@router.message(AddTaskFSM.waiting_title, F.text == "❌ إلغاء")
async def cancel_add(message: types.Message, state: FSMContext) -> None:
    from handlers.start import main_keyboard
    await state.clear()
    await message.answer("🚫 تم إلغاء الإضافة.", reply_markup=main_keyboard())


@router.message(AddTaskFSM.waiting_title)
async def receive_title(message: types.Message, state: FSMContext) -> None:
    """استقبال عنوان المهمة (مع أو بدون تاريخ)"""
    from handlers.start import main_keyboard

    raw = message.text.strip()
    title, due = parse_natural_date(raw)

    if due:
        # تحقق من أن التاريخ مش في الماضي
        if is_past(due):
            await message.answer(
                "⏳ <b>الوقت ده فات!</b>\n\n"
                f"🕐 {due.strftime('%Y-%m-%d %I:%M %p')}\n\n"
                "💡 جرّب وقت في المستقبل:\n"
                '  <i>"بكرة 9 الصبح"</i>\n'
                '  <i>"بعد ساعة"</i>',
                parse_mode="HTML",
            )
            return

        uid = message.from_user.id
        premium = await is_premium(uid)
        due_display = format_due(due)

        if premium:
            await state.update_data(title=title, due=due.isoformat())
            await state.set_state(AddTaskFSM.waiting_recurrence)
            await message.answer(
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>{title}</b>\n"
                f"🕐 {due_display}\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔄 <b>تكرار المهمة؟</b>",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="يومي 📅"), KeyboardButton(text="أسبوعي 📆")],
                        [KeyboardButton(text="بدون تكرار ✅")],
                    ],
                    resize_keyboard=True,
                ),
            )
        else:
            task_id = await add_task(uid, title, due)
            await state.clear()
            await message.answer(
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✅ <b>تمت الإضافة بنجاح!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 {title}\n"
                f"🕐 {due_display}\n"
                f"🔢 #{task_id}\n\n"
                "⏰ هذكّرك في الموعد!",
                parse_mode="HTML",
                reply_markup=main_keyboard(),
            )
    else:
        await state.update_data(title=title)
        await state.set_state(AddTaskFSM.waiting_due)
        await message.answer(
            f'📝 المهمة: <b>"{title}"</b>\n\n'
            "🕐 <b>امتى تحب أذكّرك؟</b>\n\n"
            "اكتب الوقت بأي شكل:\n"
            '  💡 <i>"بكرة 9 الصبح"</i>\n'
            '  💡 <i>"بعد ساعتين"</i>\n'
            '  💡 <i>"الخميس 3 العصر"</i>\n\n'
            'أو اكتب <b>"بدون"</b> لحفظها بدون موعد.',
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════
#  استقبال الموعد
# ══════════════════════════════════════════════════

@router.message(AddTaskFSM.waiting_due, F.text == "❌ إلغاء")
async def cancel_due(message: types.Message, state: FSMContext) -> None:
    from handlers.start import main_keyboard
    await state.clear()
    await message.answer("🚫 تم الإلغاء.", reply_markup=main_keyboard())


@router.message(AddTaskFSM.waiting_due)
async def receive_due(message: types.Message, state: FSMContext) -> None:
    """استقبال الموعد"""
    from handlers.start import main_keyboard

    data = await state.get_data()
    title = data["title"]
    uid = message.from_user.id
    raw = message.text.strip()

    if raw in ("بدون", "لا", "لأ", "مفيش", "مش عايز", "no", "none", "skip", "لا شكرا"):
        task_id = await add_task(uid, title, due=None)
        await state.clear()
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت الإضافة!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 {title}\n"
            f"🔢 #{task_id}\n\n"
            "⚡ بدون موعد تذكير.",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )
        return

    due = smart_parse(raw)
    if not due:
        _, extracted = parse_natural_date(raw)
        due = extracted

    if not due:
        await message.answer(
            "🤔 <b>مش فاهم الموعد ده!</b>\n\n"
            "💡 جرّب كده:\n"
            '  🕐 <i>"بكرة 3 العصر"</i>\n'
            '  🕐 <i>"7 الصبح"</i>\n'
            '  🕐 <i>"بعد ساعتين"</i>\n'
            '  🕐 <i>"9 بليل"</i>\n'
            '  🕐 <i>"after 1 hour"</i>',
            parse_mode="HTML",
        )
        return

    # تحقق من أن الوقت مش في الماضي
    if is_past(due):
        await message.answer(
            "⏳ <b>الوقت ده فات!</b>\n\n"
            f"🕐 {due.strftime('%Y-%m-%d %I:%M %p')}\n\n"
            "💡 اكتب وقت في المستقبل:\n"
            '  <i>"بكرة 9 الصبح"</i>\n'
            '  <i>"بعد ساعة"</i>',
            parse_mode="HTML",
        )
        return

    due_display = format_due(due)
    premium = await is_premium(uid)

    if premium:
        await state.update_data(due=due.isoformat())
        await state.set_state(AddTaskFSM.waiting_recurrence)
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>{title}</b>\n"
            f"🕐 {due_display}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔄 <b>تكرار المهمة؟</b>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="يومي 📅"), KeyboardButton(text="أسبوعي 📆")],
                    [KeyboardButton(text="بدون تكرار ✅")],
                ],
                resize_keyboard=True,
            ),
        )
    else:
        task_id = await add_task(uid, title, due)
        await state.clear()
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت الإضافة بنجاح!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 {title}\n"
            f"🕐 {due_display}\n"
            f"🔢 #{task_id}\n\n"
            "⏰ هذكّرك في الموعد!",
            parse_mode="HTML",
            reply_markup=main_keyboard(),
        )


# ══════════════════════════════════════════════════
#  استقبال التكرار (Premium فقط)
# ══════════════════════════════════════════════════

@router.message(AddTaskFSM.waiting_recurrence)
async def receive_recurrence(message: types.Message, state: FSMContext) -> None:
    """استقبال نوع التكرار"""
    from handlers.start import main_keyboard

    data = await state.get_data()
    title = data["title"]
    due = datetime.fromisoformat(data["due"])
    uid = message.from_user.id

    recurrence = None
    raw = message.text.strip()
    if "يومي" in raw or "daily" in raw.lower():
        recurrence = "daily"
    elif "أسبوعي" in raw or "weekly" in raw.lower():
        recurrence = "weekly"

    task_id = await add_task(uid, title, due, recurrence)
    await state.clear()

    due_display = format_due(due)
    rec_text = ""
    if recurrence == "daily":
        rec_text = "\n🔄 تكرار: يومي 📅"
    elif recurrence == "weekly":
        rec_text = "\n🔄 تكرار: أسبوعي 📆"

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>تمت الإضافة بنجاح!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 {title}\n"
        f"🕐 {due_display}"
        f"{rec_text}\n"
        f"🔢 #{task_id}\n\n"
        "⏰ هذكّرك في الموعد!",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )
