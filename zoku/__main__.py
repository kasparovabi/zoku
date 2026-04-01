"""Allow running Zoku as ``python -m zoku``."""

import sys
from .cli import main

sys.exit(main())
