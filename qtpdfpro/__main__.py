"""Điểm vào khi chạy `python -m qtpdfpro`."""

import sys
from qtpdfpro.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
