"""
Dispatcher Worker Package - HTTP REST + SSE Implementation
HTTP-based worker node for distributed job execution
"""

__version__ = "2.5.7"
__author__ = "Dispatcher Team"
__description__ = "Dispatcher Worker - HTTP REST + Redis Logging"

from .cli import main as cli_main
from .server import run_server

__all__ = ["cli_main", "run_server"]