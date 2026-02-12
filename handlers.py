"""
User handlers - Main bot functionality
"""
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import Database
from sender import SenderManager
from config import DEFAULT_RANDOM_INTERVAL_MIN, DEFAULT_RANDOM_INTERVAL_MAX

router = Router()


class UserStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()
    waiting_message = State()


def get_main_keyboard(is_ready: bool) -> ReplyKeyboardMarkup:
    """Get main reply keyboard"""
    buttons = [
        [KeyboardButton(text="👥 Profil")],
        [KeyboardButton(text="📁 Guruhlar")],
        [KeyboardButton(text="💬 Elon")],
        [KeyboardButton(text="▶️ Ishga tushirish")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def check_user_access(db: Database, user_id: int) -> tuple[bool, str]:
    """Check if user has access to bot"""
    user = await db.get_user(user_id)

    if not user:
        return False, "Foydalanuvchi topilmadi."

    if user['is_banned']:
        return False, "⛔️ Siz bloklangansiz."

    has_subscription = await db.check_subscription(user_id)
    if not has_subscription:
        from config import ADMIN_CONTACT
        return False, f"❌ Obuna muddati tugagan.\n\nYangilash uchun adminga murojaat qiling: {ADMIN_CONTACT}"

    return True, ""


async def is_user_ready(db: Database, user_id: int) -> bool:
    """Check if user is ready to start sending"""
    user = await db.get_user(user_id)
    if not user or user['is_logged_in'] == 0:
        return False

    profile = await db.get_profile(user_id)
    message = await db.get_message(user_id)
    user_groups = await db.get_user_groups(user_id)

    return bool(profile and message and user_groups)


@router.message(CommandStart())
async def start_handler(message: Message, db: Database):
    """Handle /start command"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name or "Foydalanuvchi"

    await db.upsert_user(user_id, full_name)

    user = await db.get_user(user_id)

    if user['is_banned']:
        await message.answer("⛔️ Siz bloklangansiz.")
        return

    # Check subscription
    has_subscription = await db.check_subscription(user_id)

    if not has_subscription:
        from config import ADMIN_CONTACT
        text = (
            f"👋 Xush kelibsiz, {full_name}!\n\n"
            "❌ Sizning botdan foydalanish ruxsatingiz yo'q.\n\n"
            f"Ruxsat olish uchun adminga murojaat qiling: {ADMIN_CONTACT}"
        )
        await message.answer(text)
        return

    is_ready = await is_user_ready(db, user_id)

    if user['is_logged_in'] == 0:
        text = (
            f"👋 Xush kelibsiz, {full_name} 🥷!\n\n"
            "Hozircha profil yo'q.\n"
            "Profil qo'shish uchun «Profil» tugmasini bosing"
        )
    else:
        text = f"👋 Xush kelibsiz, {full_name} 🥷!"

    keyboard = get_main_keyboard(is_ready)
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "👥 Profil")
async def profile_handler(message: Message, db: Database):
    """Handle profile button"""
    user_id = message.from_user.id

    # Check access
    has_access, error_msg = await check_user_access(db, user_id)
    if not has_access:
        await message.answer(error_msg)
        return

    profile = await db.get_profile(user_id)

    if not profile:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Profil qo'shish", callback_data="profile_add")]
        ])
        await message.answer("👥 Sizda profil yo'q.", reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Profilni o'chirish", callback_data="profile_delete")]
        ])

        text = (
            f"👥 Profil ma'lumotlari:\n\n"
            f"📱 Telefon: {profile['phone']}\n"
            f"✅ Holat: Faol"
        )
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "profile_add")
async def profile_add_start(callback: CallbackQuery, state: FSMContext):
    """Start profile add flow"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Kontaktni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.edit_text("📱 Telefon raqamingizni yuboring:")
    await callback.message.answer("Kontaktni ulashish yoki raqamni kiriting:", reply_markup=keyboard)
    await state.set_state(UserStates.waiting_phone)
    await callback.answer()


@router.message(UserStates.waiting_phone)
async def profile_phone_received(message: Message, state: FSMContext, sender: SenderManager):
    """Receive phone and send code"""
    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        phone = message.text.strip()
    else:
        await message.answer("❌ Telefon raqamini yuboring.")
        return

    # Ensure phone starts with +
    if not phone.startswith('+'):
        phone = '+' + phone

    try:
        client, phone_code_hash = await sender.send_code(phone)

        await state.update_data(
            phone=phone,
            phone_code_hash=phone_code_hash,
            client=client
        )

        await message.answer(
            "📨 Telegram'dan kelgan kodni kiriting.\n\n"
            "Masalan: 54.568\n"
            "(Nuqtalarni qo'shishni unutmang !!!)",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
                resize_keyboard=True
            )
        )
        await state.set_state(UserStates.waiting_code)

    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
        await state.clear()


@router.message(UserStates.waiting_code)
async def profile_code_received(message: Message, state: FSMContext, db: Database, sender: SenderManager):
    """Receive verification code"""
    if message.text == "❌ Bekor qilish":
        await message.answer("❌ Bekor qilindi.", reply_markup=get_main_keyboard(False))
        await state.clear()
        return

    code = message.text.strip().replace('.', '').replace(' ', '')

    data = await state.get_data()
    client = data['client']
    phone = data['phone']
    phone_code_hash = data['phone_code_hash']

    try:
        session_string = await sender.verify_code(client, phone, code, phone_code_hash)

        # Save profile
        user_id = message.from_user.id
        await db.upsert_profile(user_id, phone, session_string)
        await db.update_user_login_status(user_id, 1)

        user = await db.get_user(user_id)
        name = user['full_name']

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Profilni o'chirish", callback_data="profile_delete")]
        ])

        await message.answer(
            f"✅ Profil qo'shildi.\n✅ {name} 🥷, bot tayyor.",
            reply_markup=keyboard
        )

        await message.answer("Asosiy menyu:", reply_markup=get_main_keyboard(True))
        await state.clear()

    except Exception as e:
        error_str = str(e)

        if "password" in error_str.lower() or "2fa" in error_str.lower():
            await message.answer("🔐 2 bosqichli parol kerak. Parolni kiriting:")
            await state.set_state(UserStates.waiting_password)
        else:
            await message.answer(f"❌ Xatolik: {error_str}")
            await state.clear()


