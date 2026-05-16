from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema, transaction


def main() -> None:
    run_schema()

    with transaction() as conn:
        duplicate_insights = conn.execute(
            """
            WITH ranked AS (
              SELECT
                id,
                row_number() OVER (
                  PARTITION BY target_type, target_id, insight
                  ORDER BY id
                ) AS rank
              FROM user_insights
            )
            DELETE FROM user_insights
            WHERE id IN (SELECT id FROM ranked WHERE rank > 1)
            RETURNING id
            """
        ).fetchall()

        conn.execute(
            """
            WITH grouped AS (
              SELECT
                min(id) AS keep_id,
                target_type,
                target_id,
                knowledge_type,
                content,
                bool_or(confirmed_by_user) AS confirmed_by_user,
                max(confidence) AS confidence,
                min(source_id) AS source_id,
                min(stale_after) AS stale_after
              FROM knowledge_items
              GROUP BY target_type, target_id, knowledge_type, content
              HAVING count(*) > 1
            )
            UPDATE knowledge_items k SET
              confirmed_by_user = grouped.confirmed_by_user,
              confidence = grouped.confidence,
              source_id = COALESCE(k.source_id, grouped.source_id),
              stale_after = COALESCE(k.stale_after, grouped.stale_after),
              updated_at = now()
            FROM grouped
            WHERE k.id = grouped.keep_id
            """
        )
        duplicate_knowledge = conn.execute(
            """
            WITH ranked AS (
              SELECT
                id,
                row_number() OVER (
                  PARTITION BY target_type, target_id, knowledge_type, content
                  ORDER BY id
                ) AS rank
              FROM knowledge_items
            )
            DELETE FROM knowledge_items
            WHERE id IN (SELECT id FROM ranked WHERE rank > 1)
            RETURNING id
            """
        ).fetchall()

        conn.execute(
            """
            WITH canonical AS (
              SELECT url, min(id) AS keep_id
              FROM sources
              WHERE url IS NOT NULL AND url <> ''
              GROUP BY url
              HAVING count(*) > 1
            )
            UPDATE stock_sector_relations r SET source_id = canonical.keep_id
            FROM sources s
            JOIN canonical ON canonical.url = s.url
            WHERE r.source_id = s.id AND s.id <> canonical.keep_id
            """
        )
        conn.execute(
            """
            WITH canonical AS (
              SELECT url, min(id) AS keep_id
              FROM sources
              WHERE url IS NOT NULL AND url <> ''
              GROUP BY url
              HAVING count(*) > 1
            )
            UPDATE knowledge_items k SET source_id = canonical.keep_id
            FROM sources s
            JOIN canonical ON canonical.url = s.url
            WHERE k.source_id = s.id AND s.id <> canonical.keep_id
            """
        )
        duplicate_sources = conn.execute(
            """
            WITH canonical AS (
              SELECT url, min(id) AS keep_id
              FROM sources
              WHERE url IS NOT NULL AND url <> ''
              GROUP BY url
              HAVING count(*) > 1
            )
            DELETE FROM sources s
            USING canonical
            WHERE s.url = canonical.url AND s.id <> canonical.keep_id
            RETURNING s.id
            """
        ).fetchall()

        orphan_sources = conn.execute(
            """
            DELETE FROM sources s
            WHERE NOT EXISTS (
              SELECT 1 FROM stock_sector_relations r WHERE r.source_id = s.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM knowledge_items k WHERE k.source_id = s.id
              )
            RETURNING s.id
            """
        ).fetchall()

        orphan_sector_count = 0
        while True:
            orphan_sectors = conn.execute(
                """
                DELETE FROM sectors s
                WHERE NOT EXISTS (
                  SELECT 1 FROM sectors child WHERE child.parent_id = s.id
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM stock_sector_relations r WHERE r.sector_id = s.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM knowledge_items k
                    WHERE k.target_type = 'sector' AND k.target_id = s.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM user_insights ui
                    WHERE ui.target_type = 'sector' AND ui.target_id = s.id
                  )
                RETURNING s.id
                """
            ).fetchall()
            if not orphan_sectors:
                break
            orphan_sector_count += len(orphan_sectors)

    print("Duplicate cleanup completed.")
    print(
        {
            "duplicate_user_insights_deleted": len(duplicate_insights),
            "duplicate_knowledge_items_deleted": len(duplicate_knowledge),
            "duplicate_sources_deleted": len(duplicate_sources),
            "orphan_sources_deleted": len(orphan_sources),
            "orphan_sectors_deleted": orphan_sector_count,
        }
    )


if __name__ == "__main__":
    main()
