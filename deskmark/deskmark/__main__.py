"""``python -m deskmark``, for when the console script isn't on PATH yet."""
from deskmark.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
