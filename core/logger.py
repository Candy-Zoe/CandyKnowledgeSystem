"""
Candy 日志系统
按日期生成日志文件，记录所有操作
"""
import os
import logging
from datetime import datetime
from pathlib import Path


def setup_logger(name="candy", log_dir=None):
    """
    配置日志系统
    
    Args:
        name: 日志器名称
        log_dir: 日志目录，默认为项目根目录/logs
        
    Returns:
        logger实例
    """
    if log_dir is None:
        log_dir = Path(__file__).parent.parent / "logs"
    
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 按日期生成文件名
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"{today}.txt"
    
    # 创建日志器
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # 文件handler - 记录所有级别
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    
    # 控制台handler - 只记录INFO及以上
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"日志系统初始化完成，日志文件: {log_file}")
    
    return logger


# 全局日志器
log = setup_logger()


class LogCapture:
    """
    捕获并记录异常的上下文管理器
    """
    
    def __init__(self, operation_name, logger=None):
        self.operation = operation_name
        self.logger = logger or log
    
    def __enter__(self):
        self.logger.info(f"开始: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.logger.info(f"完成: {self.operation}")
        else:
            self.logger.error(f"失败: {self.operation} - {exc_type.__name__}: {exc_val}")
        return False  # 不抑制异常


def log_operation(func):
    """
    装饰器：自动记录函数调用
    """
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        log.info(f"调用: {func_name}(args={args[:2]}, kwargs={list(kwargs.keys())})")
        try:
            result = func(*args, **kwargs)
            log.info(f"成功: {func_name}")
            return result
        except Exception as e:
            log.error(f"异常: {func_name} - {type(e).__name__}: {e}")
            raise
    return wrapper
