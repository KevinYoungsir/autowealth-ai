"""
社交情绪分析模块 - 分析 Twitter/X、微博、Reddit 等社交平台的公众情绪。
支持中英文文本的情绪分析，采用基于词典的方法，不依赖外部 NLP 库。
"""

import re
import random
import logging
from collections import Counter

from .dictionary import (
    POSITIVE_WORDS_EN,
    NEGATIVE_WORDS_EN,
    POSITIVE_WORDS_CN,
    NEGATIVE_WORDS_CN,
    STOP_WORDS_EN,
    STOP_WORDS_CN,
    get_sentiment_words,
)

logger = logging.getLogger(__name__)


class SocialSentimentAnalyzer:
    """
    社交情绪分析器，支持多平台（Twitter、微博、Reddit）的情绪分析。

    使用基于词典的方法进行文本情绪分析，内置中英文情绪词典。
    当前版本使用 mock 数据模拟社交平台数据获取，后续可替换为真实 API。
    """

    def __init__(self):
        """初始化社交情绪分析器。"""
        self._positive_en = POSITIVE_WORDS_EN
        self._negative_en = NEGATIVE_WORDS_EN
        self._positive_cn = POSITIVE_WORDS_CN
        self._negative_cn = NEGATIVE_WORDS_CN
        self._stop_words_en = STOP_WORDS_EN
        self._stop_words_cn = STOP_WORDS_CN

    def analyze_twitter(self, symbol, count=100):
        """
        分析 Twitter/X 上关于指定股票代码的公众情绪。

        Args:
            symbol: 股票代码或关键词（如 "AAPL", "TSLA"）。
            count: 要分析的推文数量。

        Returns:
            dict: 包含平台、代码、总数、正面/负面/中性数量、情绪分数和关键词的字典。
        """
        logger.info(f"分析 Twitter 情绪: symbol={symbol}, count={count}")

        # Mock 模式：生成模拟推文数据
        mock_tweets = self._generate_mock_tweets(symbol, count, platform="twitter")

        # 分析每条推文的情绪
        positive = 0
        negative = 0
        neutral = 0
        texts = []

        for tweet in mock_tweets:
            text = tweet["text"]
            texts.append(text)
            result = self._analyze_text_sentiment(text)
            if result["label"] == "positive":
                positive += 1
            elif result["label"] == "negative":
                negative += 1
            else:
                neutral += 1

        total = len(mock_tweets)
        score = self._calculate_sentiment_score(positive, negative, neutral)

        # 提取关键词
        top_keywords = self._extract_keywords(texts)

        return {
            "platform": "twitter",
            "symbol": symbol,
            "total": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "score": score,
            "top_keywords": top_keywords,
        }

    def analyze_weibo(self, keyword, count=100):
        """
        分析微博上关于指定关键词的公众情绪。

        Args:
            keyword: 搜索关键词（如 "贵州茅台", "A股"）。
            count: 要分析的微博数量。

        Returns:
            dict: 包含平台、关键词、总数、正面/负面/中性数量、情绪分数和关键词的字典。
        """
        logger.info(f"分析微博情绪: keyword={keyword}, count={count}")

        # Mock 模式：生成模拟微博数据
        mock_posts = self._generate_mock_tweets(keyword, count, platform="weibo")

        positive = 0
        negative = 0
        neutral = 0
        texts = []

        for post in mock_posts:
            text = post["text"]
            texts.append(text)
            result = self._analyze_text_sentiment(text)
            if result["label"] == "positive":
                positive += 1
            elif result["label"] == "negative":
                negative += 1
            else:
                neutral += 1

        total = len(mock_posts)
        score = self._calculate_sentiment_score(positive, negative, neutral)
        top_keywords = self._extract_keywords(texts)

        return {
            "platform": "weibo",
            "symbol": keyword,
            "total": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "score": score,
            "top_keywords": top_keywords,
        }

    def analyze_reddit(self, subreddit="wallstreetbets", keyword=None, count=100):
        """
        分析 Reddit 子版块上关于指定关键词的公众情绪。

        Args:
            subreddit: 子版块名称（默认 "wallstreetbets"）。
            keyword: 搜索关键词（可选）。
            count: 要分析的帖子数量。

        Returns:
            dict: 包含平台、子版块、关键词、总数、正面/负面/中性数量、情绪分数和关键词的字典。
        """
        logger.info(
            f"分析 Reddit 情绪: subreddit={subreddit}, keyword={keyword}, count={count}"
        )

        # Mock 模式：生成模拟 Reddit 数据
        mock_posts = self._generate_mock_tweets(
            keyword or subreddit, count, platform="reddit"
        )

        positive = 0
        negative = 0
        neutral = 0
        texts = []

        for post in mock_posts:
            text = post["text"]
            texts.append(text)
            result = self._analyze_text_sentiment(text)
            if result["label"] == "positive":
                positive += 1
            elif result["label"] == "negative":
                negative += 1
            else:
                neutral += 1

        total = len(mock_posts)
        score = self._calculate_sentiment_score(positive, negative, neutral)
        top_keywords = self._extract_keywords(texts)

        return {
            "platform": "reddit",
            "symbol": keyword or subreddit,
            "subreddit": subreddit,
            "total": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "score": score,
            "top_keywords": top_keywords,
        }

    def get_combined_sentiment(self, results):
        """
        合并多平台的情绪分析结果，计算加权平均分数。

        各平台的权重：
        - Twitter: 0.35
        - Reddit: 0.35
        - Weibo: 0.30

        Args:
            results: 多个平台分析结果的列表。

        Returns:
            dict: 综合情绪报告，包含各平台详情和加权综合分数。
        """
        logger.info(f"合并多平台情绪分析: {len(results)} 个平台")

        platform_weights = {
            "twitter": 0.35,
            "reddit": 0.35,
            "weibo": 0.30,
        }

        total_weight = 0.0
        weighted_score = 0.0
        total_positive = 0
        total_negative = 0
        total_neutral = 0
        total_posts = 0
        platform_details = []

        for result in results:
            platform = result.get("platform", "unknown")
            weight = platform_weights.get(platform, 0.3)
            score = result.get("score", 0.5)

            weighted_score += score * weight
            total_weight += weight

            total_positive += result.get("positive", 0)
            total_negative += result.get("negative", 0)
            total_neutral += result.get("neutral", 0)
            total_posts += result.get("total", 0)

            platform_details.append({
                "platform": platform,
                "symbol": result.get("symbol", ""),
                "score": score,
                "positive": result.get("positive", 0),
                "negative": result.get("negative", 0),
                "neutral": result.get("neutral", 0),
                "total": result.get("total", 0),
                "weight": weight,
            })

        if total_weight > 0:
            combined_score = weighted_score / total_weight
        else:
            combined_score = 0.5

        # 合并所有平台的关键词
        all_keywords = []
        for result in results:
            all_keywords.extend(result.get("top_keywords", []))

        # 统计合并后的关键词频率
        keyword_counter = Counter()
        for kw in all_keywords:
            keyword_counter[kw["word"]] += kw["count"]

        combined_keywords = [
            {"word": word, "count": count}
            for word, count in keyword_counter.most_common(10)
        ]

        # 判断综合情绪标签
        if combined_score > 0.6:
            label = "positive"
        elif combined_score < 0.4:
            label = "negative"
        else:
            label = "neutral"

        return {
            "combined_score": round(combined_score, 4),
            "label": label,
            "total_platforms": len(results),
            "total_posts": total_posts,
            "total_positive": total_positive,
            "total_negative": total_negative,
            "total_neutral": total_neutral,
            "platform_details": platform_details,
            "top_keywords": combined_keywords,
        }

    def _analyze_text_sentiment(self, text):
        """
        分析单条文本的情绪。

        使用基于词典的方法，支持中英文混合文本。
        不依赖外部 NLP 库。

        Args:
            text: 待分析的文本字符串。

        Returns:
            dict: 包含 "score"（0.0~1.0）和 "label"（positive/negative/neutral）的字典。
        """
        if not text or not text.strip():
            return {"score": 0.5, "label": "neutral"}

        text = text.strip().lower()

        # 判断是否包含中文
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))

        positive_count = 0
        negative_count = 0

        if has_chinese:
            # 中文分词：按字符逐个匹配（简单方法）
            # 先尝试匹配双字词，再匹配单字词
            for word in self._positive_cn:
                if word in text:
                    positive_count += text.count(word)

            for word in self._negative_cn:
                if word in text:
                    negative_count += text.count(word)

            # 也检查英文词汇（混合文本）
            words_en = re.findall(r"[a-zA-Z]+", text)
            for word in words_en:
                if word in self._positive_en:
                    positive_count += 1
                elif word in self._negative_en:
                    negative_count += 1
        else:
            # 英文分词
            words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text)
            for word in words:
                word_lower = word.lower()
                if word_lower in self._positive_en:
                    positive_count += 1
                elif word_lower in self._negative_en:
                    negative_count += 1

        total = positive_count + negative_count

        if total == 0:
            return {"score": 0.5, "label": "neutral"}

        # 计算情绪分数：正面词占比（0.0 = 全负面，1.0 = 全正面）
        score = positive_count / total

        # 判断标签
        if score > 0.6:
            label = "positive"
        elif score < 0.4:
            label = "negative"
        else:
            label = "neutral"

        return {"score": round(score, 4), "label": label}

    def _extract_keywords(self, texts, top_n=10):
        """
        从文本列表中提取高频关键词。

        使用简单词频统计，过滤停用词。

        Args:
            texts: 文本字符串列表。
            top_n: 返回前 N 个高频词。

        Returns:
            list: 包含 {"word": str, "count": int} 的列表，按频率降序排列。
        """
        word_counter = Counter()

        for text in texts:
            if not text or not text.strip():
                continue

            text = text.strip()

            # 判断是否包含中文
            has_chinese = bool(re.search(r"[\u4e00-\u9fff]", text))

            if has_chinese:
                # 简单中文分词：提取连续中文字符序列（2-4字）
                cn_words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
                for word in cn_words:
                    if word not in self._stop_words_cn:
                        word_counter[word] += 1

                # 同时提取英文词
                en_words = re.findall(r"[a-zA-Z]+", text)
                for word in en_words:
                    word_lower = word.lower()
                    if word_lower not in self._stop_words_en and len(word_lower) > 1:
                        word_counter[word_lower] += 1
            else:
                # 英文分词
                words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text)
                for word in words:
                    word_lower = word.lower()
                    if word_lower not in self._stop_words_en and len(word_lower) > 1:
                        word_counter[word_lower] += 1

        return [
            {"word": word, "count": count}
            for word, count in word_counter.most_common(top_n)
        ]

    def _calculate_sentiment_score(self, positive, negative, neutral):
        """
        根据正面/负面/中性数量计算情绪分数。

        Args:
            positive: 正面数量。
            negative: 负面数量。
            neutral: 中性数量。

        Returns:
            float: 0.0~1.0 之间的情绪分数。
        """
        total = positive + negative + neutral
        if total == 0:
            return 0.5

        # 只考虑有情绪倾向的部分
        sentiment_total = positive + negative
        if sentiment_total == 0:
            return 0.5

        score = positive / sentiment_total
        return round(score, 4)

    def _generate_mock_tweets(self, keyword, count, platform="twitter"):
        """
        生成模拟的社交媒体帖子数据（mock 模式）。

        Args:
            keyword: 搜索关键词。
            count: 生成帖子数量。
            platform: 平台名称（"twitter"/"weibo"/"reddit"）。

        Returns:
            list: 包含 {"text": str, "author": str, "timestamp": str} 的字典列表。
        """
        if platform == "twitter":
            templates = [
                f"$${keyword} is looking really bullish today! Great momentum and strong volume.",
                f"Just bought more {keyword}. The fundamentals are solid and growth is impressive.",
                f"{keyword} earnings beat expectations! This stock is going to the moon!",
                f"Analysts upgrade {keyword} to strong buy. Outperforming the market.",
                f"Very disappointed with {keyword} performance today. Big drop.",
                f"{keyword} is crashing! Sell everything before it's too late.",
                f"Worried about {keyword}. The technical indicators look bearish.",
                f"{keyword} missed earnings badly. This is a disaster.",
                f"Watching {keyword} closely. Mixed signals in the market right now.",
                f"{keyword} trading sideways today. Waiting for a clear direction.",
                f"Holding {keyword} for the long term. Diamond hands!",
                f"{keyword} just hit a new all-time high! Amazing run.",
                f"The chart for {keyword} looks terrible. Support levels broken.",
                f"Loaded up on {keyword} calls. Very optimistic about next quarter.",
                f"{keyword} is overvalued at these levels. Expect a correction soon.",
                f"Great news for {keyword}! New partnership announced.",
                f"Regulatory concerns for {keyword}. Government investigation underway.",
                f"{keyword} dividend yield is attractive. Solid income play.",
                f"Shorting {keyword}. This bubble is about to burst.",
                f"{keyword} showing strong support at current levels. Rebound expected.",
            ]
        elif platform == "weibo":
            templates = [
                f"{keyword}今天表现不错，继续看好！强势上涨趋势明显。",
                f"刚刚加仓了{keyword}，基本面很好，业绩增长超预期。",
                f"{keyword}利好消息不断，股价创新高！太牛了！",
                f"分析师强烈推荐{keyword}，目标价上调，买入评级。",
                f"今天{keyword}跌得太惨了，亏损严重，很失望。",
                f"{keyword}要崩盘了！赶紧跑路，风险太大了。",
                f"担心{keyword}后市走势，技术面很弱，压力很大。",
                f"{keyword}业绩不及预期，大跌，太糟糕了。",
                f"观望{keyword}，目前信号不明，等方向明确再操作。",
                f"{keyword}今天横盘整理，成交量萎缩，等待突破。",
                f"长期持有{keyword}，价值投资，不惧波动。",
                f"{keyword}突破历史新高！强势拉升，太厉害了！",
                f"{keyword}技术面很差，支撑位跌破，看空后市。",
                f"抄底{keyword}！估值便宜，安全边际高。",
                f"{keyword}估值太高了，泡沫严重，注意风险。",
                f"{keyword}利好！签订重大合作协议，前景看好。",
                f"{keyword}被监管调查，利空消息，小心为上。",
                f"{keyword}分红方案不错，高股息率，稳健投资。",
                f"做空{keyword}，泡沫即将破裂，暴跌在即。",
                f"{keyword}在关键支撑位获得支撑，反弹可期。",
            ]
        else:  # reddit
            templates = [
                f"YOLO {keyword} to the moon! Just went all in on calls!",
                f"{keyword} is massively undervalued. DD shows strong fundamentals and growth.",
                f"Whales accumulating {keyword}. This is going to be huge!",
                f"{keyword} just broke out of the descending channel. Bullish setup!",
                f"Lost everything on {keyword} puts. This market is rigged.",
                f"{keyword} is a total scam. Stay away from this garbage.",
                f"The bear case for {keyword} is strong. Expecting a massive dump.",
                f"{keyword} earnings were terrible. Shorting this to zero.",
                f"{keyword} is consolidating. Not sure which way it breaks.",
                f"Holding {keyword} through the dip. Diamond hands baby!",
                f"{keyword} is the next big thing. Innovation leader in the space.",
                f"{keyword} just got downgraded. Institutions are fleeing.",
                f"Average down on {keyword}. Adding more shares at these levels.",
                f"{keyword} is a value trap. Don't fall for it.",
                f"Insider buying on {keyword}. Management is confident.",
                f"{keyword} is facing regulatory headwinds. Could get ugly.",
                f"The dividend on {keyword} is safe and growing. Great income stock.",
                f"{keyword} short squeeze potential is real. Float is tiny!",
                f"Sold my {keyword} position. Taking profits off the table.",
                f"{keyword} forming a golden cross. Technical analysis says buy.",
            ]

        mock_posts = []
        for i in range(count):
            text = random.choice(templates)
            mock_posts.append({
                "text": text,
                "author": f"mock_user_{i}",
                "timestamp": f"2025-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
            })

        return mock_posts
