from __future__ import annotations

import re
from typing import Any


class PrivacyGate:
    def authorize(self, *, consent: bool, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not consent:
            raise PermissionError("数据权限与隐私门禁未通过：需要 privacy_consent=true")
        columns = sorted({key for row in (rows or []) for key in row})
        sensitive = [c for c in columns if re.search(r"phone|mobile|email|身份证|姓名", c, re.I)]
        return {"authorized": True, "sensitive_columns_detected": sensitive, "policy": "consent_required"}

