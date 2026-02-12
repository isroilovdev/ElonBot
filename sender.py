"""
Sender module - Handles Telethon message sending with safe retry logic
"""
import asyncio
import random
import os
from typing import Dict, Optional, List
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.sessions import StringSession
from database import Database
from config import (
    API_ID, API_HASH, SESSION_DIR,
    DEFAULT_RANDOM_INTERVAL_MIN, DEFAULT_RANDOM_INTERVAL_MAX,
    MAX_RETRY_ATTEMPTS, BASE_RETRY_DELAY, MAX_RETRY_DELAY
)


class SenderManager:
    def __init__(self, db: Database):
        self.db = db
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self.clients: Dict[int, TelegramClient] = {}
        self.subscription_checker_task: Optional[asyncio.Task] = None

    async def create_client(self, user_id: int, session_string: str) -> TelegramClient:
        """Create or reuse Telethon client"""
        if user_id in self.clients:
            # Check if client is connected
            if self.clients[user_id].is_connected():
                return self.clients[user_id]
            else:
                # Remove disconnected client
                try:
                    del self.clients[user_id]
                except KeyError:
                    pass

        client = TelegramClient(
            StringSession(session_string),
            API_ID,
            API_HASH,
            connection_retries=3,
            retry_delay=5,
            receive_updates=False,  # Disable updates to reduce traffic
            flood_sleep_threshold=0  # Don't auto-sleep on flood, we handle it
        )

        await client.connect()
        self.clients[user_id] = client
        return client

    async def send_code(self, phone: str) -> tuple[TelegramClient, str]:
        """Send verification code"""
        session_string = StringSession()
        client = TelegramClient(
            session_string,
            API_ID,
            API_HASH,
            receive_updates=False,
            flood_sleep_threshold=0
        )
        await client.connect()

        result = await client.send_code_request(phone)
        phone_code_hash = result.phone_code_hash

        return client, phone_code_hash

    async def verify_code(self, client: TelegramClient, phone: str, code: str, phone_code_hash: str,
                          password: str = None):
        """Verify code and login"""
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if password:
                await client.sign_in(password=password)
            else:
                raise

        session_string = client.session.save()
        return session_string

    async def get_user_dialogs(self, user_id: int) -> List[Dict]:
        """Get user's group dialogs from Telethon (groups and megagroups, no channels)"""
        try:
            profile = await self.db.get_profile(user_id)
            if not profile:
                return []

            # Create temporary client to get dialogs
            client = await self.create_client(user_id, profile['session'])

            dialogs = []
            async for dialog in client.iter_dialogs():
                # Include both regular groups AND megagroups (supergroups)
                # Exclude channels (is_channel=True but not is_group)
                if dialog.is_group or (hasattr(dialog.entity, 'megagroup') and dialog.entity.megagroup):
                    # Skip channels that are marked as groups
                    if hasattr(dialog.entity, 'broadcast') and dialog.entity.broadcast:
                        continue

                    dialogs.append({
                        'id': dialog.id,
                        'title': dialog.title or f"Chat {dialog.id}"
                    })

            return dialogs

        except Exception as e:
            # Log error silently, return empty list
            return []

    async def start_sending(self, user_id: int):
        """Start sending task for user"""
        # Prevent duplicate tasks
        if user_id in self.active_tasks and not self.active_tasks[user_id].done():
            return

        # Mark user as active
        await self.db.update_user_active_status(user_id, 1)

        # Create and store task
        task = asyncio.create_task(self._sending_loop(user_id))
        self.active_tasks[user_id] = task

    async def stop_sending(self, user_id: int):
        """Stop sending task for user"""
        # Mark user as inactive
        await self.db.update_user_active_status(user_id, 0)

        # Cancel task if exists
        if user_id in self.active_tasks:
            task = self.active_tasks[user_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            # Safely remove from dict
            try:
                del self.active_tasks[user_id]
            except KeyError:
                pass

        # Disconnect client if exists
        if user_id in self.clients:
            try:
                await self.clients[user_id].disconnect()
            except:
                pass
            # Safely remove from dict
            try:
                del self.clients[user_id]
            except KeyError:
                pass

    async def _sending_loop(self, user_id: int):
        """Main sending loop with safe retry logic"""
        retry_count = 0
        client = None

        try:
            while True:
                # Check if user is still active and not banned
                user = await self.db.get_user(user_id)
                if not user or user['is_active'] == 0 or user['is_banned'] == 1:
                    break

                # Check subscription
                has_subscription = await self.db.check_subscription(user_id)
                if not has_subscription:
                    # Subscription expired, stop sending
                    await self.db.update_user_active_status(user_id, 0)
                    break

                # Get profile, message and user's selected groups
                profile = await self.db.get_profile(user_id)
                message = await self.db.get_message(user_id)
                user_groups = await self.db.get_user_groups(user_id)

                if not profile or not message or not user_groups:
                    break

                try:
                    # Get or create client (reuse existing client to reduce traffic)
                    if not client or not client.is_connected():
                        client = await self.create_client(user_id, profile['session'])

                    # Send message to all selected groups
                    for group_id in user_groups:
                        try:
                            # Use group_id directly (dialog.id is already in correct format)
                            await client.send_message(group_id, message['text'])
                            # Small delay between groups to avoid flood
                            await asyncio.sleep(random.uniform(2, 5))
                        except FloodWaitError as e:
                            # Handle flood wait for individual group
                            await asyncio.sleep(e.seconds + random.randint(5, 15))
                        except Exception as e:
                            # Continue to next group if one fails
                            # Log error silently
                            pass

                    # Reset retry count on success
                    retry_count = 0

                    # Random interval between 5-6 minutes
                    interval = random.randint(
                        DEFAULT_RANDOM_INTERVAL_MIN,
                        DEFAULT_RANDOM_INTERVAL_MAX
                    )
                    await asyncio.sleep(interval)

                except FloodWaitError as e:
                    # Respect FloodWait + add buffer
                    wait_time = e.seconds + random.randint(5, 15)
                    await asyncio.sleep(wait_time)

                except Exception as e:
                    # Exponential backoff for other errors
                    retry_count += 1
                    if retry_count >= MAX_RETRY_ATTEMPTS:
                        # Too many failures, stop sending
                        await self.db.update_user_active_status(user_id, 0)
                        break

                    delay = min(BASE_RETRY_DELAY * (2 ** retry_count), MAX_RETRY_DELAY)
                    delay += random.uniform(0, 5)
                    await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass
        except Exception:
            # Silent failure, mark inactive
            await self.db.update_user_active_status(user_id, 0)
        finally:
            # Cleanup
            if client and client.is_connected():
                try:
                    await client.disconnect()
                except:
                    pass

            if user_id in self.clients:
                try:
                    del self.clients[user_id]
                except KeyError:
                    pass

            if user_id in self.active_tasks:
                try:
                    del self.active_tasks[user_id]
                except KeyError:
                    pass

    async def restore_active_tasks(self):
        """Restore sending tasks after restart"""
        active_users = await self.db.get_active_users()

        for user in active_users:
            user_id = user['user_id']

            # Check subscription first
            has_subscription = await self.db.check_subscription(user_id)
            if not has_subscription:
                await self.db.update_user_active_status(user_id, 0)
                continue

            # Verify user has profile, message and selected groups
            profile = await self.db.get_profile(user_id)
            message = await self.db.get_message(user_id)
            user_groups = await self.db.get_user_groups(user_id)

            if profile and message and user_groups:
                await self.start_sending(user_id)
            else:
                # Incomplete setup, mark inactive
                await self.db.update_user_active_status(user_id, 0)

        # Start subscription checker task
        if not self.subscription_checker_task:
            self.subscription_checker_task = asyncio.create_task(self._subscription_checker_loop())

    async def _subscription_checker_loop(self):
        """Background task to check and stop expired subscriptions"""
        try:
            while True:
                try:
                    # Check every 5 minutes
                    await asyncio.sleep(300)

                    # Get expired subscriptions
                    expired_users = await self.db.get_expired_subscriptions()

                    for user_id in expired_users:
                        # Stop sending for expired user
                        await self.stop_sending(user_id)

                except Exception as e:
                    # Log error but continue checking
                    pass

        except asyncio.CancelledError:
            pass

    async def stop_subscription_checker(self):
        """Stop subscription checker task"""
        if self.subscription_checker_task and not self.subscription_checker_task.done():
            self.subscription_checker_task.cancel()
            try:
                await self.subscription_checker_task
            except asyncio.CancelledError:
                pass

    async def cleanup_profile(self, user_id: int):
        """Cleanup profile and stop sending"""
        await self.stop_sending(user_id)
        await self.db.delete_profile(user_id)
        await self.db.delete_message(user_id)
        await self.db.update_user_login_status(user_id, 0)