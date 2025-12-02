"""Migration script to add missing columns to users table.

Run this script once to add new columns to an existing database.
Safe to run multiple times - it will skip columns that already exist.

Usage:
    python -m bot.migrations.add_streak_columns
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add bot directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.database import get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# New columns to add to the users table
NEW_COLUMNS = [
    # Streak columns
    ("daily_streak", "INTEGER DEFAULT 0 NOT NULL"),
    ("daily_streak_best", "INTEGER DEFAULT 0 NOT NULL"),
    ("hourly_streak", "INTEGER DEFAULT 0 NOT NULL"),
    ("hourly_streak_best", "INTEGER DEFAULT 0 NOT NULL"),
    # XP/Level columns (may have been missing)
    ("experience_points", "INTEGER DEFAULT 0 NOT NULL"),
    ("level", "INTEGER DEFAULT 1 NOT NULL"),
]


async def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table (SQLite)."""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = result.fetchall()
    return any(col[1] == column for col in columns)


async def run_migration():
    """Add streak columns to the users table."""
    engine = get_engine()
    
    async with engine.begin() as conn:
        logger.info("Starting streak columns migration...")
        
        for column_name, column_def in NEW_COLUMNS:
            exists = await column_exists(conn, "users", column_name)
            
            if exists:
                logger.info(f"Column '{column_name}' already exists, skipping...")
                continue
            
            logger.info(f"Adding column '{column_name}'...")
            await conn.execute(
                text(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
            )
            logger.info(f"Column '{column_name}' added successfully!")
        
        logger.info("Migration completed successfully!")


def main():
    """Entry point for the migration script."""
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()

