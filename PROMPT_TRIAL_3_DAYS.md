# Cursor Prompt: إضافة Trial 3 أيام مجاني لأول Premium

انسخ الـ prompt ده وألصقه في Cursor كرسالة جديدة:

---

## الـ Prompt:

```
أضف ميزة "Trial 3 أيام مجاني" لأول مستخدم جديد يجرب Premium:

### 1. database.py:
- أضف عمود `trial_used INTEGER DEFAULT 0` في جدول `users`
- أضف دالة `has_used_trial(user_id) -> bool` تتحقق هل المستخدم استخدم الـ trial قبل كده
- أضف دالة `activate_trial(user_id)` تعمل:
  - `is_premium = 1`
  - `sub_end = datetime.now(Cairo) + timedelta(days=3)`
  - `trial_used = 1`
- عدّل `init_db()` تضيف العمود لو مش موجود:
  ```python
  try:
      await db.execute("ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0")
  except:
      pass  # العمود موجود بالفعل
  ```

### 2. handlers/premium.py:
- في `show_premium()`:
  - لو المستخدم مش premium ومستخدمش الـ trial:
    - أرسل رسالة فيها زرين (InlineKeyboardMarkup):
      1. "🎁 جرّب 3 أيام مجانًا" → callback_data="start_trial"
      2. "💳 اشترك 299 ⭐" → callback_data="buy_premium"
  - لو المستخدم مش premium واستخدم الـ trial:
    - أرسل الفاتورة مباشرة (بدون زر الـ trial)
  - لو المستخدم premium:
    - نفس رسالة "أنت بالفعل مشترك"

- أضف callback handler لـ "start_trial":
  ```python
  @router.callback_query(F.data == "start_trial")
  async def activate_trial_cb(callback: types.CallbackQuery) -> None:
      uid = callback.from_user.id
      if await has_used_trial(uid):
          await callback.answer("⚠️ استخدمت الفترة التجريبية قبل كده!", show_alert=True)
          return
      await activate_trial(uid)
      await callback.message.edit_text(
          "━━━━━━━━━━━━━━━━━━━━\n"
          "🎉🎁 <b>مبروك! تم تفعيل الفترة التجريبية!</b>\n"
          "━━━━━━━━━━━━━━━━━━━━\n\n"
          "⏰ مدة التجربة: <b>3 أيام</b>\n\n"
          "🔓 اتفتحلك دلوقتي:\n"
          "  ♾ مهام غير محدودة\n"
          "  ♾ تذكيرات غير محدودة\n"
          "  🔄 تكرار يومي/أسبوعي\n"
          "  ☀️ ملخص صباحي 7:00\n\n"
          "💡 بعد 3 أيام هترجع مجاني.\n"
          "⭐ للاستمرار: /premium",
          parse_mode="HTML",
      )
      await callback.answer("🎉 تم التفعيل!")
  ```

- أضف callback handler لـ "buy_premium":
  ```python
  @router.callback_query(F.data == "buy_premium")
  async def buy_premium_cb(callback: types.CallbackQuery) -> None:
      await callback.message.answer_invoice(
          title="TelePot Premium ⭐ (30 يوم)",
          description="♾ مهام + تذكيرات غير محدودة\n🔄 تكرار + ☀️ ملخص صباحي",
          payload="premium_monthly_v1",
          currency="XTR",
          prices=[LabeledPrice(label="Premium 30 يوم", amount=299)],
      )
      await callback.answer()
  ```

### 3. handlers/start.py:
- في رسالة الترحيب `/start`، لو المستخدم جديد (مش premium ومستخدمش trial):
  أضف سطر: "🎁 جرّب Premium مجانًا 3 أيام! اضغط /premium"

### 4. scheduler.py:
- الـ expire_subscriptions الموجود بالفعل هيشيل الـ trial تلقائيًا لأنه بيشيك على sub_end (شغال بدون تعديل)

### ملاحظات:
- الرسائل بالعربي المصري
- استخدم parse_mode="HTML"
- الخطوط الفاصلة: "━━━━━━━━━━━━━━━━━━━━"
- إيموجي كتير
- trial_used مبيترجعش – لو استخدم الـ trial مرة مش هيقدر تاني
```

---

## طريقة الاستخدام:
1. افتح Cursor
2. افتح Composer (Ctrl+I)
3. الصق الـ prompt أعلاه
4. اضغط Enter
5. Cursor هينفذ كل التعديلات تلقائيًا!
