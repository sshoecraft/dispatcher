#!/usr/bin/env python3
"""
Worker Node CLI Interface
Command line interface for starting worker node HTTP server
"""

import argparse
import sys
import socket
from .server import run_server
from .output import output
from . import __version__
from .args import get_worker_name, get_backend_url_from_args, get_port_from_args, get_max_jobs_from_args


def check_port_available(host: str, port: int) -> bool:
    """Check if port is available for binding"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Dispatcher Worker Node - HTTP REST command executor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  dispatcher-worker --backend-url https://orchestrator.example.com:8443 --worker-name worker1 --port 8501
  dispatcher-worker --backend-url http://localhost:8000 --worker-name local-worker --port 8500 --max-jobs 5
        """
    )
    
    parser.add_argument(
        "--backend-url",
        required=True,
        help="Backend orchestrator URL (required)"
    )
    
    parser.add_argument(
        "--worker-name", 
        required=True,
        help="Worker name/identifier (required)"
    )
    
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="HTTP server bind address (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="HTTP server port (required)"
    )
    
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=10,
        help="Maximum concurrent jobs (default: 10)"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"Dispatcher Worker Node v{__version__} (use configured backend URL)"
    )
    
    args = parser.parse_args()
    
    # Validate backend URL
    if not args.backend_url.startswith(('http://', 'https://')):
        output.error("Backend URL must start with http:// or https://")
        sys.exit(1)
    
    # Check if port is available
    if not check_port_available(args.host, args.port):
        output.error(f"Port {args.port} is not available on {args.host}")
        sys.exit(1)
    
    # Validate max_jobs
    if args.max_jobs < 1:
        output.error("max-jobs must be at least 1")
        sys.exit(1)
    
    output.info(f"Starting worker node '{args.worker_name}'")
    output.info(f"  Backend URL: {args.backend_url}")
    output.info(f"  Listening on: {args.host}:{args.port}")
    output.info(f"  Max concurrent jobs: {args.max_jobs}")
    
    try:
        # Start the worker node server
        run_server(
            backend_url=args.backend_url,
            worker_name=args.worker_name,
            host=args.host,
            port=args.port,
            max_jobs=args.max_jobs
        )
    except KeyboardInterrupt:
        output.info("Shutting down worker node...")
        sys.exit(0)
    except Exception as e:
        output.error(f"Error starting worker node: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()