"""
AuraBot — Music Extractor
"""

from __future__ import annotations

from typing import Optional

from database.models import Track


class Extractor:

    async def resolve(
        self,
        query: str,
        user_id: int = 0
    ) -> Optional[Track]:

        return Track(
            track_id="dummy",
            title=query,
            artist="Unknown",
            url=query,
            source="youtube",
            duration=0,
            added_by=user_id,
            is_live=False,
        )


extractor = Extractor()
