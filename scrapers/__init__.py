"""各網站爬蟲模組。新增爬蟲請在此匯出，供 main.py 動態調用。"""
from .moovup import MoovupScraper
from .gov_hk import GovHkScraper
from .jobsdb import JobsDBScraper
from .linkedin import LinkedInScraper
from .indeed import IndeedScraper
from .recruit import RecruitScraper

SCRAPERS = {
    "moovup": MoovupScraper,
    "gov_hk": GovHkScraper,
    "jobsdb": JobsDBScraper,
    "linkedin": LinkedInScraper,
    "indeed": IndeedScraper,
    "recruit": RecruitScraper,
}

__all__ = [
    "SCRAPERS",
    "MoovupScraper",
    "GovHkScraper",
    "JobsDBScraper",
    "LinkedInScraper",
    "IndeedScraper",
    "RecruitScraper",
]
