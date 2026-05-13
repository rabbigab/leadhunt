import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FBPost:
    fb_post_id: str
    group_id: str
    group_name: str
    author_name: str
    content: str
    post_url: str
    published_at: Optional[datetime] = None
    raw_html: str = field(default="", repr=False)


def extract_post_id_from_url(url: str) -> Optional[str]:
    patterns = [
        r"/posts/(\d+)",
        r"story_fbid=(\d+)",
        r"/permalink/(\d+)",
        r"pfbid([A-Za-z0-9]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()
