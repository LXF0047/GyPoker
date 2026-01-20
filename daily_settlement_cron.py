#!/usr/bin/env python3
"""
独立的每日结算脚本，用于crontab调度
用法: 
1. 添加到crontab: 0 1 * * * /path/to/python3 /path/to/daily_settlement_cron.py
2. 或者手动执行: python3 daily_settlement_cron.py
"""

import os
import sys
import logging
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from poker.database import daily_settlement_task

def setup_logging():
    """设置日志配置"""
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'daily_settlement.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

def main():
    """主函数"""
    logger = setup_logging()
    
    try:
        logger.info("=" * 50)
        logger.info(f"开始执行每日结算任务 - {datetime.now()}")
        logger.info("=" * 50)
        
        # 执行每日结算任务
        daily_settlement_task()
        
        logger.info("=" * 50)
        logger.info(f"每日结算任务完成 - {datetime.now()}")
        logger.info("=" * 50)
        
        return 0
        
    except Exception as e:
        logger.error(f"每日结算任务执行失败: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)