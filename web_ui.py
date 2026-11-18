"""Launcher for Samia Web UI."""

import os
import subprocess
import sys


def run_web_ui() -> None:
    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path] + sys.argv[1:])


if __name__ == "__main__":
    run_web_ui()
