import json
import os
import datetime
import asyncio
import logging
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

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
                # Convert dict to BotUser
                user_data['role'] = UserRole(user_data.get('role', 'user'))
                if user_data.get('subscription_expiry'):
                    user_data['subscription_expiry'] = datetime.datetime.fromisoformat(user_data['subscription_expiry'])
                if user_data.get('created_at'):
                    user_data['created_at'] = datetime.datetime.fromisoformat(user_data['created_at'])
                user = BotUser(**user_data)
            else:
                user = user_data
            return user
        return None
    
    async def create_user(self, user_id: int, username: str = "", first_name: str = "", owner_id: int = None) -> BotUser:
        """Create new user"""
        from src.config import OWNER_ID
        user = BotUser(
            user_id=user_id,
            username=username,
            first_name=first_name,
            role=UserRole.OWNER if user_id == (owner_id or OWNER_ID) else UserRole.USER
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
        users = {}
        for k, v in self.data["users"].items():
            if isinstance(v, dict):
                v['role'] = UserRole(v.get('role', 'user'))
                if v.get('subscription_expiry'):
                    v['subscription_expiry'] = datetime.datetime.fromisoformat(v['subscription_expiry'])
                if v.get('created_at'):
                    v['created_at'] = datetime.datetime.fromisoformat(v['created_at'])
                users[int(k)] = BotUser(**v)
            else:
                users[int(k)] = v
        return users
