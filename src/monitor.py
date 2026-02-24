import httpx
import logging
from typing import Tuple, Dict, Any
from src.config import USER_AGENT
from src.database import AccountStatus

logger = logging.getLogger(__name__)

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
                
                # Try Instagram API
                response = await client.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and "user" in data["data"]:
                        user_data = data["data"]["user"]
                        
                        # Check if account is active
                        if user_data.get("is_private") is not None:
                            # Get follower count safely
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
                
                # If account not found or error
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
