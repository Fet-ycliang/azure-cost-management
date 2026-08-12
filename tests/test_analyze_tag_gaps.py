from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from analyze_tag_gaps import analyze_resource


def _resource(*, sub_name: str = "TO-ABD360", rg: str = "fet-ids-prod-rg", purpose: str = "fet-ids") -> dict:
    return {
        "_sub_name": sub_name,
        "resourceGroup": rg,
        "type": "Microsoft.Compute/virtualMachines",
        "name": "vm-1",
        "tags": {
            "cost_center": "6251",
            "EnvType": "Production",
            "Purpose": purpose,
            "owner": "John Zeng (598493)",
        },
    }


def test_analyze_resource_accepts_reviewed_rg_default_purpose() -> None:
    result = analyze_resource(_resource())
    assert all("Purpose 不符" not in issue for issue in result["issues"])


def test_analyze_resource_flags_reviewed_rg_purpose_mismatch() -> None:
    result = analyze_resource(_resource(purpose="ai_verse"))
    assert "Purpose 不符: RG=fet-ids-prod-rg 預設為 fet-ids，實為 ai_verse" in result["issues"]


def test_analyze_resource_skips_unreviewed_rg_purpose_validation() -> None:
    result = analyze_resource(_resource(rg="unreviewed-rg", purpose="other-purpose"))
    assert all("Purpose 不符" not in issue for issue in result["issues"])
