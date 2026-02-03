"""
Riko - The Ruyi Packaging Bot

A three-tier architecture package for automated package manifest generation and management.

Architecture:
- core: Business logic and data models
- services: Business service orchestration
- interfaces: CLI and API interfaces

Main exports:
- get_riko: Get the Riko singleton instance
- Riko: Core business class
- RikoPkg: Package data model
"""

from .core import Riko, get_riko, RikoPkg

__all__ = ["Riko", "get_riko", "RikoPkg"]
