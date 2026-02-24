"""
Telegram Username Monitor Bot - Enterprise Grade
Python 3.10/3.11 | python-telegram-bot v20.x
"""

import os
import json
import asyncio
import logging
import datetime
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import traceback
from collections import defaultdict

# Third-party imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode
import httpx
from flask import Flask

# ==================== Configuration ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
DATA_FILE = "data/bot_data.json"
MONITOR_INTERVAL = 300  # 5 minutes in seconds
CONFIRMATION_THRESHOLD = 3  # Triple confirmation required

# Platform detection
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ==================== Data Models ====================
class UserRole(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"

class AccountStatus(Enum):
    ACTIVE = "active"
    BANNED = "banned"
    UNKNOWN = "unknown"

@dataclass
class MonitoredUser:
    username: str
    current_status: AccountStatus = AccountStatus.UNKNOWN
    confirmation_count: int = 0
    last_checked: Optional[datetime.datetime] = None
    last_alert_sent: Optional[datetime.datetime] = None
    profile_details: Dict[str, Any] = None

@dataclass
class BotUser:
    user_id: int
    username: str = ""
    first_name: str = ""
    role: UserRole = UserRole.USER
    subscription_expiry: Optional[datetime.datetime] = None
    watch_list: List[str] = None
    ban_list: List[str] = None
    created_at: datetime.datetime = None
    
    def __post_init__(self):
        if self.watch_list is None:
            self.watch_list = []
        if self.ban_list is None:
            self.ban_list = []
        if self.created_at is None:
            self.created_at = datetime.datetime.now()

# ==================== Database Manager ====================
class DatabaseManager:
    def __init__(self, filename: str):
        self.filename = filename
        self.data = {
            "users": {},
            "monitored_accounts": {}
        }
        self.lock = asyncio.Lock()
        self._ensure_data_dir()
        self.load()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists"""
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
    
    def load(self):
        """Load data from JSON file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r') as f:
                    loaded_data = json.load(f)
                    
                    # Convert string dates back to datetime objects
                    if "users" in loaded_data:
                        for user_id, user_data in loaded_data["users"].items():
                            if "subscription_expiry" in user_data and user_data["subscription_expiry"]:
                                user_data["subscription_expiry"] = datetime.datetime.fromisoformat(user_data["subscription_expiry"])
                            if "created_at" in user_data and user_data["created_at"]:
                                user_data["created_at"] = datetime.datetime.fromisoformat(user_data["created_at"])
                    
                    if "monitored_accounts" in loaded_data:
                        for username, acc_data in loaded_data["monitored_accounts"].items():
                            if "last_checked" in acc_data and acc_data["last_checked"]:
                                acc_data["last_checked"] = datetime.datetime.fromisoformat(acc_data["last_checked"])
                            if "last_alert_sent" in acc_data and acc_data["last_alert_sent"]:
                                acc_data["last_alert_sent"] = datetime.datetime.fromisoformat(acc_data["last_alert_sent"])
                            if "current_status" in acc_data:
                                acc_data["current_status"] = AccountStatus(acc_data["current_status"])
                    
                    self.data = loaded_data
                    
        except Exception as e:
            logger.error(f"Error loading data: {e}")
    
    async def save(self):
        """Save data to JSON file"""
        async with self.lock:
            try:
                # Prepare data for serialization
                save_data = {
                    "users": {},
                    "monitored_accounts": {}
                }
                
                # Convert users
                for user_id, user in self.data["users"].items():
                    user_dict = {
                        "user_id": user.user_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "role": user.role.value,
                        "watch_list": user.watch_list,
                        "ban_list": user.ban_list,
                        "subscription_expiry": user.subscription_expiry.isoformat() if user.subscription_expiry else None,
                        "created_at": user.created_at.isoformat() if user.created_at else None
                    }
                    save_data["users"][user_id] = user_dict
                
                # Convert monitored accounts
                for username, account in self.data["monitored_accounts"].items():
                    account_dict = {
                        "username": account.username,
                        "current_status": account.current_status.value,
                        "confirmation_count": account.confirmation_count,
                        "last_checked": account.last_checked.isoformat() if account.last_checked else None,
                        "last_alert_sent": account.last_alert_sent.isoformat() if account.last_alert_sent else None,
                        "profile_details": account.profile_details
                    }
                    save_data["monitored_accounts"][username] = account_dict
                
                with open(self.filename, 'w') as f:
                    json.dump(save_data, f, indent=2)
                    
            except Exception as e:
                logger.error(f"Error saving data: {e}")
    
    async def get_user(self, user_id: int) -> Optional[BotUser]:
        """Get user by ID"""
        user_data = self.data["users"].get(str(user_id))
        if user_data:
            if isinstance(user_data, dict):
                user = BotUser(**user_data)
            else:
                user = user_data
            return user
        return None
    
    async def create_user(self, user_id: int, username: str = "", first_name: str = "") -> BotUser:
        """Create new user"""
        user = BotUser(
            user_id=user_id,
            username=username,
            first_name=first_name,
            role=UserRole.OWNER if user_id == OWNER_ID else UserRole.USER
        )
        self.data["users"][str(user_id)] = user
        await self.save()
        return user
    
    async def update_user(self, user: BotUser):
        """Update user data"""
        self.data["users"][str(user.user_id)] = user
        await self.save()
    
    async def get_monitored_account(self, username: str) -> MonitoredUser:
        """Get monitored account by username"""
        username = username.lower().strip()
        if username not in self.data["monitored_accounts"]:
            self.data["monitored_accounts"][username] = MonitoredUser(username=username)
        return self.data["monitored_accounts"][username]
    
    async def update_monitored_account(self, account: MonitoredUser):
        """Update monitored account"""
        self.data["monitored_accounts"][account.username] = account
        await self.save()
    
    async def get_all_monitored_accounts(self) -> Dict[str, MonitoredUser]:
        """Get all monitored accounts"""
        return self.data["monitored_accounts"]
    
    async def get_all_users(self) -> Dict[int, BotUser]:
        """Get all users"""
        return {int(k): v for k, v in self.data["users"].items()}

# ==================== Platform Monitor ====================
class InstagramMonitor:
    @staticmethod
    async def check_user(username: str) -> Tuple[AccountStatus, Dict[str, Any]]:
        """
        Check Instagram user status
        Returns: (status, profile_details)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                }
                
                response = await client.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and "user" in data["data"]:
                        user_data = data["data"]["user"]
                        
                        if user_data.get("is_private") is not None:
                            followers = 0
                            following = 0
                            posts = 0
                            
                            if "edge_followed_by" in user_data:
                                followers = user_data["edge_followed_by"].get("count", 0)
                            if "edge_follow" in user_data:
                                following = user_data["edge_follow"].get("count", 0)
                            if "edge_owner_to_timeline_media" in user_data:
                                posts = user_data["edge_owner_to_timeline_media"].get("count", 0)
                            
                            details = {
                                "name": user_data.get("full_name", "N/A"),
                                "followers": followers,
                                "following": following,
                                "posts": posts,
                                "private": user_data.get("is_private", False),
                                "verified": user_data.get("is_verified", False),
                                "business": user_data.get("is_business_account", False),
                                "bio": user_data.get("biography", "N/A")[:100]
                            }
                            return AccountStatus.ACTIVE, details
                
                if response.status_code == 404:
                    return AccountStatus.BANNED, {"error": "Account not found"}
                else:
                    return AccountStatus.UNKNOWN, {"error": f"HTTP {response.status_code}"}
                    
        except httpx.TimeoutException:
            logger.warning(f"Timeout checking {username}")
            return AccountStatus.UNKNOWN, {"error": "Timeout"}
        except Exception as e:
            logger.error(f"Error checking {username}: {e}")
            return AccountStatus.UNKNOWN, {"error": str(e)}

# ==================== Bot Instance ====================
class UsernameMonitorBot:
    def __init__(self, token: str):
        self.token = token
        self.db = DatabaseManager(DATA_FILE)
        self.monitor = InstagramMonitor()
        self.monitoring_task = None
        self.app = None
        self.USER_LIMIT = 20
    
    async def initialize(self):
        """Initialize bot and start monitoring"""
        self.app = Application.builder().token(self.token).build()
        self._register_handlers()
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Bot initialized successfully")
    
    def _register_handlers(self):
        """Register all command and callback handlers"""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("watch", self.cmd_watch))
        self.app.add_handler(CommandHandler("ban", self.cmd_ban))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("approve", self.cmd_approve))
        self.app.add_handler(CommandHandler("addadmin", self.cmd_addadmin))
        self.app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_error_handler(self.error_handler)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors gracefully"""
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ An error occurred. Please try again later."
                )
        except:
            pass
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        db_user = await self.db.get_user(user.id)
        if not db_user:
            db_user = await self.db.create_user(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name or ""
            )
        
        welcome_text = f"""
🚀 **Welcome to Username Monitor Bot** 🚀

👤 **User:** {user.first_name}
🆔 **ID:** `{user.id}`
⭐ **Role:** {db_user.role.value.upper()}

📋 **Your Stats:**
• Watch List: {len(db_user.watch_list)}/{self.USER_LIMIT if db_user.role == UserRole.USER else '∞'}
• Ban List: {len(db_user.ban_list)} usernames
• Subscription: {db_user.subscription_expiry.strftime('%Y-%m-%d') if db_user.subscription_expiry else 'Not Active'}

**Available Commands:**
/watch <username> - Add to watch list
/ban <username> - Add to ban list
/status - View your lists
/approve <user_id> <days> - Approve user (Admin)
/addadmin <user_id> - Add admin (Owner)
/broadcast <message> - Broadcast to users (Admin)
/help - Show help

Powered by @proxyfxc
        """
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add username to watch list"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if not context.args:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Usage: /watch <username>"
            )
            return
        
        username = context.args[0].lower().strip()
        
        db_user = await self.db.get_user(user.id)
        if not db_user:
            db_user = await self.db.create_user(user.id)
        
        if db_user.role == UserRole.USER:
            if not db_user.subscription_expiry or db_user.subscription_expiry < datetime.datetime.now():
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Your subscription has expired. Contact an admin to renew."
                )
                return
            
            if len(db_user.watch_list) >= self.USER_LIMIT:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ You've reached the limit of {self.USER_LIMIT} usernames."
                )
                return
        
        if username in db_user.watch_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{username} is already in your watch list."
            )
            return
        
        db_user.watch_list.append(username)
        await self.db.update_user(db_user)
        await self.db.get_monitored_account(username)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
