#!/usr/bin/env python3
"""Run local code tests only. A pass is NOT native PostgreSQL acceptance."""
import os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root)
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','server/tests','server/tests_v71',
                                 '--ignore=server/tests_v71/test_postgres_native.py'],
                                env={**os.environ,'PYTHONPATH':'server'}))
