"""
HS News Service - 数据库操作类
提供 Source, Category, Article, CrawlLog, SystemConfig 的 CRUD 操作
"""
import hashlib
from datetime import datetime
from typing import List, Optional, Dict
from .models import Source, Category, Article, CrawlLog, SystemConfig


class SourceManager:
    @staticmethod
    def get_all(session) -> List[Source]:
        return session.query(Source).order_by(Source.id).all()

    @staticmethod
    def get_active(session) -> List[Source]:
        return session.query(Source).filter_by(is_active=True).order_by(Source.id).all()

    @staticmethod
    def get_by_id(session, source_id: int) -> Optional[Source]:
        return session.query(Source).filter_by(id=source_id).first()

    @staticmethod
    def get_by_module(session, module_name: str) -> Optional[Source]:
        return session.query(Source).filter_by(crawler_module=module_name).first()

    @staticmethod
    def add(session, name: str, url: str, category: str = 'general',
            crawler_type: str = 'async', crawler_module: str = '',
            crawl_interval: int = 1800, timeout: int = 45,
            config_json: str = None) -> Source:
        source = Source(
            name=name, url=url, category=category,
            crawler_type=crawler_type, crawler_module=crawler_module,
            crawl_interval=crawl_interval, timeout=timeout,
            config_json=config_json
        )
        session.add(source)
        session.commit()
        return source

    @staticmethod
    def update(session, source_id: int, **kwargs) -> bool:
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            return False
        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)
        source.updated_at = datetime.now()
        session.commit()
        return True

    @staticmethod
    def delete(session, source_id: int) -> bool:
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            return False
        session.delete(source)
        session.commit()
        return True

    @staticmethod
    def update_crawl_status(session, source_id: int, status: str,
                            articles_found: int = 0, articles_new: int = 0,
                            error_message: str = None):
        source = SourceManager.get_by_id(session, source_id)
        if not source:
            return
        source.last_crawl_time = datetime.now()
        source.last_crawl_status = status
        source.article_count_last = articles_found
        source.total_articles += articles_new
        if error_message:
            source.error_message = error_message
        session.commit()


class CategoryManager:
    @staticmethod
    def get_all(session) -> List[Category]:
        return session.query(Category).order_by(Category.priority, Category.id).all()

    @staticmethod
    def get_active(session) -> List[Category]:
        return session.query(Category).filter_by(is_active=True).order_by(Category.priority).all()

    @staticmethod
    def get_by_id(session, cat_id: int) -> Optional[Category]:
        return session.query(Category).filter_by(id=cat_id).first()

    @staticmethod
    def get_by_name(session, name: str) -> Optional[Category]:
        return session.query(Category).filter_by(name=name).first()

    @staticmethod
    def add(session, name: str, keywords: str, description: str = '',
            priority: int = 10, color: str = '#6366f1') -> Category:
        cat = Category(name=name, keywords=keywords, description=description,
                       priority=priority, color=color)
        session.add(cat)
        session.commit()
        return cat

    @staticmethod
    def update(session, cat_id: int, **kwargs) -> bool:
        cat = CategoryManager.get_by_id(session, cat_id)
        if not cat:
            return False
        for key, value in kwargs.items():
            if hasattr(cat, key):
                setattr(cat, key, value)
        session.commit()
        return True

    @staticmethod
    def delete(session, cat_id: int) -> bool:
        cat = CategoryManager.get_by_id(session, cat_id)
        if not cat or cat.name == '其他':
            return False
        session.delete(cat)
        session.commit()
        return True

    @staticmethod
    def match(session, title: str, summary: str = '') -> str:
        """根据关键词匹配分类，返回分类名称"""
        text = f"{title} {summary}".lower()
        categories = CategoryManager.get_active(session)
        best_match = '其他'
        best_score = 0
        for cat in categories:
            if cat.name == '其他':
                continue
            score = 0
            for kw in cat.get_keywords_list():
                if kw.lower() in text:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = cat.name
        return best_match


