"""各網站爬蟲模組。新增爬蟲請在此匯出，供 main.py 動態調用。"""
from .moovup import MoovupScraper
from .gov_hk import GovHkScraper
from .jobsdb import JobsDBScraper
from .linkedin import LinkedInScraper
from .indeed import IndeedScraper
from .recruit import RecruitScraper
from .jobmarket import JobMarketScraper
from .foundit import FounditScraper
from .efc import EfcScraper
from .liepin import LiepinScraper
from .zhipin import ZhipinScraper

SCRAPERS = {
    "moovup": MoovupScraper,
    "gov_hk": GovHkScraper,
    "jobsdb": JobsDBScraper,
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "recruit": RecruitScraper,
    "jobmarket": JobMarketScraper,
    "foundit": FounditScraper,
    "efc": EfcScraper,
    "liepin": LiepinScraper,
    "zhipin": ZhipinScraper,
}

__all__ = [
    "SCRAPERS",
    "MoovupScraper",
    "GovHkScraper",
    "JobsDBScraper",
    "LinkedInScraper",
    "IndeedScraper",
    "RecruitScraper",
    "JobMarketScraper",
    "FounditScraper",
    "EfcScraper",
    "LiepinScraper",
    "ZhipinScraper",
]
