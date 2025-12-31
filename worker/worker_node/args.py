#!/usr/bin/env python3
"""
Shared command-line argument parsing utilities for Dispatcher worker components.
Used by both the wrapper and core worker processes.
"""

import sys
import os
from typing import Optional


def get_worker_name() -> str:
    """Extract worker name from command line arguments or environment"""
    # Try to get from command line arguments (--worker-name)
    for i, arg in enumerate(sys.argv):
        if arg == '--worker-name' and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith('--worker-name='):
            return arg.split('=', 1)[1]
    
    # Try environment variable
    worker_name = os.getenv('WORKER_NAME')
    if worker_name:
        return worker_name
    
    # Default fallback
    return 'Unknown'


def get_backend_url_from_args() -> str:
    """Extract backend URL from command line arguments"""
    # Try to get from command line arguments (--backend-url)
    for i, arg in enumerate(sys.argv):
        if arg == '--backend-url' and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith('--backend-url='):
            return arg.split('=', 1)[1]
    
    # Default fallback
    return 'http://localhost:8000'


def get_port_from_args() -> Optional[int]:
    """Extract port from command line arguments"""
    # Try to get from command line arguments (--port)
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                return None
        if arg.startswith('--port='):
            try:
                return int(arg.split('=', 1)[1])
            except ValueError:
                return None
    
    return None


def get_max_jobs_from_args() -> Optional[int]:
    """Extract max jobs from command line arguments"""
    # Try to get from command line arguments (--max-jobs)
    for i, arg in enumerate(sys.argv):
        if arg == '--max-jobs' and i + 1 < len(sys.argv):
            try:
                return int(sys.argv[i + 1])
            except ValueError:
                return None
        if arg.startswith('--max-jobs='):
            try:
                return int(arg.split('=', 1)[1])
            except ValueError:
                return None
    
    return None


def get_debug_from_args() -> bool:
    """Check if --debug flag is present"""
    return '--debug' in sys.argv