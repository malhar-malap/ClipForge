"""ClipForge. This file runs first, before any other part of ClipForge, so it can stop early with a clear message.
Keep it simple enough for old Python versions to read, or they fail before they can show the message."""
import sys

if sys.version_info < (3, 10):
    sys.exit("\n  ClipForge needs Python 3.10 or newer. This is Python %d.%d (%s).\n"
             "  Install a newer Python (python.org, or: brew install python@3.12 / sudo apt install python3.12),\n"
             "  then make the project's environment with it:  python3.12 -m venv .venv\n"
             % (sys.version_info[0], sys.version_info[1], sys.executable))
