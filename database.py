"""
database.py – SQLite async layer (aiosqlite)
جداول: users + tasks + reminders (تذكيرات متكررة كل X دقيقة)
"""

import aiosqlite
import os
from datetime import datetime, timedelta

import pytz

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")
CAIRO = pytz.timezone("Africa/Cairo")

# ─── الحد الأقصى للمهام للمستخدم المجاني ───
FREE_TASK_LIMIT = 15
FREE_REMINDER_LIMIT = 3


async def init_db() -> None:
    """إنشاء الجداول إذا لم تكن موجودة"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                is_premium INTEGER DEFAULT 0,
                sub_end    TEXT,          -- ISO-format datetime (Cairo)
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT    NOT NULL,
                due         TEXT,         -- ISO-format datetime (Cairo)
                recurrence  TEXT,         -- 'daily' | 'weekly' | NULL
                is_done     INTEGER DEFAULT 0,
                reminded    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                text            TEXT    NOT NULL,
                interval_mins   INTEGER NOT NULL,  -- كل كم دقيقة
                next_fire       TEXT    NOT NULL,   -- ISO-format: الموعد القادم
                is_active       INTEGER DEFAULT 1,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


# ══════════════════════════════════════════════════
#  User helpers
# ══════════════════════════════════════════════════

async def ensure_user(user_id: int, username: str | None = None) -> None:
    """تسجيل المستخدم إذا لم يكن موجودًا"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await db.commit()


async def is_premium(user_id: int) -> bool:
    """هل المستخدم premium (ولم ينتهِ اشتراكه)؟"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_premium, sub_end FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if not row or not row["is_premium"]:
                return False
            if row["sub_end"]:
                end = datetime.fromisoformat(row["sub_end"])
                if end < datetime.now(CAIRO):
                    # الاشتراك انتهى – نرجّع False ونحدّث
                    await db.execute(
                        "UPDATE users SET is_premium = 0 WHERE user_id = ?",
                        (user_id,),
                    )
                    await db.commit()
                    return False
            return True


async def update_premium(user_id: int, days: int = 30) -> None:
    """تفعيل Premium لمدة days يوم"""
    sub_end = (datetime.now(CAIRO) + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET is_premium = 1, sub_end = ? WHERE user_id = ?",
            (sub_end, user_id),
        )
        await db.commit()


async def get_subscription_info(user_id: int) -> dict | None:
    """إرجاع معلومات اشتراك المستخدم"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_premium, sub_end, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_premium_users() -> list[dict]:
    """إرجاع كل المستخدمين الـ premium الفعالين"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now_iso = datetime.now(CAIRO).isoformat()
        async with db.execute(
            "SELECT user_id FROM users WHERE is_premium = 1 AND sub_end > ?",
            (now_iso,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def check_expired_subscriptions() -> list[int]:
    """إرجاع وتحديث المستخدمين اللي اشتراكهم انتهى"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now_iso = datetime.now(CAIRO).isoformat()
        async with db.execute(
            "SELECT user_id FROM users WHERE is_premium = 1 AND sub_end <= ?",
            (now_iso,),
        ) as cur:
            rows = await cur.fetchall()
            expired = [r["user_id"] for r in rows]
        if expired:
            placeholders = ",".join("?" * len(expired))
            await db.execute(
                f"UPDATE users SET is_premium = 0 WHERE user_id IN ({placeholders})",
                expired,
            )
            await db.commit()
        return expired


# ══════════════════════════════════════════════════
#  Task helpers
# ══════════════════════════════════════════════════

