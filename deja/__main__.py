"""Allow running Deja as ``python -m deja``."""

import sys
from .cli import main

sys.exit(main())