class ArticleManager:
    @staticmethod
    def get_all(session, limit: int = 100) -> List[Article]:
        return session.query(Article).order_by(Article.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_by_id(session, article_id: int) -> Optional[Article]:
        return session.query(Article).filter_by(id=article_id).first()

    @staticmethod
    def get_by_category(session, category: str, limit: int = 100) -> List[Article]:
        return session.query(Article).filter_by(category=category).order_by(Article.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_by_source(session, source_id: int, limit: int = 100) -> List[Article]:
        return session.query(Article).filter_by(source_id=source_id).order_by(Article.created_at.desc()).limit(limit).all()

    @staticmethod
    def count(session) -> int:
        return session.query(Article).count()

    @staticmethod
    def count_by_category(session) -> Dict[str, int]:
        """按分类统计文章数"""
        results = session.query(Article.category, Article).all()
        counts = {}
        for cat, _ in results:
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    @staticmethod
    def add(session, title: str, url: str, source_id: int = None,
            source_name: str = None, summary: str = None,
            content: str = None, category: str = 'other',
            severity: str = 'low', location: str = None,
            latitude: float = None, longitude: float = None,
            publish_time: datetime = None) -> Optional[Article]:
        """添加文章，自动去重"""
        dedup_hash = hashlib.sha256(title.encode('utf-8')).hexdigest()
        existing = session.query(Article).filter_by(dedup_hash=dedup_hash).first()
        if existing:
            return None

        article = Article(
            title=title, url=url, source_id=source_id,
            source_name=source_name, summary=summary, content=content,
            category=category, severity=severity, location=location,
            latitude=latitude, longitude=longitude, publish_time=publish_time,
            dedup_hash=dedup_hash, crawl_time=datetime.now()
        )
        session.add(article)
        session.commit()
        return article

    @staticmethod
    def delete(session, article_id: int) -> bool:
        article = ArticleManager.get_by_id(session, article_id)
        if not article:
            return False
        session.delete(article)
        session.commit()
        return True

    @staticmethod
    def clear_old(session, days: int = 30) -> int:
        """清理旧文章"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        count = session.query(Article).filter(Article.created_at < cutoff).delete()
        session.commit()
        return count


class CrawlLogManager:
    @staticmethod
    def get_recent(session, limit: int = 50) -> List[CrawlLog]:
        return session.query(CrawlLog).order_by(CrawlLog.created_at.desc()).limit(limit).all()

    @staticmethod
    def add(session, source_id: int = None, source_name: str = None,
            status: str = 'success', articles_found: int = 0,
            articles_new: int = 0, error_message: str = None,
            duration_seconds: float = 0):
        log = CrawlLog(
            source_id=source_id, source_name=source_name,
            status=status, articles_found=articles_found,
            articles_new=articles_new, error_message=error_message,
            duration_seconds=duration_seconds
        )
        session.add(log)
        session.commit()
        return log

    @staticmethod
    def clear_old(session, days: int = 7) -> int:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        count = session.query(CrawlLog).filter(CrawlLog.created_at < cutoff).delete()
        session.commit()
        return count


class ConfigManager:
    @staticmethod
    def get(session, key: str, default: str = None) -> str:
        cfg = session.query(SystemConfig).filter_by(key=key).first()
        return cfg.value if cfg else default

    @staticmethod
    def set(session, key: str, value: str, description: str = None) -> SystemConfig:
        cfg = session.query(SystemConfig).filter_by(key=key).first()
        if cfg:
            cfg.value = value
            if description:
                cfg.description = description
        else:
            cfg = SystemConfig(key=key, value=value, description=description)
            session.add(cfg)
        session.commit()
        return cfg

    @staticmethod
    def get_all(session) -> List[SystemConfig]:
        return session.query(SystemConfig).order_by(SystemConfig.key).all()

    @staticmethod
    def get_int(session, key: str, default: int = 0) -> int:
        val = ConfigManager.get(session, key, str(default))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_bool(session, key: str, default: bool = False) -> bool:
        val = ConfigManager.get(session, key, str(default)).lower()
        return val in ('true', '1', 'yes', 'on')
