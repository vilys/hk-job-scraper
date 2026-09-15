# -*- coding: utf-8 -*-
"""離線測試套件（零請求、零網路）。

為什麼存在：本專案是爬蟲，任何驗證若只能靠真實請求，就與
「不要太狠、一步一步、不要被封」的鐵律直接衝突。這套測試的目的，
是把能在本地推理完的部分全部搬到沙盤上，減少不必要的出擊。

框架選用標準庫 unittest（非 pytest）：零安裝、零依賴變更，
clone 下來即可執行：

    python -m unittest discover -s tests -v
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
