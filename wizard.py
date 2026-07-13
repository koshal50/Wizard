#!/usr/bin/env python3
"""Wizard CLI — Convenience entry script.

Usage:
    python wizard.py analyze .
    python wizard.py dependency-insights .
"""

from wizard.cli.app import main

if __name__ == "__main__":
    main()
