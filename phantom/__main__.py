"""Allow running Phantom Agent as ``python -m phantom``."""

import sys
from .cli import main

sys.exit(main())
