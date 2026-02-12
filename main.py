"""
Main entry point - Bot initialization and startup with improved error handling
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from database import Database
from sender import SenderManager
from handlers import router as user_router
from admin import router as admin_router
from config import BOT_TOKEN, SESSION_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce Telethon logging noise
logging.getLogger('telethon').setLevel(logging.WARNING)


async def on_startup(bot: Bot, db: Database, sender: SenderManager):
    """Actions on bot startup"""
    logger.info("Bot starting...")

    # Initialize database
    await db.init_db()
    logger.info("Database initialized")

    # Create sessions directory
    os.makedirs(SESSION_DIR, exist_ok=True)
    logger.info(f"Sessions directory ready: {SESSION_DIR}")

    # Restore active sending tasks
    await sender.restore_active_tasks()
    logger.info("Active tasks restored")

    logger.info("Bot started successfully")


async def on_shutdown(bot: Bot, sender: SenderManager):
    """Actions on bot shutdown"""
    logger.info("Bot shutting down...")

    # Stop subscription checker
    await sender.stop_subscription_checker()

    # Stop all active sending tasks safely
    user_ids = list(sender.active_tasks.keys())
    for user_id in user_ids:
        try:
            await sender.stop_sending(user_id)
        except Exception as e:
            logger.warning(f"Error stopping task for user {user_id}: {e}")

    logger.info("Bot stopped")


async def main():
    """Main function with retry logic for network errors"""
    retry_count = 0
    max_retries = 5

    while retry_count < max_retries:
        try:
            # Initialize bot
            bot = Bot(
                token=BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )

            # Initialize dispatcher
            dp = Dispatcher()

            # Initialize database and sender
            db = Database()
            sender = SenderManager(db)

            # Register routers
            dp.include_router(user_router)
            dp.include_router(admin_router)

            # Register middleware to pass db and sender to handlers
            @dp.update.outer_middleware()
            async def inject_dependencies(handler, event, data):
                data['db'] = db
                data['sender'] = sender
                return await handler(event, data)

            # Startup actions
            await on_startup(bot, db, sender)

            try:
                # Start polling with longer timeout and retry logic
                logger.info("Starting polling...")
                await dp.start_polling(
                    bot,
                    allowed_updates=dp.resolve_used_update_types(),
                    handle_as_tasks=True,  # Handle updates as tasks
                    timeout=60,  # 60 seconds timeout
                    relax=0.1  # 100ms between requests
                )
            finally:
                # Shutdown actions
                await on_shutdown(bot, sender)
                await bot.session.close()

            # If we got here without exception, break the retry loop
            break

        except TelegramNetworkError as e:
            retry_count += 1
            logger.warning(f"Network error (attempt {retry_count}/{max_retries}): {e}")

            if retry_count < max_retries:
                wait_time = min(5 * retry_count, 30)  # Max 30 seconds
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("Max retries reached. Giving up.")
                raise

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)