✅ **Added to Watch List**

📌 **Username:** @{username}
📊 **Status:** Monitoring started
🔍 **Next Check:** In 5 minutes

You'll be notified when status changes.
            """,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add username to ban list"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if not context.args:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Usage: /ban <username>"
            )
            return
        
        username = context.args[0].lower().strip()
        
        db_user = await self.db.get_user(user.id)
        if not db_user:
            db_user = await self.db.create_user(user.id)
        
        if db_user.role == UserRole.USER:
            if not db_user.subscription_expiry or db_user.subscription_expiry < datetime.datetime.now():
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Your subscription has expired. Contact an admin to renew."
                )
                return
        
        if username in db_user.ban_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ @{username} is already in your ban list."
            )
            return
        
        if username in db_user.watch_list:
            db_user.watch_list.remove(username)
        
        db_user.ban_list.append(username)
        await self.db.update_user(db_user)
        await self.db.get_monitored_account(username)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
✅ **Added to Ban List**

📌 **Username:** @{username}
📊 **Status:** Monitoring for unban
🔍 **Next Check:** In 5 minutes

You'll be notified when account becomes active.
            """,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's watch and ban lists"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        db_user = await self.db.get_user(user.id)
        if not db_user:
            db_user = await self.db.create_user(user.id)
        
        status_text = f"""
📊 **Your Monitoring Status**

👤 **User:** {user.first_name}
⭐ **Role:** {db_user.role.value.upper()}
📅 **Expires:** {db_user.subscription_expiry.strftime('%Y-%m-%d') if db_user.subscription_expiry else 'N/A'}

**Watch List** ({len(db_user.watch_list)}/{self.USER_LIMIT if db_user.role == UserRole.USER else '∞'}):
"""
        
        if db_user.watch_list:
            for i, username in enumerate(db_user.watch_list[:10], 1):
                account = await self.db.get_monitored_account(username)
                status_emoji = "🟢" if account.current_status == AccountStatus.ACTIVE else "🔴" if account.current_status == AccountStatus.BANNED else "⚪"
                status_text += f"{i}. {status_emoji} @{username}\n"
            
            if len(db_user.watch_list) > 10:
                status_text += f"... and {len(db_user.watch_list) - 10} more\n"
        else:
            status_text += "• Empty\n"
        
        status_text += "\n**Ban List:**\n"
        if db_user.ban_list:
            for i, username in enumerate(db_user.ban_list[:10], 1):
                account = await self.db.get_monitored_account(username)
                status_emoji = "🔴" if account.current_status == AccountStatus.BANNED else "🟢" if account.current_status == AccountStatus.ACTIVE else "⚪"
                status_text += f"{i}. {status_emoji} @{username}\n"
        else:
            status_text += "• Empty\n"
        
        status_text += "\n_Powered by @proxyfxc_"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=status_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve user subscription (Admin only)"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        db_user = await self.db.get_user(user.id)
        if not db_user or db_user.role not in [UserRole.OWNER, UserRole.ADMIN]:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ This command is for admins only."
            )
            return
        
        if len(context.args) < 2:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Usage: /approve <user_id> <days>"
            )
            return
        
        try:
            target_id = int(context.args[0])
            days = int(context.args[1])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Invalid user ID or days. Please use numbers."
            )
            return
        
        target_user = await self.db.get_user(target_id)
        if not target_user:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ User {target_id} not found. They need to start the bot first."
            )
            return
        
        target_user.subscription_expiry = datetime.datetime.now() + datetime.timedelta(days=days)
        await self.db.update_user(target_user)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
