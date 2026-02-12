"""
Database module - SQLite operations
"""
import aiosqlite
import time
from typing import Optional, List, Dict
from config import DB_PATH


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initialize database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS users
                             (
                                 user_id
                                 INTEGER
                                 PRIMARY
                                 KEY,
                                 full_name
                                 TEXT,
                                 is_logged_in
                                 INTEGER
                                 DEFAULT
                                 0,
                                 is_active
                                 INTEGER
                                 DEFAULT
                                 0,
                                 is_banned
                                 INTEGER
                                 DEFAULT
                                 0,
                                 subscription_until
                                 INTEGER
                                 DEFAULT
                                 0,
                                 created_at
                                 INTEGER,
                                 updated_at
                                 INTEGER
                             )
                             """)

            # Profiles table
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS profiles
                             (
                                 user_id
                                 INTEGER
                                 PRIMARY
                                 KEY,
                                 phone
                                 TEXT,
                                 session
                                 TEXT,
                                 updated_at
                                 INTEGER
                             )
                             """)

            # Messages table
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS messages
                             (
                                 user_id
                                 INTEGER
                                 PRIMARY
                                 KEY,
                                 text
                                 TEXT,
                                 updated_at
                                 INTEGER
                             )
                             """)

            # Admin settings table
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS admin_settings
                             (
                                 key
                                 TEXT
                                 PRIMARY
                                 KEY,
                                 value
                                 TEXT
                             )
                             """)

            # User selected groups table (user can select up to 3 groups from their chats)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS user_groups
                             (
                                 id
                                 INTEGER
                                 PRIMARY
                                 KEY
                                 AUTOINCREMENT,
                                 user_id
                                 INTEGER,
                                 group_id
                                 INTEGER,
                                 group_title
                                 TEXT,
                                 added_at
                                 INTEGER,
                                 UNIQUE
                             (
                                 user_id,
                                 group_id
                             )
                                 )
                             """)

            await db.commit()

    async def upsert_user(self, user_id: int, full_name: str):
        """Insert or update user"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            await db.execute("""
                             INSERT INTO users (user_id, full_name, created_at, updated_at)
                             VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO
                             UPDATE SET
                                 full_name = excluded.full_name,
                                 updated_at = excluded.updated_at
                             """, (user_id, full_name, now, now))
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_user_login_status(self, user_id: int, is_logged_in: int):
        """Update user login status"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_logged_in = ?, updated_at = ? WHERE user_id = ?",
                (is_logged_in, int(time.time()), user_id)
            )
            await db.commit()

    async def update_user_active_status(self, user_id: int, is_active: int):
        """Update user active status"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE user_id = ?",
                (is_active, int(time.time()), user_id)
            )
            await db.commit()

    async def ban_user(self, user_id: int):
        """Ban user"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_banned = 1, is_active = 0, updated_at = ? WHERE user_id = ?",
                (int(time.time()), user_id)
            )
            await db.commit()

    async def upsert_profile(self, user_id: int, phone: str, session: str):
        """Insert or update profile"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            await db.execute("""
                             INSERT INTO profiles (user_id, phone, session, updated_at)
                             VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO
                             UPDATE SET
                                 phone = excluded.phone,
                                 session = excluded.session,
                                 updated_at = excluded.updated_at
                             """, (user_id, phone, session, now))
            await db.commit()

    async def get_profile(self, user_id: int) -> Optional[Dict]:
        """Get profile by user ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_profile(self, user_id: int):
        """Delete profile"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
            await db.commit()

    async def upsert_message(self, user_id: int, text: str):
        """Insert or update message (overwrites existing)"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            await db.execute("""
                             INSERT INTO messages (user_id, text, updated_at)
                             VALUES (?, ?, ?) ON CONFLICT(user_id) DO
                             UPDATE SET
                                 text = excluded.text,
                                 updated_at = excluded.updated_at
                             """, (user_id, text, now))
            await db.commit()

    async def get_message(self, user_id: int) -> Optional[Dict]:
        """Get message by user ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM messages WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_message(self, user_id: int):
        """Delete message"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_active_users(self) -> List[Dict]:
        """Get all active and not banned users"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM users WHERE is_active = 1 AND is_banned = 0"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_users(self) -> List[Dict]:
        """Get all users"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def add_user_group(self, user_id: int, group_id: int, group_title: str):
        """Add group to user's selected groups (max 3)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if user already has 3 groups
            async with db.execute(
                    "SELECT COUNT(*) FROM user_groups WHERE user_id = ?", (user_id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
                if count >= 3:
                    return False

            # Add group
            try:
                await db.execute("""
                                 INSERT INTO user_groups (user_id, group_id, group_title, added_at)
                                 VALUES (?, ?, ?, ?)
                                 """, (user_id, group_id, group_title, int(time.time())))
                await db.commit()
                return True
            except:
                return False

    async def remove_user_group(self, user_id: int, group_id: int):
        """Remove group from user's selected groups"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM user_groups WHERE user_id = ? AND group_id = ?",
                (user_id, group_id)
            )
            await db.commit()

    async def get_user_groups(self, user_id: int) -> List[int]:
        """Get user's selected group IDs"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    "SELECT group_id FROM user_groups WHERE user_id = ?", (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def get_user_groups_with_titles(self, user_id: int) -> List[Dict]:
        """Get user's selected groups with titles"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM user_groups WHERE user_id = ?", (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def clear_user_groups(self, user_id: int):
        """Clear all user's selected groups"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
            await db.commit()

    async def save_user_groups(self, user_id: int, groups: List[tuple]):
        """Save user's selected groups (replace all)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Clear existing
            await db.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))

            # Add new groups
            now = int(time.time())
            for group_id, group_title in groups:
                await db.execute("""
                                 INSERT INTO user_groups (user_id, group_id, group_title, added_at)
                                 VALUES (?, ?, ?, ?)
                                 """, (user_id, group_id, group_title, now))

            await db.commit()

    async def add_subscription(self, user_id: int, days: int):
        """Add subscription days to user"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            # Get current subscription
            async with db.execute(
                    "SELECT subscription_until FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if row and row[0] > now:
                # Extend existing subscription
                new_expiry = row[0] + (days * 86400)
            else:
                # New subscription from now
                new_expiry = now + (days * 86400)

            await db.execute(
                "UPDATE users SET subscription_until = ?, updated_at = ? WHERE user_id = ?",
                (new_expiry, now, user_id)
            )
            await db.commit()
            return new_expiry

    async def remove_subscription(self, user_id: int):
        """Remove user subscription"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET subscription_until = 0, is_active = 0, updated_at = ? WHERE user_id = ?",
                (int(time.time()), user_id)
            )
            await db.commit()

    async def check_subscription(self, user_id: int) -> bool:
        """Check if user has active subscription"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            async with db.execute(
                    "SELECT subscription_until FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return bool(row and row[0] > now)

    async def get_expired_subscriptions(self) -> List[int]:
        """Get users with expired subscriptions who are still active"""
        async with aiosqlite.connect(self.db_path) as db:
            now = int(time.time())
            async with db.execute(
                    "SELECT user_id FROM users WHERE subscription_until > 0 AND subscription_until < ? AND is_active = 1",
                    (now,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]