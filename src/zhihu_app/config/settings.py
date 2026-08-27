from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(eq=True)
class AppSettings:
    output_dir: Path
    profile_dir: Path | None = None
    interval_seconds: float = 1.5
    max_items: int = 50
    proxy: str = ""

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.profile_dir is not None:
            self.profile_dir = Path(self.profile_dir)
        if self.interval_seconds < 0.5:
            raise ValueError("interval must be at least 0.5 seconds")
        if self.max_items < 1:
            raise ValueError("max_items must be positive")

    @classmethod
    def defaults(cls, root: Path | None = None) -> "AppSettings":
        if root is not None:
            base = Path(root)
            return cls(base / "output", base / "data" / "browser_profile")
        if getattr(sys, "frozen", False):
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ZhihuCrawler"
            return cls(base / "output", base / "browser_profile")
        base = Path(__file__).resolve().parents[3]
        return cls(base / "output", base / "data" / "browser_profile")

    @classmethod
    def load(cls, path: Path | None = None) -> "AppSettings":
        if path is None:
            return cls.defaults()
        path = Path(path)
        if not path.exists():
            return cls.defaults(path.parent)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def save(self, path: Path | None = None) -> None:
        path = Path(path) if path is not None else self.output_dir.parent / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data = {key: str(value) if isinstance(value, Path) else value for key, value in data.items()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