✅ **Subscription Approved**

👤 **User:** {target_id}
📅 **Duration:** {days} days
📆 **Expires:** {target_user.subscription_expiry.strftime('%Y-%m-%d')}

The user has been notified.
            """,
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"""
✅ **Subscription Activated!**

📅 **Expiry Date:** {target_user.subscription_expiry.strftime('%Y-%m-%d')}
📊 **Limit:** {self.USER_LIMIT} usernames

You can now add usernames to monitor.
            """,
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    
    async def cmd_addadmin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add admin (Owner only)"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if user.id != OWNER_ID:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ This command is for the owner only."
            )
            return
        
        if not context.args:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Usage: /addadmin <user_id>"
            )
            return
        
        try:
            target_id = int(context.args[0])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Invalid user ID."
            )
            return
        
        target_user = await self.db.get_user(target_id)
        if not target_user:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ User {target_id} not found."
            )
            return
        
        target_user.role = UserRole.ADMIN
        await self.db.update_user(target_user)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""
✅ **Admin Added Successfully**

👤 **User:** {target_id}
⭐ **New Role:** ADMIN
            """,
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"""
✅ **You've been promoted to ADMIN!**

You now have access to:
• /approve - Approve subscriptions
• /broadcast - Send messages to all users
• Unlimited monitoring limit
            """,
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    
    async def cmd_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users (Admin only)"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        db_user = await self.db.get_user(user.id)
        if not db_user or db_user.role not in [UserRole.OWNER, UserRole.ADMIN]:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ This command is for admins only."
            )
            return
        
        if not context.args:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Usage: /broadcast <message>"
            )
            return
        
        message = " ".join(context.args)
        
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="📤 Broadcasting message..."
        )
        
        all_users = await self.db.get_all_users()
        
        success_count = 0
        fail_count = 0
        
        for uid, user_data in all_users.items():
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"""
📢 **Broadcast Message**

{message}

---
Sent by: @{db_user.username or 'Admin'}
_Powered by @proxyfxc_
                    """,
                    parse_mode=ParseMode.MARKDOWN
                )
                success_count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"Failed to send to {uid}: {e}")
                fail_count += 1
        
        await status_msg.edit_text(
            text=f"""
✅ **Broadcast Complete**

📨 **Sent:** {success_count} users
❌ **Failed:** {fail_count} users
            """,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        chat_id = update.effective_chat.id
        
        help_text = """
📚 **Help & Commands**

**Basic Commands:**
/start - Start the bot
/watch <username> - Add to watch list
/ban <username> - Add to ban list
/status - View your lists
/help - Show this help

**Admin Commands:**
/approve <user_id> <days> - Approve user
/broadcast <message> - Broadcast to all users

**Owner Commands:**
/addadmin <user_id> - Add new admin

**How It Works:**
• Bot checks usernames every 5 minutes
• 3 confirmations required before alerts
• Watch list: Alert when account is BANNED
• Ban list: Alert when account is ACTIVE
• Subscription required for normal users

**Status Indicators:**
🟢 Active / Available
🔴 Banned / Not Found
⚪ Unknown / Checking

_Powered by @proxyfxc_
        """
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        data = query.data.split(':')
        
        if data[0] == "refresh_status":
            await self.cmd_status(update, context)
    
    async def _monitoring_loop(self):
        """Background monitoring loop"""
        logger.info("Starting monitoring loop")
        
        while True:
            try:
                await self._check_all_users()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                logger.error(traceback.format_exc())
            
            await asyncio.sleep(MONITOR_INTERVAL)
    
    async def _check_all_users(self):
        """Check all monitored usernames"""
        logger.info("Running monitoring check...")
        
        monitored_accounts = await self.db.get_all_monitored_accounts()
        all_users = await self.db.get_all_users()
        
        username_to_users = defaultdict(list)
        watch_list_usernames = set()
        ban_list_usernames = set()
        
        for uid, user in all_users.items():
            for username in user.watch_list:
                username_to_users[username].append((uid, "watch"))
                watch_list_usernames.add(username)
            for username in user.ban_list:
                username_to_users[username].append((uid, "ban"))
                ban_list_usernames.add(username)
        
        all_usernames = watch_list_usernames.union(ban_list_usernames)
        
        for username in all_usernames:
            try:
                await self._check_single_username(username, username_to_users[username])
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error checking {username}: {e}")
    
    async def _check_single_username(self, username: str, watching_users: List[Tuple[int, str]]):
        """Check a single username and process alerts"""
        account = await self.db.get_monitored_account(username)
        
        new_status, details = await self.monitor.check_user(username)
        account.last_checked = datetime.datetime.now()
        account.profile_details = details
        
        if new_status != account.current_status:
            account.confirmation_count += 1
            
            if account.confirmation_count >= CONFIRMATION_THRESHOLD:
                await self._trigger_alert(username, account.current_status, new_status, watching_users)
                account.current_status = new_status
                account.confirmation_count = 0
                account.last_alert_sent = datetime.datetime.now()
        else:
            if new_status != account.current_status:
                account.confirmation_count = 0
        
        await self.db.update_monitored_account(account)
    
    async def _trigger_alert(self, username: str, old_status: AccountStatus, new_status: AccountStatus, watching_users: List[Tuple[int, str]]):
        """Send alerts to watching users"""
        logger.info(f"Alert triggered for @{username}: {old_status.value} -> {new_status.value}")
        
        account = await self.db.get_monitored_account(username)
        details = account.profile_details or {}
        
        if new_status == AccountStatus.BANNED:
            alert_type = "BANNED"
            emoji = "🔴"
            
            for uid, list_type in watching_users:
                if list_type == "watch":
                    user = await self.db.get_user(uid)
                    if user and username in user.watch_list:
                        user.watch_list.remove(username)
                        if username not in user.ban_list:
                            user.ban_list.append(username)
                        await self.db.update_user(user)
        
        elif new_status == AccountStatus.ACTIVE:
            alert_type = "UNBANNED"
            emoji = "🟢"
            
            for uid, list_type in watching_users:
                if list_type == "ban":
                    user = await self.db.get_user(uid)
                    if user and username in user.ban_list:
                        user.ban_list.remove(username)
                        if username not in user.watch_list:
                            user.watch_list.append(username)
                        await self.db.update_user(user)
        else:
            return
        
        alert_text = f"""
{emoji} **ACCOUNT STATUS CHANGE** {emoji}

**Username:** @{username}
**Status:** {alert_type}

📊 **Profile Details:**
👤 **Name:** {details.get('name', 'N/A')}
👥 **Followers:** {details.get('followers', 0):,}
👤 **Following:** {details.get('following', 0):,}
📸 **Posts:** {details.get('posts', 0)}
🔐 **Private:** {'Yes' if details.get('private') else 'No'}
{'✅ **Verified**' if details.get('verified') else ''}

_Powered by @proxyfxc_
        """
        
        for uid, _ in watching_users:
            try:
                await self.app.bot.send_message(
                    chat_id=uid,
                    text=alert_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Failed to send alert to {uid}: {e}")

# ==================== Flask Keep-Alive Server ====================
app = Flask(__name__)
bot_instance = None

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    """Run Flask server"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==================== Main Entry Point ====================
async def main():
    """Main async function"""
    global bot_instance
    
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Please set BOT_TOKEN environment variable")
        return
    
    try:
        # Initialize bot
        bot_instance = UsernameMonitorBot(BOT_TOKEN)
        
        # Initialize application properly
        bot_instance.app = Application.builder().token(BOT_TOKEN).build()
        bot_instance._register_handlers()
        
        # Start monitoring task
        bot_instance.monitoring_task = asyncio.create_task(bot_instance._monitoring_loop())
        
        # Start polling
        await bot_instance.app.initialize()
        await bot_instance.app.start()
        
        # Start polling without Updater
        await bot_instance.app.updater.start_polling()
        
        logger.info("Bot started successfully!")
        
        # Keep running
        while True:
            await asyncio.sleep(60)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        logger.error(traceback.format_exc())

def run_bot():
    """Run bot in asyncio event loop"""
    try:
        asyncio.run(main())
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        # If event loop is already running
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            time.sleep(5)  # Wait and retry

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run bot with retry
    while True:
        try:
            run_bot()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            logger.error(traceback.format_exc())
            time.sleep(10)  # Wait 10 seconds before restarting
