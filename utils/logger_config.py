"""
Structured logging configuration for the distributed chat system
"""
import logging
import sys
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and structured output"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    # Component prefixes
    COMPONENT_ICONS = {
        'raft_server': '⚙️ ',
        'app_server': '💬',
        'chat_client': '👤',
        'llm_server': '🤖'
    }
    
    def format(self, record):
        # Add color
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Get component icon
        component = record.name.split('.')[-1]
        icon = self.COMPONENT_ICONS.get(component, '📋')
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Build formatted message
        if record.levelno >= logging.WARNING:
            # Warnings and errors get more visibility
            formatted = f"{color}[{timestamp}] {icon} {record.levelname}{reset}: {record.getMessage()}"
        elif record.levelno == logging.INFO:
            # Info messages are clean
            formatted = f"[{timestamp}] {icon} {record.getMessage()}"
        else:
            # Debug messages are minimal
            formatted = f"{color}[{timestamp}] {record.name}: {record.getMessage()}{reset}"
        
        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


def setup_logging(component: str, level: str = "INFO", log_file: Optional[str] = None):
    """
    Setup structured logging for a component
    
    Args:
        component: Component name (e.g., 'raft_server', 'app_server')
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file to write logs to
    """
    logger = logging.getLogger(component)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    # Optional file handler (no colors)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger for a specific module"""
    return logging.getLogger(name)


# Performance logging helper
class PerformanceLogger:
    """Helper class for logging performance metrics"""
    
    def __init__(self, logger: logging.Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"⏱️  Starting: {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type:
            self.logger.warning(f"❌ Failed: {self.operation} ({duration:.3f}s)")
        elif duration > 1.0:
            self.logger.warning(f"🐌 Slow: {self.operation} ({duration:.3f}s)")
        else:
            self.logger.debug(f"✓ Completed: {self.operation} ({duration:.3f}s)")
