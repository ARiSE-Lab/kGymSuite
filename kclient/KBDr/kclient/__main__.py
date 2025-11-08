"""KBDr-Runner Client Interactive Shell.

This module provides an interactive IPython-based shell for working with the KBDr-Runner
client library. It automatically imports all kclient components and launches an async-enabled
IPython session for interactive exploration and debugging.

The shell is pre-configured with:
    - All kclient classes and functions imported
    - Asyncio support enabled
    - Common utilities (os, json, sys, asyncio, Path) imported
    - Pydantic models and serialization helpers available

Usage:
    python -m KBDr.kclient

    This will drop you into an IPython shell where you can interactively work with
    the kGymClient and other components.

Example Session:
    $ python -m KBDr.kclient
    In [1]: client = kGymAsyncClient("http://localhost:8000")
    In [2]: jobs = await client.get_jobs()
"""

import os, json, sys, asyncio
from KBDr.kclient import *
from pathlib import Path
from pydantic import BaseModel, RootModel
from pydantic_core import to_json, from_json
from IPython import embed

def main_cli():
    embed(using='asyncio')

if __name__ == '__main__':
    main_cli()
