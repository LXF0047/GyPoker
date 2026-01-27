# _*_ coding: utf-8 _*_
# @Time : 2026/1/23 15:00
# @Author : lxf
# @Version：V 0.1
# @File : system_utils.py
# @desc : System configuration and utilities

import pysqlite3 as sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta, time as dt_time
from typing import Optional
from .base import get_db_connection


def get_api_key(service_name: str) -> Optional[str]:
    """Get API Key for a service."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.execute("SELECT api_key FROM api_keys WHERE service_name = ?", (service_name,))
        result = cursor.fetchone()
        return result['api_key'] if result else None
    except sqlite3.Error as e:
        logging.error(f"Error getting api key for {service_name}: {e}")
        return None
    finally:
        conn.close()


def daily_settlement_task():
    """
    Daily settlement task.
    In the new system, stats are updated in real-time.
    This task is kept for maintenance or future daily logic (e.g. archiving).
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting daily settlement task...")
        print("Starting daily settlement task...")

        # Here we could add logic to archive old data or reset chips if needed.
        # For now, since stats are live, we just log.
        
        logger.info("Daily settlement task completed (Stats are real-time).")
        print("Daily settlement task completed.")

    except Exception as e:
        logger.error(f"Daily settlement task failed: {e}")
        print(f"Daily settlement task failed: {e}")


def start_daily_settlement_scheduler():
    """Start the daily settlement scheduler in a background thread."""
    
    logger = logging.getLogger(__name__)
    
    def run_scheduler():
        logger.info("Daily settlement scheduler thread started")
        
        while True:
            try:
                now = datetime.now()
                # Target: 01:00:00
                target_time = dt_time(1, 0, 0)
                
                if now.time() < target_time:
                    target_datetime = now.replace(hour=1, minute=0, second=0, microsecond=0)
                else:
                    target_datetime = (now + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)
                
                wait_seconds = (target_datetime - now).total_seconds()
                logger.info(f"Next settlement at: {target_datetime}, waiting {wait_seconds/3600:.1f} hours")
                
                while wait_seconds > 0:
                    sleep_time = min(3600, wait_seconds)
                    time.sleep(sleep_time)
                    wait_seconds -= sleep_time
                    
                    now = datetime.now()
                    if now.time() >= target_time and now.date() == target_datetime.date():
                        break
                
                logger.info("Executing daily settlement task...")
                daily_settlement_task()
                logger.info("Daily settlement task finished")
                
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                time.sleep(300)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True) # daemon=True usually better so it doesn't block exit
    scheduler_thread.start()
    logger.info("Daily settlement scheduler started")

