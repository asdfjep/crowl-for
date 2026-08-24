"""
新闻爬虫基类 & 数据模型
整合 WorldMonitor 风格的严重程度评估与地理位置自动匹配
"""
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入严重程度评估
try:
    from services.severity import SeverityAssessor
except ImportError:
    SeverityAssessor = None

# 默认请求头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# 简易地名转坐标字典 (解决没有 API 时的地图标点问题)
# 包含主要航天发射场、冲突热点、金融中心
LOCATION_COORDS = {
    # 🚀 航天发射场 (高优先级)
    "Florida": (28.57, -80.64), "Cape Canaveral": (28.39, -80.60), "Kennedy": (28.57, -80.64), "CCSFS": (28.39, -80.60),
    "California": (34.75, -120.61), "Vandenberg": (34.75, -120.61), "Edwards": (34.90, -117.88),
    "Texas": (28.60, -96.50), "Boca Chica": (25.99, -97.15), "Starbase": (25.99, -97.15),
    "Wenchang": (19.61, 110.95), "Jiuquan": (40.96, 100.29), "Xichang": (28.25, 102.03), "Taiyuan": (38.85, 111.60),
    "Baikonur": (45.96, 63.30), "Kourou": (5.16, -52.64), "Tanegashima": (30.40, 130.97),
    "Satish Dhawan": (13.72, 80.23), "Sriharikota": (13.72, 80.23),
    
    # 🌍 常见国家/地区/城市
    "中国": (35.86, 104.19), "北京": (39.90, 116.40), "上海": (31.23, 121.47), "深圳": (22.54, 114.05), "文昌": (19.61, 110.95),
    "美国": (38.90, -77.04), "华盛顿": (38.90, -77.04), "纽约": (40.71, -74.00), "加州": (36.77, -119.41), "德州": (31.96, -99.90),
    "伊朗": (32.42, 53.68), "德黑兰": (35.68, 51.38),
    "以色列": (31.04, 34.85), "特拉维夫": (32.08, 34.78), "加沙": (31.50, 34.46), "Gaza": (31.50, 34.46),
    "俄罗斯": (61.52, 105.31), "莫斯科": (55.75, 37.61),
    "日本": (36.20, 138.25), "东京": (35.67, 139.65), "种子岛": (30.40, 130.97),
    "韩国": (35.90, 127.76), "首尔": (37.56, 126.97),
    "英国": (55.37, -3.43), "伦敦": (51.50, -0.12),
    "德国": (51.16, 10.45), "柏林": (52.52, 13.40),
    "印度": (20.59, 78.96), "新德里": (28.61, 77.20),
    "法国": (46.60, 2.21), "巴黎": (48.85, 2.35),
    "澳大利亚": (25.27, 133.77), "堪培拉": (35.28, 149.12),
    "乌克兰": (48.37, 31.16), "基辅": (50.45, 30.52),
    "叙利亚": (34.80, 38.99), "大马士革": (33.51, 36.29),
    "台湾": (23.69, 120.96),
    "Pacific Ocean": (0.0, -160.0), "Pacific": (0.0, -160.0), # 溅落点
}


class NewsItem:
    """新闻数据模型"""
    
    def __init__(
        self,
        title: str,
        url: str,
        source: str,
        publish_time: datetime,
        category: str,
        summary: Optional[str] = None,
        content: Optional[str] = None,
        location: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        tags: Optional[List[str]] = None,
        severity: Optional[str] = None,
    ):
        self.title = title
        self.url = url
        self.source = source
        self.publish_time = publish_time
        self.category = category
        self.summary = summary
        self.content = content
        self.location = location
        self.tags = tags or []
        self.crawl_time = datetime.now()
        
        # 自动补全坐标：如果提供了 location 但没有经纬度，尝试匹配
        if latitude is not None and longitude is not None:
            self.latitude = latitude
            self.longitude = longitude
        elif location:
            coords = self._match_location(location)
            if coords:
                self.latitude, self.longitude = coords
            else:
                self.latitude = None
                self.longitude = None
        else:
            self.latitude = None
            self.longitude = None
        
        # WorldMonitor 风格：严重程度评估
        if severity:
            self.severity = severity
        elif SeverityAssessor:
            self.severity = SeverityAssessor.assess(title, summary or '', content or '')
        else:
            self.severity = 'low'

    def _match_location(self, loc_str: str):
        """根据地点字符串匹配坐标"""
        if not loc_str:
            return None
        # 简单的关键词匹配
        for key, coords in LOCATION_COORDS.items():
            if key.lower() in loc_str.lower():
                return coords
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（仅保留发布时间，抓取时间写在文件抬头）"""
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "publishTime": self.publish_time.isoformat() if self.publish_time else None,
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "content": self.content,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "tags": self.tags,
            "isPushed": False,
        }


class BaseCrawler(ABC):
    """爬虫基类"""

    # 子类可覆盖的类属性
    default_timeout = aiohttp.ClientTimeout(total=30)
    default_headers = DEFAULT_HEADERS

    def __init__(self, name: str, base_url: str, category: str):
        self.name = name
        self.base_url = base_url
        self.category = category
        self.session: Optional[aiohttp.ClientSession] = None
        # enhanced.py 子类需要的属性
        self.headers = self.default_headers
        self.timeout = self.default_timeout

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers=self.default_headers
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @abstractmethod
    async def fetch_news(self) -> List[NewsItem]:
        """获取新闻列表"""
        pass

    async def fetch_url(self, url: str) -> Optional[str]:
        """获取网页内容"""
        try:
            async with self.session.get(url, timeout=self.timeout) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            logger.error(f"获取 {url} 失败：{e}")
            return None

    def parse_category(self, title: str, content: str = "") -> str:
        """根据内容自动分类"""
        keywords = {
            "aerospace": ["航天", "航空", "卫星", "火箭", "空间站", "发射"],
            "ai": ["人工智能", "AI", "大模型", "深度学习", "机器学习"],
            "polarizer": ["偏光片", "显示", "面板", "LCD", "OLED"],
            "politics": ["政府", "外交", "选举", "政策"],
            "military": ["军事", "军队", "武器", "演习"],
            "economy": ["经济", "股市", "贸易", "金融"],
            "tech": ["科技", "互联网", "数码"],
        }
        
        text = title + " " + content
        for category, words in keywords.items():
            if any(word in text for word in words):
                return category
        
        return self.category
