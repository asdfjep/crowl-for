"""
HS News Service - 数据库模型
对应 news_aggregator 后台管理的数据结构
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

Base = declarative_base()


class Source(Base):
    """订阅源表 - 对应 news_aggregator Source 模型"""
    __tablename__ = 'sources'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, comment='源名称')
    url = Column(String(500), nullable=False, comment='源 URL')
    category = Column(String(50), default='general', comment='源分类: general/aerospace/ai/polarizer/display/finance')
    crawler_type = Column(String(50), default='async', comment='爬虫类型: async/playwright/html')
    crawler_module = Column(String(100), nullable=False, comment='爬虫模块名 (sources.xxx)')
    crawl_interval = Column(Integer, default=1800, comment='爬取间隔（秒）')
    is_active = Column(Boolean, default=True, comment='是否启用')
    timeout = Column(Integer, default=45, comment='单源超时时间（秒）')
    last_crawl_time = Column(DateTime, nullable=True, comment='上次爬取时间')
    last_crawl_status = Column(String(20), default='pending', comment='爬取状态: pending/success/failed')
    total_articles = Column(Integer, default=0, comment='累计抓取文章数')
    article_count_last = Column(Integer, default=0, comment='上次爬取文章数')
    error_message = Column(Text, nullable=True, comment='最近错误信息')
    config_json = Column(Text, nullable=True, comment='自定义爬虫配置 (JSON)')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'category': self.category,
            'crawler_type': self.crawler_type,
            'crawler_module': self.crawler_module,
            'crawl_interval': self.crawl_interval,
            'is_active': self.is_active,
            'timeout': self.timeout,
            'last_crawl_time': self.last_crawl_time.strftime('%Y-%m-%d %H:%M:%S') if self.last_crawl_time else None,
            'last_crawl_status': self.last_crawl_status,
            'total_articles': self.total_articles,
            'article_count_last': self.article_count_last,
            'error_message': self.error_message,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class Category(Base):
    """行业分类表 - 对应 news_aggregator INDUSTRY_CATEGORIES 配置"""
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True, comment='分类名称')
    description = Column(String(200), nullable=True, comment='分类描述')
    keywords = Column(Text, nullable=False, comment='关键词列表 (每行一个)')
    priority = Column(Integer, default=10, comment='匹配优先级')
    color = Column(String(20), default='#6366f1', comment='前端显示颜色')
    is_active = Column(Boolean, default=True, comment='是否启用')
    article_count = Column(Integer, default=0, comment='文章数')
    created_at = Column(DateTime, default=datetime.now)

    def get_keywords_list(self):
        """获取关键词列表"""
        if not self.keywords:
            return []
        return [k.strip() for k in self.keywords.strip().split('\n') if k.strip()]

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'keywords': self.get_keywords_list(),
            'keywords_raw': self.keywords,
            'priority': self.priority,
            'color': self.color,
            'is_active': self.is_active,
            'article_count': self.article_count,
        }


class Article(Base):
    """新闻文章表 - 存储抓取结果"""
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False, comment='标题')
    summary = Column(Text, nullable=True, comment='摘要')
    content = Column(Text, nullable=True, comment='全文内容')
    url = Column(String(500), nullable=False, unique=True, comment='原文链接')
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=True, comment='来源 ID')
    source_name = Column(String(100), nullable=True, comment='来源名称（冗余）')

    # 分类信息
    category = Column(String(50), default='other', comment='自动匹配的行业分类')
    severity = Column(String(10), default='low', comment='严重程度: low/medium/high/critical')

    # 地理位置
    location = Column(String(200), nullable=True, comment='位置描述')
    latitude = Column(Float, nullable=True, comment='纬度')
    longitude = Column(Float, nullable=True, comment='经度')

    # 去重
    dedup_hash = Column(String(64), nullable=False, index=True, comment='标题 hash')

    # 状态
    is_pushed = Column(Boolean, default=False, comment='是否已推送')
    publish_time = Column(DateTime, nullable=True, comment='原文发布时间')

    created_at = Column(DateTime, default=datetime.now, index=True)
    crawl_time = Column(DateTime, default=datetime.now, comment='抓取时间')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'summary': self.summary,
            'url': self.url,
            'source_name': self.source_name,
            'category': self.category,
            'severity': self.severity,
            'location': self.location,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'is_pushed': self.is_pushed,
            'publish_time': self.publish_time.strftime('%Y-%m-%d %H:%M:%S') if self.publish_time else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class CrawlLog(Base):
    """爬取日志表"""
    __tablename__ = 'crawl_logs'

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=True, comment='来源 ID')
    source_name = Column(String(100), nullable=True, comment='来源名称')
    status = Column(String(20), default='success', comment='状态: success/failed')
    articles_found = Column(Integer, default=0, comment='发现文章数')
    articles_new = Column(Integer, default=0, comment='新增文章数')
    error_message = Column(Text, nullable=True, comment='错误信息')
    duration_seconds = Column(Float, default=0, comment='耗时（秒）')
    created_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'source_name': self.source_name,
            'status': self.status,
            'articles_found': self.articles_found,
            'articles_new': self.articles_new,
            'error_message': self.error_message,
            'duration_seconds': self.duration_seconds,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class SystemConfig(Base):
    """系统配置表 - 对应 news_aggregator settings.py"""
    __tablename__ = 'system_config'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, comment='配置键')
    value = Column(Text, nullable=True, comment='配置值')
    description = Column(String(200), nullable=True, comment='配置描述')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }


# ========== 数据库初始化 ==========

def init_db(db_path):
    """初始化数据库"""
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


def seed_default_categories(session):
    """种子默认分类数据 - 从 news_aggregator 配置文档迁移"""
    existing = session.query(Category).count()
    if existing > 0:
        return

    defaults = [
        Category(
            name='航天',
            description='航天、航空、卫星、火箭、发射等',
            keywords='航天\n航空\n卫星\n火箭\n飞船\n空间站\n载人航天\n嫦娥\n天问\n神舟\n天宫\n长征火箭\n发射\n轨道\nNASA\nSpaceX\n星舰\n星链\n火星\n月球\n探月\n中国航天\n航天科技\n航天科工\n国家航天局',
            priority=10,
            color='#3b82f6',
        ),
        Category(
            name='偏光片',
            description='偏光片、LCD、OLED、显示面板、面板厂商',
            keywords='偏光片\n偏振片\nLCD\nOLED\n显示面板\n液晶\n面板\n显示屏\n背光\n液晶模组\n偏光膜\n三星\nLG 显示\n京东方\nTCL 华星\n惠科\n维信诺\n住友化学\n日东电工\n三利谱\n恒美光电\n深天马',
            priority=10,
            color='#8b5cf6',
        ),
        Category(
            name='人工智能',
            description='AI、大模型、机器学习、自动驾驶、GPU',
            keywords='人工智能\nAI\n大模型\n机器学习\n深度学习\n神经网络\n自然语言处理\n计算机视觉\n语音识别\n生成式 AI\nAIGC\nChatGPT\nGPT\n文心一言\n通义千问\n智谱\n月之暗面\nMiniMax\n阶跃星辰\n百川智能\n自动驾驶\n智能驾驶\n机器人\n人形机器人\n具身智能\n算力\nGPU\nNPU\n训练\n推理\n大语言模型',
            priority=10,
            color='#10b981',
        ),
        Category(
            name='杉杉集团',
            description='杉杉集团相关',
            keywords='杉杉\n杉杉股份\n杉杉集团\n杉杉科技\n杉杉能源\n杉杉材料\n杉杉锂电\n杉杉光伏\n杉杉纺织\n杉杉商业\n郑永刚\n郑驹\n杉杉控股\n杉杉品牌',
            priority=10,
            color='#f59e0b',
        ),
        Category(
            name='其他',
            description='不属于以上分类的内容',
            keywords='',
            priority=99,
            color='#6b7280',
        ),
    ]
    for cat in defaults:
        session.add(cat)
    session.commit()


def seed_default_sources(session):
    """种子默认订阅源 - 从 scheduler.py 迁移"""
    existing = session.query(Source).count()
    if existing > 0:
        return

    # 映射 scheduler.py 中的 sources
    defaults = [
        Source(name='同花顺', url='http://www.10jqka.com.cn/', category='finance', crawler_type='async', crawler_module='thsnews', crawl_interval=1800),
        Source(name='航空航天', url='https://techcrunch.com/category/space/', category='aerospace', crawler_type='async', crawler_module='aerospace', crawl_interval=1800),
        Source(name='人工智能', url='https://techcrunch.com/category/artificial-intelligence/', category='ai', crawler_type='async', crawler_module='ai_news', crawl_interval=1800),
        Source(name='偏光片/显示', url='https://www.oled-info.com/', category='polarizer', crawler_type='async', crawler_module='polarizer', crawl_interval=1800),
        Source(name='冲突事件', url='https://www.theverge.com/', category='other', crawler_type='async', crawler_module='conflict_events', crawl_interval=1800),
        Source(name='金融市场', url='http://www.10jqka.com.cn/', category='finance', crawler_type='async', crawler_module='financial_markets', crawl_interval=1800),
        Source(name='财联社/新浪财经', url='https://www.cls.cn/', category='finance', crawler_type='async', crawler_module='enhanced', crawl_interval=900),
        Source(name='显示行业 Daily', url='https://www.displaydaily.com/', category='display', crawler_type='async', crawler_module='enhanced', crawl_interval=3600),
        Source(name='航天科技/SpaceNews', url='https://spacenews.com/', category='aerospace', crawler_type='async', crawler_module='enhanced', crawl_interval=1800),
        Source(name='Space.com', url='https://www.space.com/', category='aerospace', crawler_type='async', crawler_module='space_com', crawl_interval=1800),
        Source(name='NASA', url='https://www.nasa.gov/', category='aerospace', crawler_type='async', crawler_module='nasa', crawl_interval=3600),
        Source(name='The Decoder', url='https://the-decoder.com/', category='ai', crawler_type='async', crawler_module='the_decoder', crawl_interval=1800),
        Source(name='Synced', url='https://syncedreview.com/', category='ai', crawler_type='async', crawler_module='synced', crawl_interval=1800),
        Source(name='DeepMind', url='https://deepmind.google/', category='ai', crawler_type='async', crawler_module='deepmind', crawl_interval=1800),
        Source(name='VentureBeat', url='https://venturebeat.com/', category='ai', crawler_type='async', crawler_module='venturebeat', crawl_interval=1800),
        Source(name='EU AI Act', url='https://digital-strategy.ec.europa.eu/', category='ai', crawler_type='async', crawler_module='eu_ai', crawl_interval=3600),
        Source(name='雷锋网', url='https://www.leiphone.com/', category='ai', crawler_type='async', crawler_module='leiphone', crawl_interval=1800),
        Source(name='量子位', url='https://www.qbitai.com/', category='ai', crawler_type='async', crawler_module='qbitai', crawl_interval=1800),
        Source(name='OFweek', url='https://display.ofweek.com/', category='display', crawler_type='playwright', crawler_module='ofweek_pw', crawl_interval=3600),
        Source(name='36Kr', url='https://36kr.com/', category='finance', crawler_type='playwright', crawler_module='kr36_pw', crawl_interval=1800),
        Source(name='京东方', url='https://www.boe.com/', category='display', crawler_type='playwright', crawler_module='boe_pw', crawl_interval=3600),
        Source(name='SpaceNews', url='https://spacenews.com/', category='aerospace', crawler_type='playwright', crawler_module='spacenews_pw', crawl_interval=1800),
        Source(name='AI Business', url='https://aibusiness.com/', category='ai', crawler_type='html', crawler_module='aibusiness', crawl_interval=3600),
        Source(name='LG Display', url='https://www.lgdisplay.com/', category='display', crawler_type='html', crawler_module='lgdisplay', crawl_interval=3600),
    ]
    for src in defaults:
        session.add(src)
    session.commit()


def seed_default_config(session):
    """种子默认系统配置"""
    existing = session.query(SystemConfig).count()
    if existing > 0:
        return

    defaults = [
        SystemConfig(key='site_name', value='HS News 管理后台', description='站点名称'),
        SystemConfig(key='site_description', value='新闻聚合爬虫管理系统', description='站点描述'),
        SystemConfig(key='crawl_enabled', value='true', description='是否启用定时爬取'),
        SystemConfig(key='default_interval_minutes', value='60', description='默认爬取间隔（分钟）'),
        SystemConfig(key='output_format', value='json,markdown', description='输出格式: json,markdown,both'),
        SystemConfig(key='dedup_enabled', value='true', description='是否启用去重'),
        SystemConfig(key='max_retries', value='3', description='最大重试次数'),
        SystemConfig(key='request_timeout', value='30', description='请求超时时间（秒）'),
        SystemConfig(key='user_agent', value='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', description='爬虫 User-Agent'),
        SystemConfig(key='request_delay', value='1', description='请求间隔（秒）'),
        SystemConfig(key='analyzer_url', value='http://localhost:8001/api/analyze', description='分析服务推送地址'),
    ]
    for cfg in defaults:
        session.add(cfg)
    session.commit()
