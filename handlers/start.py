"""
handlers/start.py – أمر /start + /help + الكيبورد الرئيسي
"""

from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import ensure_user, is_premium, count_tasks, count_reminders

router = Router(name="start")


def main_keyboard() -> ReplyKeyboardMarkup:
    """الكيبورد الرئيسي الدائم"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ إضافة مهمة"),
                KeyboardButton(text="📋 مهامي"),
            ],
            [
                KeyboardButton(text="⏰ تذكير متكرر"),
                KeyboardButton(text="🔔 تذكيراتي"),
            ],
            [
                KeyboardButton(text="⭐ ترقية Premium"),
                KeyboardButton(text="👤 اشتراكي"),
            ],
            [
                KeyboardButton(text="ℹ️ مساعدة"),
            ],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    """ترحيب بالمستخدم + تسجيله في DB"""
    uid = message.from_user.id
    await ensure_user(uid, message.from_user.username)

    name = message.from_user.first_name or "صديقي"
    premium = await is_premium(uid)
    badge = " ⭐" if premium else ""

    text = (
        f"👋 <b>أهلاً يا {name}!</b>{badge}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 أنا <b>TelePot</b> – مساعدك الذكي لتنظيم المهام\n"
        "والتذكيرات بالعربي والإنجليزي!\n\n"
        "🚀 <b>ابدأ دلوقتي:</b>\n\n"
        "📝 اكتب مهمتك مباشرة:\n"
        '   <i>"بكرة 3 العصر اجتماع الشغل"</i>\n'
        '   <i>"بعد ساعتين كلم الدكتور"</i>\n\n'
        "🔔 أو اكتب تذكير:\n"
        '   <i>"ذكرني بالاستغفار كل 5 دقايق"</i>\n\n'
        "👇 أو استخدم الأزرار بالأسفل"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_keyboard())


@router.message(Command("help"))
@router.message(lambda m: m.text == "ℹ️ مساعدة")
async def cmd_help(message: types.Message) -> None:
    """رسالة المساعدة الشاملة"""
    uid = message.from_user.id
    tasks_count = await count_tasks(uid)
    reminders_count = await count_reminders(uid)
    premium = await is_premium(uid)

    status = "⭐ Premium" if premium else "🆓 مجاني"

    text = (
        "📖 <b>دليل استخدام TelePot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "📊 <b>حالتك:</b> {status} • {tasks} مهمة • {reminders} تذكير\n\n"

        "━━ 1️⃣ <b>إضافة مهمة</b> ━━\n"
        "اضغط ➕ أو اكتب مباشرة:\n"
        '  📝 <i>"بكرة 8 الصبح اجتماع الفريق"</i>\n'
        '  📝 <i>"after 2 hours call doctor"</i>\n'
        '  📝 <i>"الخميس 3 العصر ميتنج"</i>\n'
        '  📝 <i>"بعد ساعتين دليفري"</i>\n\n'

        "━━ 2️⃣ <b>المهام</b> ━━\n"
        "📋 اضغط <b>مهامي</b> لعرض كل المهام\n"
        "✅ اضغط <b>تم</b> لإنهاء مهمة\n"
        "🗑 اضغط <b>حذف</b> لحذفها\n\n"

        "━━ 3️⃣ <b>تذكيرات متكررة</b> ━━\n"
        "اضغط ⏰ أو اكتب مباشرة:\n"
        '  🔔 <i>"ذكرني بالاستغفار كل 5 دقايق"</i>\n'
        '  🔔 <i>"فكرني اشرب ماء كل ساعة"</i>\n'
        '  🔔 <i>"نبهني كل نص ساعة أتحرك"</i>\n\n'

        "━━ 4️⃣ <b>Premium ⭐</b> ━━\n"
        "  ♾ مهام غير محدودة (بدل 15)\n"
        "  ♾ تذكيرات غير محدودة (بدل 3)\n"
        "  🔄 تكرار يومي / أسبوعي\n"
        "  ☀️ ملخص صباحي يومي 7:00\n"
        "  💰 299 ⭐ Stars / شهر\n\n"

        "━━ 💡 <b>كل الأوامر</b> ━━\n"
        "  /start ─ البداية\n"
        "  /help ─ المساعدة (أنت هنا 📍)\n"
        "  /tasks ─ مهامي\n"
        "  /reminders ─ تذكيراتي\n"
        "  /premium ─ ترقية\n"
        "  /my_subscription ─ حالة اشتراكي\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 اكتب أي حاجة وأنا هساعدك!"
    ).format(
        status=status,
        tasks=tasks_count,
        reminders=reminders_count,
    )
    await message.answer(text, parse_mode="HTML")
