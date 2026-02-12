"""
Admin handlers - Admin panel functionality
"""
import asyncio
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import Database
from config import ADMIN_IDS, DB_PATH, BROADCAST_DELAY_MIN, BROADCAST_DELAY_MAX

router = Router()


class AdminStates(StatesGroup):
    add_group = State()
    broadcast = State()
    add_subscription = State()
    remove_subscription = State()


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_panel(message: Message, db: Database):
    """Show admin panel"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Ruxsat yo'q.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="⏰ Obuna boshqaruvi", callback_data="admin_subscription")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💾 Ma'lumotlar bazasi", callback_data="admin_download_db")]
    ])

    await message.answer("👮 Admin panel", reply_markup=keyboard)


@router.callback_query(F.data == "admin_users")
async def show_users(callback: CallbackQuery, db: Database):
    """Show users list"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    users = await db.get_all_users()

    if not users:
        await callback.message.edit_text("📊 Foydalanuvchilar yo'q.")
        return

    text = "📊 Foydalanuvchilar ro'yxati:\n\n"

    import time
    now = int(time.time())

    for user in users[:10]:  # Show first 10
        status = "🟢" if user['is_active'] else "⚪️"
        banned = "🚫" if user['is_banned'] else ""
        logged = "✅" if user['is_logged_in'] else "❌"

        # Check subscription
        sub_until = user.get('subscription_until', 0)
        if sub_until > now:
            days_left = (sub_until - now) // 86400
            sub_status = f"⏰ {days_left} kun"
        else:
            sub_status = "❌ Obuna yo'q"

        text += f"{status} {user['full_name']}\n"
        text += f"ID: {user['user_id']} | {sub_status} | Profil: {logged} {banned}\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_subscription")
async def subscription_menu(callback: CallbackQuery):
    """Show subscription management menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    text = (
        "⏰ Obuna boshqaruvi\n\n"
        "Buyruqlar:\n"
        "/add30day_USER_ID - 30 kun qo'shish\n"
        "/add7day_USER_ID - 7 kun qo'shish\n"
        "/add365day_USER_ID - 365 kun qo'shish\n"
        "/removesub_USER_ID - Obunani olib qo'yish\n\n"
        "Yoki quyidagi tugmalardan foydalaning:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Obuna qo'shish", callback_data="admin_add_sub")],
        [InlineKeyboardButton(text="🗑 Obunani olib qo'yish", callback_data="admin_remove_sub")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_back")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_add_sub")
async def add_subscription_start(callback: CallbackQuery, state: FSMContext):
    """Start add subscription flow"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ Obuna qo'shish\n\n"
        "Format: USER_ID KUNLAR\n"
        "Misol: 6700049540 30"
    )
    await state.set_state(AdminStates.add_subscription)
    await callback.answer()


@router.message(AdminStates.add_subscription)
async def add_subscription_finish(message: Message, state: FSMContext, db: Database):
    """Finish add subscription"""
    if not is_admin(message.from_user.id):
        return

    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.answer("❌ Noto'g'ri format. Misol: 6700049540 30")
            return

        user_id = int(parts[0])
        days = int(parts[1])

        if days <= 0:
            await message.answer("❌ Kunlar soni musbat bo'lishi kerak.")
            return

        # Check if user exists
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Foydalanuvchi {user_id} topilmadi.")
            return

        new_expiry = await db.add_subscription(user_id, days)

        import time
        expiry_date = time.strftime('%Y-%m-%d %H:%M', time.localtime(new_expiry))

        await message.answer(
            f"✅ Obuna qo'shildi!\n\n"
            f"Foydalanuvchi: {user['full_name']}\n"
            f"ID: {user_id}\n"
            f"Qo'shildi: {days} kun\n"
            f"Tugash sanasi: {expiry_date}"
        )

        # Notify user
        try:
            await message.bot.send_message(
                user_id,
                f"✅ Obuna faollashtirildi!\n\n"
                f"Muddat: {days} kun\n"
                f"Tugash sanasi: {expiry_date}"
            )
        except:
            pass

    except ValueError:
        await message.answer("❌ Noto'g'ri format. Faqat raqamlar kiriting.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")

    await state.clear()