@router.message(UserStates.waiting_password)
async def profile_password_received(message: Message, state: FSMContext, db: Database, sender: SenderManager):
    """Receive 2FA password"""
    password = message.text.strip()
    data = await state.get_data()
    client = data['client']
    phone = data['phone']
    phone_code_hash = data['phone_code_hash']

    # We need to get code again from state or ask user
    # For simplicity, assume we stored it
    code = data.get('code', '')

    try:
        await client.sign_in(password=password)
        session_string = client.session.save()

        user_id = message.from_user.id
        await db.upsert_profile(user_id, phone, session_string)
        await db.update_user_login_status(user_id, 1)

        user = await db.get_user(user_id)
        name = user['full_name']

        await message.answer(
            f"✅ Profil qo'shildi.\n✅ {name} 🥷, bot tayyor.",
            reply_markup=get_main_keyboard(True)
        )
        await state.clear()

    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
        await state.clear()


@router.callback_query(F.data == "profile_delete")
async def profile_delete_confirm(callback: CallbackQuery, sender: SenderManager, db: Database):
    """Delete profile"""
    user_id = callback.from_user.id

    # Stop sending and cleanup
    await sender.cleanup_profile(user_id)

    await callback.message.edit_text("✅ Profil o'chirildi.")
    await callback.answer()


