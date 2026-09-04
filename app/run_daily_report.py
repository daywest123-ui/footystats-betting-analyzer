"""Combined daily report: strict value candidates + draw-pattern candidates."""
import subprocess,sys
for script in ("run_quality_verified_analysis.py","run_draw_analysis.py"):
    print("\n"+"="*70); print(script); print("="*70)
    subprocess.run([sys.executable,script],check=False)
