"""Back-compat entry point — launch the unified dashboard.

The dashboard lives at ``dashboard/app.py``. This file is kept so existing
``streamlit run app.py`` invocations still work.
"""

import runpy
from pathlib import Path

_DASHBOARD = Path(__file__).parent / "dashboard" / "app.py"

runpy.run_path(str(_DASHBOARD), run_name="__main__")
