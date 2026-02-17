"""
handlers/callbacks.py – معالجة callback queries (done / delete)
"""

from aiogram import Router, types, F

from database import mark_done, delete_task

router = Router(name="callbacks")


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: types.CallbackQuery) -> None:
    """تحديد مهمة كمنتهية"""
    task_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    success = await mark_done(task_id, uid)

    if success:
        await callback.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تم إنجاز المهمة!</b> 🎉\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<s>{callback.message.text}</s>\n\n"
            "👏 أحسنت! استمر كده!",
            parse_mode="HTML",
        )
        await callback.answer("✅ برافو عليك! 🎉")
    else:
        await callback.answer("❌ المهمة مش موجودة أو اتحذفت.", show_alert=True)


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: types.CallbackQuery) -> None:
    """حذف مهمة"""
    task_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    success = await delete_task(task_id, uid)

    if success:
        await callback.message.edit_text(
            "🗑 <i>تم حذف المهمة نهائيًا.</i>",
            parse_mode="HTML",
        )
        await callback.answer("🗑 تم الحذف.")
    else:
        await callback.answer("❌ المهمة مش موجودة أو اتحذفت.", show_alert=True)
