"""Allow running HarnessKit as ``python -m harnesskit``."""

import sys

from .cli import main

sys.exit(main())