@router.message(F.text == "📁 Guruhlar")
async def groups_handler(message: Message, db: Database, sender: SenderManager):
    """Handle groups button"""
    user_id = message.from_user.id

    # Check access
    has_access, error_msg = await check_user_access(db, user_id)
    if not has_access:
        await message.answer(error_msg)
        return

    # Check if user has profile
    profile = await db.get_profile(user_id)
    if not profile:
        await message.answer(
            "❌ Avval profil qo'shishingiz kerak.\n\n"
            "👥 Profil tugmasini bosing."
        )
        return

    # Show loading message
    loading_msg = await message.answer("⏳ Guruhlar yuklanmoqda...")

    # Get user's dialogs (groups/channels)
    dialogs = await sender.get_user_dialogs(user_id)

    await loading_msg.delete()

    if not dialogs:
        await message.answer(
            "❌ Hech qanday guruh topilmadi.\n\n"
            "Siz biror guruhga a'zo bo'lishingiz kerak."
        )
        return

    # Get user's current selected groups
    user_groups = await db.get_user_groups_with_titles(user_id)
    selected_ids = [g['group_id'] for g in user_groups]

    text = f"📁 Guruhlarni tanlang ({len(selected_ids)}/3)\n\n"
    text += "Maksimum 3 ta guruhni tanlang.\n"
    text += "Tanlash tugagach 'Saqlash' tugmasini bosing.\n\n"

    # Create inline keyboard with user's dialogs
    keyboard_buttons = []
    for dialog in dialogs[:20]:  # Show max 20 groups
        is_selected = dialog['id'] in selected_ids

        # Show checkmark if selected
        button_text = f"✅ {dialog['title']}" if is_selected else f"⬜️ {dialog['title']}"
        callback_data = f"select_group_{dialog['id']}"

        keyboard_buttons.append([
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        ])

    # Add action buttons
    action_buttons = []
    if selected_ids:
        action_buttons.append(
            InlineKeyboardButton(text="💾 Saqlash", callback_data="save_groups")
        )
        action_buttons.append(
            InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_all_groups")
        )

    if action_buttons:
        keyboard_buttons.append(action_buttons)

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("select_group_"))
async def select_group(callback: CallbackQuery, db: Database, sender: SenderManager):
    """Toggle group selection (temporary, not saved until user clicks Save)"""
    user_id = callback.from_user.id
    group_id = int(callback.data.split("_")[-1])

    # Get all dialogs
    dialogs = await sender.get_user_dialogs(user_id)
    dialog_map = {d['id']: d['title'] for d in dialogs}

    # Parse current selections from the MESSAGE BUTTONS (not from database!)
    selected_ids = []
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for button in row:
                if button.text.startswith("✅"):
                    # This button is selected - extract group_id from callback_data
                    try:
                        btn_group_id = int(button.callback_data.split("_")[-1])
                        selected_ids.append(btn_group_id)
                    except (ValueError, AttributeError):
                        pass

    # Toggle the clicked group
    if group_id in selected_ids:
        # Remove group (deselect)
        selected_ids.remove(group_id)
        await callback.answer("❌ Olib tashlandi")
    else:
        # Add group (select)
        if len(selected_ids) >= 3:
            await callback.answer("⚠️ Maksimum 3 ta guruh!", show_alert=True)
            return

        selected_ids.append(group_id)
        await callback.answer("✅ Tanlandi")

    # Rebuild the keyboard with updated selections
    text = f"📁 Guruhlarni tanlang ({len(selected_ids)}/3)\n\n"
    text += "Maksimum 3 ta guruhni tanlang.\n"
    text += "Tanlash tugagach 'Saqlash' tugmasini bosing.\n\n"

    keyboard_buttons = []
    for dialog in dialogs[:20]:
        is_selected = dialog['id'] in selected_ids

        button_text = f"✅ {dialog['title']}" if is_selected else f"⬜️ {dialog['title']}"
        callback_data = f"select_group_{dialog['id']}"

        keyboard_buttons.append([
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        ])

    # Add action buttons
    action_buttons = []
    if selected_ids:
        action_buttons.append(
            InlineKeyboardButton(text="💾 Saqlash", callback_data="save_groups")
        )
        action_buttons.append(
            InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_temp_groups")
        )

    if action_buttons:
        keyboard_buttons.append(action_buttons)

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # Update the message
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        # Silently ignore if message wasn't modified (same content)
        pass


@router.callback_query(F.data == "save_groups")
async def save_groups(callback: CallbackQuery, db: Database, sender: SenderManager):
    """Save selected groups to database"""
    user_id = callback.from_user.id

    # Get dialogs to map IDs to titles
    dialogs = await sender.get_user_dialogs(user_id)
    dialog_map = {d['id']: d['title'] for d in dialogs}

    # Parse selected groups from current message buttons
    selected_groups = []
    for row in callback.message.reply_markup.inline_keyboard:
        for button in row:
            if button.text.startswith("✅"):
                # This is a selected group
                group_id = int(button.callback_data.split("_")[-1])
                group_title = button.text[2:]  # Remove ✅ and space
                selected_groups.append((group_id, group_title))

    if not selected_groups:
        await callback.answer("❌ Hech narsa tanlanmagan!", show_alert=True)
        return

    # Save to database
    await db.save_user_groups(user_id, selected_groups)

    await callback.message.edit_text(
        f"✅ {len(selected_groups)} ta guruh saqlandi!\n\n"
        + "\n".join([f"• {title}" for _, title in selected_groups])
    )
    await callback.answer("✅ Saqlandi!")


