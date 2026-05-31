"""Allow `python -m glyph` to invoke the CLI."""
from .cli import main
raise SystemExit(main())
