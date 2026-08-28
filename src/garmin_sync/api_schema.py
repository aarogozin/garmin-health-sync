from __future__ import annotations

import json

from .api_models import exported_schema


def main() -> None:
    print(json.dumps(exported_schema(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