async def count_tasks(user_id: int) -> int:
    """عدد المهام النشطة (غير المنتهية)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND is_done = 0",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def add_task(
    user_id: int,
    title: str,
    due: datetime | None = None,
    recurrence: str | None = None,
) -> int:
    """إضافة مهمة وإرجاع الـ ID"""
    due_str = due.isoformat() if due else None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tasks (user_id, title, due, recurrence) VALUES (?, ?, ?, ?)",
            (user_id, title, due_str, recurrence),
        )
        await db.commit()
        return cur.lastrowid


async def get_tasks(user_id: int, include_done: bool = False) -> list[dict]:
    """جلب مهام المستخدم"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_done:
            query = "SELECT * FROM tasks WHERE user_id = ? ORDER BY due ASC"
            params = (user_id,)
        else:
            query = "SELECT * FROM tasks WHERE user_id = ? AND is_done = 0 ORDER BY due ASC"
            params = (user_id,)
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def mark_done(task_id: int, user_id: int) -> bool:
    """تحديد مهمة كمنتهية"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_task(task_id: int, user_id: int) -> bool:
    """حذف مهمة"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_due_tasks() -> list[dict]:
    """المهام المستحقة الآن (due <= now) وغير منتهية وغير مُذَكَّر بها"""
    now_iso = datetime.now(CAIRO).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM tasks
               WHERE is_done = 0
                 AND reminded = 0
                 AND due IS NOT NULL
                 AND due <= ?""",
            (now_iso,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def mark_reminded(task_id: int) -> None:
    """وسم المهمة أنه تم التذكير بها"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,)
        )
        await db.commit()


async def get_today_tasks(user_id: int) -> list[dict]:
    """مهام اليوم (من بداية اليوم لنهايته) + المتأخرة"""
    now = datetime.now(CAIRO)
    start = now.replace(hour=0, minute=0, second=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM tasks
               WHERE user_id = ?
                 AND is_done = 0
                 AND due IS NOT NULL
                 AND due <= ?
               ORDER BY due ASC""",
            (user_id, end),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def handle_recurring_task(task: dict) -> None:
    """إعادة جدولة مهمة متكررة (daily/weekly)"""
    if not task.get("recurrence"):
        return
    due = datetime.fromisoformat(task["due"])
    if task["recurrence"] == "daily":
        new_due = due + timedelta(days=1)
    elif task["recurrence"] == "weekly":
        new_due = due + timedelta(weeks=1)
    else:
        return
    await add_task(
        user_id=task["user_id"],
        title=task["title"],
        due=new_due,
        recurrence=task["recurrence"],
    )


# ══════════════════════════════════════════════════
#  Reminder helpers (تذكيرات متكررة كل X دقيقة)
# ══════════════════════════════════════════════════

async def add_reminder(user_id: int, text: str, interval_mins: int) -> int:
    """إضافة تذكير متكرر وإرجاع الـ ID"""
    next_fire = (datetime.now(CAIRO) + timedelta(minutes=interval_mins)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO reminders (user_id, text, interval_mins, next_fire) VALUES (?, ?, ?, ?)",
            (user_id, text, interval_mins, next_fire),
        )
        await db.commit()
        return cur.lastrowid


async def get_due_reminders() -> list[dict]:
    """التذكيرات المستحقة الآن (next_fire <= now) والنشطة"""
    now_iso = datetime.now(CAIRO).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM reminders
               WHERE is_active = 1
                 AND next_fire <= ?""",
            (now_iso,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def advance_reminder(reminder_id: int) -> None:
    """تقديم موعد التذكير القادم بعد الإرسال"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT interval_mins FROM reminders WHERE id = ?", (reminder_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return
        next_fire = (
            datetime.now(CAIRO) + timedelta(minutes=row["interval_mins"])
        ).isoformat()
        await db.execute(
            "UPDATE reminders SET next_fire = ? WHERE id = ?",
            (next_fire, reminder_id),
        )
        await db.commit()


async def get_user_reminders(user_id: int) -> list[dict]:
    """جلب تذكيرات المستخدم النشطة"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE user_id = ? AND is_active = 1 ORDER BY id",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_reminders(user_id: int) -> int:
    """عدد التذكيرات النشطة"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM reminders WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def pause_reminder(reminder_id: int, user_id: int) -> bool:
    """إيقاف تذكير"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE reminders SET is_active = 0 WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def resume_reminder(reminder_id: int, user_id: int) -> bool:
    """استئناف تذكير"""
    next_fire = (datetime.now(CAIRO) + timedelta(minutes=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE reminders SET is_active = 1, next_fire = ? WHERE id = ? AND user_id = ?",
            (next_fire, reminder_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    """حذف تذكير"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0
