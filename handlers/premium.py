"""
handlers/premium.py – اشتراك Premium عبر Telegram Stars (XTR)
- /premium أو زر "⭐ ترقية Premium"
- pre_checkout_query + successful_payment handlers
- /my_subscription لعرض حالة الاشتراك
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice

from database import update_premium, is_premium, get_subscription_info

CAIRO = pytz.timezone("Africa/Cairo")

router = Router(name="premium")
log = logging.getLogger(__name__)

# ─── ثوابت الدفع ───
PREMIUM_PRICE = 299          # 299 Stars ≈ ~$3
SUBSCRIPTION_DAYS = 30
SUBSCRIPTION_PERIOD = 2592000  # 30 يوم بالثواني
PAYLOAD = "premium_monthly_v1"


# ══════════════════════════════════════════════════
#  عرض صفحة Premium / إرسال الفاتورة
# ══════════════════════════════════════════════════

@router.message(F.text == "⭐ ترقية Premium")
@router.message(Command("premium"))
async def show_premium(message: types.Message) -> None:
    """عرض مزايا Premium وإرسال فاتورة Stars"""
    uid = message.from_user.id
    already = await is_premium(uid)

    if already:
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌟 <b>أنت بالفعل مشترك Premium!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 مميزاتك الحالية:\n"
            "  ♾ مهام غير محدودة\n"
            "  ♾ تذكيرات غير محدودة\n"
            "  🔄 تكرار يومي/أسبوعي\n"
            "  ☀️ ملخص صباحي يومي\n\n"
            "📊 لمعرفة حالة اشتراكك: /my_subscription\n\n"
            "💙 شكرًا لدعمك!",
            parse_mode="HTML",
        )
        return

    # رسالة المزايا أولاً
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⭐ <b>TelePot Premium</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "🆓 <b>المجاني:</b>\n"
        "  📝 15 مهمة\n"
        "  🔔 3 تذكيرات\n"
        "  ❌ بدون تكرار\n"
        "  ❌ بدون ملخص صباحي\n\n"

        "⭐ <b>Premium:</b>\n"
        "  ♾ مهام <b>غير محدودة</b>\n"
        "  ♾ تذكيرات <b>غير محدودة</b>\n"
        "  🔄 تكرار يومي / أسبوعي\n"
        "  ☀️ ملخص صباحي يومي 7:00\n"
        "  🚀 أولوية في الدعم\n\n"

        "💰 <b>299 ⭐ Stars / شهر</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 اضغط على زر الدفع بالأسفل:",
        parse_mode="HTML",
    )

    # فاتورة Stars
    desc = (
        "TelePot Premium – 30 يوم\n"
        "♾ مهام + تذكيرات غير محدودة\n"
        "🔄 تكرار + ☀️ ملخص صباحي"
    )

    await message.answer_invoice(
        title="TelePot Premium ⭐ (30 يوم)",
        description=desc,
        payload=PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 يوم", amount=PREMIUM_PRICE)],
    )


# ══════════════════════════════════════════════════
#  Pre-checkout: الموافقة على الدفع
# ══════════════════════════════════════════════════

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery) -> None:
    """الموافقة على pre-checkout query"""
    await query.answer(ok=True)


# ══════════════════════════════════════════════════
#  Successful Payment: تفعيل Premium
# ══════════════════════════════════════════════════

@router.message(F.successful_payment)
async def successful_payment(message: types.Message) -> None:
    """تفعيل Premium بعد الدفع الناجح"""
    uid = message.from_user.id
    payment = message.successful_payment

    await update_premium(uid, days=SUBSCRIPTION_DAYS)

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎉🎉🎉\n"
        "<b>مبروك! تم تفعيل Premium!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "🔓 <b>اتفتحلك دلوقتي:</b>\n"
        "  ♾ مهام غير محدودة\n"
        "  ♾ تذكيرات غير محدودة\n"
        "  🔄 تكرار يومي/أسبوعي\n"
        "  ☀️ ملخص صباحي كل يوم 7:00\n\n"

        f"💳 الدفع: {payment.total_amount} ⭐ Stars\n"
        f"🔖 رقم العملية: <code>{payment.telegram_payment_charge_id}</code>\n\n"

        "💙 شكرًا لدعمك! استمتع بتجربة أفضل! 🚀",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════════
#  حالة الاشتراك /my_subscription
# ══════════════════════════════════════════════════

@router.message(Command("my_subscription"))
@router.message(F.text == "👤 اشتراكي")
async def my_subscription(message: types.Message) -> None:
    """عرض حالة اشتراك المستخدم"""
    uid = message.from_user.id
    info = await get_subscription_info(uid)

    if not info or not info["is_premium"]:
        await message.answer(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>حالة اشتراكك</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📦 الخطة: <b>🆓 مجاني</b>\n\n"
            "📊 <b>الحدود:</b>\n"
            "  📝 15 مهمة كحد أقصى\n"
            "  🔔 3 تذكيرات كحد أقصى\n"
            "  ❌ التكرار غير متاح\n"
            "  ❌ الملخص الصباحي غير متاح\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⭐ ترقَّ لـ Premium عبر /premium\n"
            "♾ مهام + تذكيرات غير محدودة!",
            parse_mode="HTML",
        )
        return

    sub_end = datetime.fromisoformat(info["sub_end"])
    now = datetime.now(CAIRO)
    remaining = (sub_end - now).days
    end_str = sub_end.strftime("%Y-%m-%d %I:%M %p")

    if remaining < 0:
        status_icon = "🔴"
        status_text = "منتهي"
        remaining_text = "⚠️ انتهى اشتراكك! جدّده عبر /premium"
    elif remaining == 0:
        status_icon = "🟡"
        status_text = "آخر يوم!"
        remaining_text = "⚠️ بينتهي النهاردة! جدّده عبر /premium"
    elif remaining <= 3:
        status_icon = "🟡"
        status_text = f"{remaining} يوم متبقي"
        remaining_text = f"⚠️ ينتهي قريب! باقي {remaining} يوم"
    else:
        status_icon = "🟢"
        status_text = "نشط"
        remaining_text = f"✅ باقي {remaining} يوم"

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>حالة اشتراكك</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 الخطة: <b>⭐ Premium</b>\n"
        f"{status_icon} الحالة: <b>{status_text}</b>\n"
        f"📅 ينتهي: {end_str}\n"
        f"⏳ {remaining_text}\n\n"
        "🎯 <b>مميزاتك:</b>\n"
        "  ♾ مهام غير محدودة\n"
        "  ♾ تذكيرات غير محدودة\n"
        "  🔄 تكرار يومي / أسبوعي\n"
        "  ☀️ ملخص صباحي 7:00\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💙 شكرًا لدعمك!",
        parse_mode="HTML",
    )
