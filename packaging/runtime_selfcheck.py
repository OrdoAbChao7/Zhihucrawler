from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from zhihu_app.config.settings import AppSettings
from zhihu_app.engine.collection_downloader import CollectionDownloader
from zhihu_app.engine.errors import ZhihuRiskControlError
from zhihu_app.engine.mediacrawler_adapter import MediaCrawlerAdapter
from zhihu_app.engine.models import TaskType, ZhihuTask


def main() -> None:
    root = Path(os.environ["LOCALAPPDATA"]) / "ZhihuCrawler"
    run_root = root / "selfcheck" / datetime.now().strftime("%Y%m%d-%H%M%S")
    settings = AppSettings(run_root, root / "browser_profile", interval_seconds=2.0, max_items=1)
    cases = [
        (TaskType.SEARCH, "Python"),
        (TaskType.QUESTION, "https://www.zhihu.com/question/1959694620851167862"),
        (TaskType.CREATOR, "https://www.zhihu.com/people/he-tao-you-jian-he-tao"),
        (TaskType.COLLECTION, "https://www.zhihu.com/people/he-tao-you-jian-he-tao/posts"),
    ]
    for kind, target in cases:
        max_items = 3 if kind is TaskType.CREATOR else 1
        task = ZhihuTask(
            kind, target, max_items=max_items, interval_seconds=2.0,
            output_dir=run_root / kind.value,
        )
        engine = CollectionDownloader(settings) if kind is TaskType.COLLECTION else MediaCrawlerAdapter(settings)
        try:
            result = engine.run(task, lambda message: print(f"{kind.value}: {message}"), Event())
            print(f"{kind.value}: status={result.status}, items={result.items_processed}")
        except ZhihuRiskControlError as exc:
            print(f"{kind.value}: error={type(exc).__name__}: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    main()
