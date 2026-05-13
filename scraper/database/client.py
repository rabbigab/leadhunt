import logging
from datetime import datetime, timezone
from typing import List, Optional

from supabase import create_client, Client

from scraper.config.settings import settings
from scraper.facebook.post_parser import FBPost
from scraper.detection.keyword_engine import MatchResult

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        self._client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )

    def get_keyword_categories(self) -> List[dict]:
        response = self._client.table("keyword_categories").select("*").eq("is_active", True).execute()
        return response.data or []

    def get_recent_post_ids(self, limit: int = 5000) -> List[str]:
        """Charge les post_ids récents pour initialiser le déduplicateur."""
        response = (
            self._client.table("detected_leads")
            .select("fb_post_id")
            .order("detected_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [row["fb_post_id"] for row in (response.data or [])]

    def post_id_exists(self, fb_post_id: str) -> bool:
        response = (
            self._client.table("detected_leads")
            .select("id")
            .eq("fb_post_id", fb_post_id)
            .execute()
        )
        return len(response.data or []) > 0

    def save_lead(self, post: FBPost, match: MatchResult) -> Optional[str]:
        try:
            row = {
                "fb_post_id": post.fb_post_id,
                "group_id": post.group_id,
                "group_name": post.group_name,
                "author_name": post.author_name,
                "post_content": post.content,
                "post_url": post.post_url,
                "matched_keywords": match.keywords_found,
                "matched_category": match.category,
                "confidence": match.confidence,
            }
            response = self._client.table("detected_leads").insert(row).execute()
            if response.data:
                lead_id = response.data[0]["id"]
                logger.info(f"Lead sauvegardé : {post.fb_post_id} ({match.category})")
                return lead_id
        except Exception as e:
            logger.error(f"Erreur sauvegarde lead {post.fb_post_id} : {e}")
        return None

    def mark_notified(self, fb_post_id: str) -> None:
        try:
            self._client.table("detected_leads").update(
                {"notified": True, "notified_at": datetime.now(timezone.utc).isoformat()}
            ).eq("fb_post_id", fb_post_id).execute()
        except Exception as e:
            logger.error(f"Erreur mark_notified {fb_post_id} : {e}")

    def update_group_last_scraped(self, fb_group_id: str, posts_found_delta: int = 0) -> None:
        try:
            self._client.table("monitored_groups").update(
                {
                    "last_scraped_at": datetime.now(timezone.utc).isoformat(),
                    "posts_found": self._client.rpc(
                        "increment", {"table": "monitored_groups", "column": "posts_found", "amount": posts_found_delta}
                    ),
                }
            ).eq("fb_group_id", fb_group_id).execute()
        except Exception:
            pass  # non critique

    def save_scrape_session(self, groups_scraped: int, posts_checked: int, leads_found: int, errors: List[str]) -> None:
        try:
            self._client.table("scrape_sessions").insert(
                {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "groups_scraped": groups_scraped,
                    "posts_checked": posts_checked,
                    "leads_found": leads_found,
                    "errors": errors,
                }
            ).execute()
        except Exception as e:
            logger.warning(f"Erreur sauvegarde session scraping : {e}")
