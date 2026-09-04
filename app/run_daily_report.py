"""Combined daily report: strict value candidates + draw-pattern candidates."""
from pathlib import Path
import subprocess
import sys

APP_DIR = Path(__file__).resolve().parent

for script in ("run_quality_verified_analysis.py", "run_draw_analysis.py"):
    print("\n" + "=" * 70)
    print(script)
    print("=" * 70)
    subprocess.run([sys.executable, str(APP_DIR / script)], check=False)