@router.callback_query(F.data == "clear_temp_groups")
async def clear_temp_groups(callback: CallbackQuery, sender: SenderManager):
    """Clear temporary selections (clear all checkmarks)"""
    user_id = callback.from_user.id

    # Get dialogs
    dialogs = await sender.get_user_dialogs(user_id)

    text = f"📁 Guruhlarni tanlang (0/3)\n\n"
    text += "Maksimum 3 ta guruhni tanlang.\n"
    text += "Tanlash tugagach 'Saqlash' tugmasini bosing.\n\n"

    keyboard_buttons = []
    for dialog in dialogs[:20]:
        button_text = f"⬜️ {dialog['title']}"
        callback_data = f"select_group_{dialog['id']}"

        keyboard_buttons.append([
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("🗑 Tanlovlar tozalandi")


@router.callback_query(F.data == "clear_all_groups")
async def clear_all_groups(callback: CallbackQuery, db: Database):
    """Clear all saved groups from database"""
    user_id = callback.from_user.id

    await db.clear_user_groups(user_id)

    await callback.message.edit_text("✅ Barcha guruhlar o'chirildi.")
    await callback.answer("✅ O'chirildi")


@router.message(F.text == "💬 Elon")
async def message_handler(message: Message, state: FSMContext, db: Database):
    """Handle message button"""
    user_id = message.from_user.id

    # Check access
    has_access, error_msg = await check_user_access(db, user_id)
    if not has_access:
        await message.answer(error_msg)
        return

    await message.answer("💬 Yubormoqchi bo'lgan matnni yuboring:")
    await state.set_state(UserStates.waiting_message)


@router.message(UserStates.waiting_message)
async def message_text_received(message: Message, state: FSMContext, db: Database):
    """Receive message text"""
    text = message.text

    if not text:
        await message.answer("❌ Matn yuboring.")
        return

    user_id = message.from_user.id
    await db.upsert_message(user_id, text)

    await message.answer("✅ Matn saqlandi.", reply_markup=get_main_keyboard(True))
    await state.clear()


@router.message(F.text == "▶️ Ishga tushirish")
async def start_sending_handler(message: Message, db: Database):
    """Handle start sending button"""
    user_id = message.from_user.id

    # Check access
    has_access, error_msg = await check_user_access(db, user_id)
    if not has_access:
        await message.answer(error_msg)
        return

    user = await db.get_user(user_id)
    is_ready = await is_user_ready(db, user_id)

    if not is_ready:
        missing = []
        if user['is_logged_in'] == 0:
            missing.append("Profil")

        msg = await db.get_message(user_id)
        if not msg:
            missing.append("Elon matni")

        user_groups = await db.get_user_groups(user_id)
        if not user_groups:
            missing.append("Guruhlar tanlash")

        await message.answer(
            f"❌ Yuborish uchun tayyor emas.\n\n"
            f"Yetishmayotgan: {', '.join(missing)}"
        )
        return

    # Check if already active
    if user['is_active'] == 1:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔴 To'xtatish", callback_data="stop_sending")]
        ])
        await message.answer("🟢 Yuborish faol.", reply_markup=keyboard)
        return

    interval_min = DEFAULT_RANDOM_INTERVAL_MIN // 60
    interval_max = DEFAULT_RANDOM_INTERVAL_MAX // 60

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Boshlash", callback_data="start_sending")]
    ])

    text = (
        "🟢 Boshlash uchun tugmani bosing\n\n"
        f"✅ Interval: {interval_min}–{interval_max} daqiqa (tasodifiy)"
    )

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "start_sending")
async def start_sending_callback(callback: CallbackQuery, sender: SenderManager, db: Database):
    """Start sending"""
    user_id = callback.from_user.id

    await sender.start_sending(user_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 To'xtatish", callback_data="stop_sending")]
    ])

    await callback.message.edit_text("🟢 Yuborish boshlandi.", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "stop_sending")
async def stop_sending_callback(callback: CallbackQuery, sender: SenderManager, db: Database):
    """Stop sending"""
    user_id = callback.from_user.id

    await sender.stop_sending(user_id)

    await callback.message.edit_text("🔴 Yuborish to'xtatildi.")
    await callback.answer()