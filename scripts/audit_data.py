import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ckd_core import config as C  # noqa: E402
from ckd_core.data import audit, load_splits  # noqa: E402

rep = audit(load_splits())
C.REPORT_DIR.mkdir(exist_ok=True)
(C.REPORT_DIR / "data_audit.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(rep, indent=2, ensure_ascii=False))