@router.callback_query(F.data == "admin_remove_sub")
async def remove_subscription_start(callback: CallbackQuery, state: FSMContext):
    """Start remove subscription flow"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 Obunani olib qo'yish\n\n"
        "Foydalanuvchi ID sini yuboring:"
    )
    await state.set_state(AdminStates.remove_subscription)
    await callback.answer()


@router.message(AdminStates.remove_subscription)
async def remove_subscription_finish(message: Message, state: FSMContext, db: Database, sender):
    """Finish remove subscription"""
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())

        # Check if user exists
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Foydalanuvchi {user_id} topilmadi.")
            return

        # Stop sending if active
        if user['is_active']:
            await sender.stop_sending(user_id)

        await db.remove_subscription(user_id)

        await message.answer(
            f"✅ Obuna olib qo'yildi!\n\n"
            f"Foydalanuvchi: {user['full_name']}\n"
            f"ID: {user_id}"
        )

        # Notify user
        try:
            from config import ADMIN_CONTACT
            await message.bot.send_message(
                user_id,
                f"❌ Obuna muddati tugadi.\n\n"
                f"Yangilash uchun adminga murojaat qiling: {ADMIN_CONTACT}"
            )
        except:
            pass

    except ValueError:
        await message.answer("❌ Noto'g'ri format. Faqat raqam kiriting.")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")

    await state.clear()


# Command handlers for quick subscription management
@router.message(Command(commands=["add30day", "add7day", "add365day"]))
async def quick_add_subscription(message: Message, db: Database):
    """Quick add subscription via command"""
    if not is_admin(message.from_user.id):
        return

    try:
        # Extract command and user_id
        parts = message.text.split('_')
        if len(parts) != 2:
            await message.answer("❌ Format: /add30day_USER_ID")
            return

        command = parts[0][1:]  # Remove /
        user_id = int(parts[1])

        # Determine days based on command
        if "30day" in command:
            days = 30
        elif "7day" in command:
            days = 7
        elif "365day" in command:
            days = 365
        else:
            await message.answer("❌ Noma'lum buyruq.")
            return

        # Check if user exists
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Foydalanuvchi {user_id} topilmadi.")
            return

        new_expiry = await db.add_subscription(user_id, days)

        import time
        expiry_date = time.strftime('%Y-%m-%d %H:%M', time.localtime(new_expiry))

        await message.answer(
            f"✅ Obuna qo'shildi!\n\n"
            f"Foydalanuvchi: {user['full_name']}\n"
            f"ID: {user_id}\n"
            f"Qo'shildi: {days} kun\n"
            f"Tugash sanasi: {expiry_date}"
        )

        # Notify user
        try:
            await message.bot.send_message(
                user_id,
                f"✅ Obuna faollashtirildi!\n\n"
                f"Muddat: {days} kun\n"
                f"Tugash sanasi: {expiry_date}"
            )
        except:
            pass

    except ValueError:
        await message.answer("❌ Noto'g'ri format. Misol: /add30day_6700049540")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")


@router.message(Command("removesub"))
async def quick_remove_subscription(message: Message, db: Database, sender):
    """Quick remove subscription via command"""
    if not is_admin(message.from_user.id):
        return

    try:
        # Extract user_id
        parts = message.text.split('_')
        if len(parts) != 2:
            await message.answer("❌ Format: /removesub_USER_ID")
            return

        user_id = int(parts[1])

        # Check if user exists
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Foydalanuvchi {user_id} topilmadi.")
            return

        # Stop sending if active
        if user['is_active']:
            await sender.stop_sending(user_id)

        await db.remove_subscription(user_id)

        await message.answer(
            f"✅ Obuna olib qo'yildi!\n\n"
            f"Foydalanuvchi: {user['full_name']}\n"
            f"ID: {user_id}"
        )

        # Notify user
        try:
            from config import ADMIN_CONTACT
            await message.bot.send_message(
                user_id,
                f"❌ Obuna muddati tugadi.\n\n"
                f"Yangilash uchun adminga murojaat qiling: {ADMIN_CONTACT}"
            )
        except:
            pass

    except ValueError:
        await message.answer("❌ Noto'g'ri format. Misol: /removesub_6700049540")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Start broadcast flow"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 Broadcast xabar\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabarni yuboring:"
    )
    await state.set_state(AdminStates.broadcast)
    await callback.answer()


@router.message(AdminStates.broadcast)
async def broadcast_send(message: Message, state: FSMContext, db: Database):
    """Send broadcast message"""
    if not is_admin(message.from_user.id):
        return

    broadcast_text = message.text
    if not broadcast_text:
        await message.answer("❌ Matn yuboring.")
        return

    # Get all users
    users = await db.get_all_users()

    if not users:
        await message.answer("❌ Foydalanuvchilar yo'q.")
        await state.clear()
        return

    status_msg = await message.answer(
        f"📢 Broadcast boshlandi...\n"
        f"Jami: {len(users)} ta foydalanuvchi"
    )

    success = 0
    failed = 0

    for user in users:
        try:
            await message.bot.send_message(user['user_id'], broadcast_text)
            success += 1
            # Random delay to avoid flood
            await asyncio.sleep(random.uniform(BROADCAST_DELAY_MIN, BROADCAST_DELAY_MAX))
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ Broadcast tugadi!\n\n"
        f"Yuborildi: {success}\n"
        f"Xatolik: {failed}\n"
        f"Jami: {len(users)}"
    )

    await state.clear()


@router.callback_query(F.data == "admin_download_db")
async def download_database(callback: CallbackQuery):
    """Download database file"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    try:
        db_file = FSInputFile(DB_PATH)
        await callback.message.answer_document(
            db_file,
            caption="💾 Ma'lumotlar bazasi"
        )
        await callback.answer("✅ Yuborildi!")
    except Exception as e:
        await callback.answer(f"❌ Xatolik: {str(e)}", show_alert=True)


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, db: Database):
    """Return to admin panel"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔️ Ruxsat yo'q.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Foydalanuvchilar", callback_data="admin_users")],
        [InlineKeyboardButton(text="⏰ Obuna boshqaruvi", callback_data="admin_subscription")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💾 Ma'lumotlar bazasi", callback_data="admin_download_db")]
    ])

    await callback.message.edit_text("👮 Admin panel", reply_markup=keyboard)
    await callback.answer()