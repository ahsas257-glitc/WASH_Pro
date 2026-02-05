# src/Tools/utils/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List


@dataclass(frozen=True)
class Tool6Context:
    project_root: str
    tool_name: str
    tpm_id: str
    row: Dict[str, Any]

    # Step 2
    defaults: Dict[str, Any]
    hints: Dict[str, str]

    # Step 3/4 media
    all_photo_urls: List[str]
    photo_label_by_url: Dict[str, str]
    audios: List[Dict[str, Any]]

    # logos (optional)
    unicef_logo_path: Optional[str] = None
    act_logo_path: Optional[str] = None
    ppc_logo_path: Optional[str] = None
