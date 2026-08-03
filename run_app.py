"""개발/동결 공용 런처. 개발: .venv/bin/python run_app.py [pdf]"""
import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
