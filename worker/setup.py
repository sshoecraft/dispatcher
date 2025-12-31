#!/usr/bin/env python3
"""
Setup script for Dispatcher Worker package - HTTP REST + SSE Implementation
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read version from __init__.py
version_file = Path(__file__).parent / "worker_node" / "__init__.py"
version = {}
with open(version_file) as f:
    # Only execute the lines we need for version info, avoid imports
    lines = f.readlines()
    version_lines = []
    for line in lines:
        if line.strip().startswith('__version__') or line.strip().startswith('__author__') or line.strip().startswith('__description__'):
            version_lines.append(line)
    exec('\n'.join(version_lines), version)

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    with open(readme_file, encoding="utf-8") as f:
        long_description = f.read()

setup(
    name="dispatcher-worker",
    version=version["__version__"],
    author=version["__author__"],
    description=version["__description__"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    py_modules=['dispatcher_worker'],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "psutil>=5.9.0",
        "requests>=2.28.0",
        "aiofiles>=23.2.0",
        "starlette>=0.27.0",
        "httpx>=0.25.0",
        "redis>=5.0.0",
        "websockets>=11.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "dispatcher-worker=dispatcher_worker:main",
            "dispatcher-worker-core=worker_node.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators", 
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Systems Administration",
    ],
    keywords="distributed worker http rest sse orchestrator automation",
    include_package_data=True,
    zip_safe=False,
)