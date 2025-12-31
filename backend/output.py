import logging
from datetime import datetime

# Logging configuration dict for uvicorn
log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "access": {
            "format": "[%(asctime)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout"
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout"
        }
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        },
        "uvicorn.error": {
            "level": "INFO"
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False
        }
    }
}

class Output:
    def __init__(self, logger_name="uvicorn"):
        self.logger = logging.getLogger(logger_name)
        
    def _format_message(self, message):
        """Just return the message - timestamp formatting is handled by logging config"""
        return message
    
    def debug(self, message):
        """Log debug level message"""
        self.logger.debug(self._format_message(message))
        
    def info(self, message):
        """Log info level message"""
        self.logger.info(self._format_message(message))
        
    def warning(self, message):
        """Log warning level message"""
        self.logger.warning(self._format_message(message))
        
    def error(self, message):
        """Log error level message"""
        self.logger.error(self._format_message(message))
        
    def critical(self, message):
        """Log critical level message"""
        self.logger.critical(self._format_message(message))

# Standard output for application logging
output = Output("uvicorn")
