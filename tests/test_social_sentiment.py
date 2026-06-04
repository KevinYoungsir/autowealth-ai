"""
社交情绪分析模块测试。

覆盖：英文/中文文本情绪分析、关键词提取、
Twitter/微博/Reddit 分析接口（mock）、多平台情绪合并、
空文本处理、混合语言文本等场景。
"""

import pytest

from autowealth.sentiment.social_analyzer import SocialSentimentAnalyzer
from autowealth.sentiment.dictionary import (
    POSITIVE_WORDS_EN,
    NEGATIVE_WORDS_EN,
    POSITIVE_WORDS_CN,
    NEGATIVE_WORDS_CN,
    STOP_WORDS_EN,
    STOP_WORDS_CN,
    get_sentiment_words,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def analyzer():
    """创建 SocialSentimentAnalyzer 实例。"""
    return SocialSentimentAnalyzer()


# ============================================================
# 英文文本情绪分析测试
# ============================================================

class TestEnglishSentiment:
    """英文文本情绪分析测试。"""

    def test_positive_english_text(self, analyzer):
        """测试正面英文文本。"""
        text = "This stock is amazing! Great growth and excellent profit. Bullish outlook!"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "positive"
        assert result["score"] > 0.5

    def test_negative_english_text(self, analyzer):
        """测试负面英文文本。"""
        text = "Terrible performance. The stock is crashing, huge losses and bearish trend."
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "negative"
        assert result["score"] < 0.5

    def test_neutral_english_text(self, analyzer):
        """测试中性英文文本。"""
        text = "The stock price moved slightly today. Trading volume was average."
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "neutral"
        assert result["score"] == 0.5

    def test_strongly_positive_english(self, analyzer):
        """测试强烈正面英文文本。"""
        text = "Outstanding brilliant fantastic amazing wonderful superb excellent great awesome"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "positive"
        assert result["score"] == 1.0

    def test_strongly_negative_english(self, analyzer):
        """测试强烈负面英文文本。"""
        text = "Terrible horrible awful worst bad poor failure crash collapse scam fraud"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "negative"
        assert result["score"] == 0.0

    def test_mixed_english_sentiment(self, analyzer):
        """测试混合情绪英文文本。"""
        # good(正面), growth(正面), terrible(负面), management(无), losses(负面), profit(正面), crash(负面)
        # 正面3个 vs 负面3个 -> neutral
        text = "Good growth but terrible management. Losses reported but profit up. Crash risk exists."
        result = analyzer._analyze_text_sentiment(text)
        # 混合情绪应返回 neutral（正面和负面词数量相等）
        assert result["label"] == "neutral"
        assert 0.0 <= result["score"] <= 1.0


# ============================================================
# 中文文本情绪分析测试
# ============================================================

class TestChineseSentiment:
    """中文文本情绪分析测试。"""

    def test_positive_chinese_text(self, analyzer):
        """测试正面中文文本。"""
        text = "这只股票表现非常出色，业绩增长超预期，强势上涨！"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "positive"
        assert result["score"] > 0.5

    def test_negative_chinese_text(self, analyzer):
        """测试负面中文文本。"""
        text = "太糟糕了，股价暴跌，亏损严重，崩盘风险很大。"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "negative"
        assert result["score"] < 0.5

    def test_neutral_chinese_text(self, analyzer):
        """测试中性中文文本。"""
        text = "今天股票价格变化不大，成交量一般。"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "neutral"
        assert result["score"] == 0.5

    def test_strongly_positive_chinese(self, analyzer):
        """测试强烈正面中文文本。"""
        text = "优秀出色卓越极好完美厉害强大稳定可靠增长上涨暴涨飙升盈利赚钱利好牛市翻倍"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "positive"
        assert result["score"] > 0.5

    def test_strongly_negative_chinese(self, analyzer):
        """测试强烈负面中文文本。"""
        text = "糟糕恶劣垃圾差亏损亏钱暴跌崩盘暴跌暴跌套牢恐慌悲观风险危机泡沫骗局欺诈"
        result = analyzer._analyze_text_sentiment(text)
        assert result["label"] == "negative"
        assert result["score"] < 0.5


# ============================================================
# 空文本和边界情况测试
# ============================================================

class TestEdgeCases:
    """边界情况和异常输入测试。"""

    def test_empty_string(self, analyzer):
        """测试空字符串。"""
        result = analyzer._analyze_text_sentiment("")
        assert result["score"] == 0.5
        assert result["label"] == "neutral"

    def test_whitespace_only(self, analyzer):
        """测试仅包含空白字符的文本。"""
        result = analyzer._analyze_text_sentiment("   \n\t  ")
        assert result["score"] == 0.5
        assert result["label"] == "neutral"

    def test_none_like_empty(self, analyzer):
        """测试通过空字符串模拟 None 输入。"""
        result = analyzer._analyze_text_sentiment("")
        assert result["score"] == 0.5
        assert result["label"] == "neutral"

    def test_single_positive_word(self, analyzer):
        """测试单个正面词。"""
        result = analyzer._analyze_text_sentiment("good")
        assert result["label"] == "positive"
        assert result["score"] == 1.0

    def test_single_negative_word(self, analyzer):
        """测试单个负面词。"""
        result = analyzer._analyze_text_sentiment("bad")
        assert result["label"] == "negative"
        assert result["score"] == 0.0

    def test_mixed_language_text(self, analyzer):
        """测试中英文混合文本。"""
        text = "AAPL表现amazing，业绩增长excellent，但是风险也很大，要注意crash风险。"
        result = analyzer._analyze_text_sentiment(text)
        assert "score" in result
        assert "label" in result
        assert result["label"] in ("positive", "negative", "neutral")
        assert 0.0 <= result["score"] <= 1.0


# ============================================================
# 关键词提取测试
# ============================================================

class TestKeywordExtraction:
    """关键词提取测试。"""

    def test_extract_english_keywords(self, analyzer):
        """测试英文关键词提取。"""
        texts = [
            "Apple stock is going up today with strong momentum",
            "Apple earnings beat expectations and the stock rallied",
            "Investors are bullish on Apple stock right now",
        ]
        keywords = analyzer._extract_keywords(texts)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # "stock" 和 "apple" 应该出现
        keyword_words = [kw["word"] for kw in keywords]
        assert "apple" in keyword_words
        assert "stock" in keyword_words

    def test_extract_chinese_keywords(self, analyzer):
        """测试中文关键词提取。"""
        texts = [
            "贵州茅台今天大涨，白酒板块表现强势",
            "贵州茅台业绩超预期，机构看好后市",
            "投资者看好贵州茅台长期价值",
        ]
        keywords = analyzer._extract_keywords(texts)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        keyword_words = [kw["word"] for kw in keywords]
        # "贵州茅台" 应该出现
        assert "贵州茅台" in keyword_words

    def test_extract_keywords_empty_texts(self, analyzer):
        """测试空文本列表的关键词提取。"""
        keywords = analyzer._extract_keywords([])
        assert keywords == []

    def test_extract_keywords_top_n(self, analyzer):
        """测试限制返回关键词数量。"""
        texts = [
            "stock market analysis trading investment portfolio",
            "stock market trends trading strategy analysis",
        ]
        keywords = analyzer._extract_keywords(texts, top_n=3)
        assert len(keywords) <= 3

    def test_extract_keywords_with_stopwords(self, analyzer):
        """测试停用词过滤。"""
        texts = [
            "The stock is good and the market is going up",
            "I think the stock will be great",
        ]
        keywords = analyzer._extract_keywords(texts)
        keyword_words = [kw["word"] for kw in keywords]
        # 停用词 "the", "is", "and", "i" 不应出现在结果中
        for stop_word in ["the", "is", "and", "i"]:
            assert stop_word not in keyword_words

    def test_keyword_count_field(self, analyzer):
        """测试关键词包含正确的 count 字段。"""
        texts = ["stock stock stock market market"]
        keywords = analyzer._extract_keywords(texts)
        assert len(keywords) > 0
        for kw in keywords:
            assert "word" in kw
            assert "count" in kw
            assert isinstance(kw["count"], int)
            assert kw["count"] > 0


# ============================================================
# Twitter 分析接口测试（mock）
# ============================================================

class TestTwitterAnalysis:
    """Twitter/X 情绪分析接口测试。"""

    def test_twitter_analysis_returns_correct_structure(self, analyzer):
        """测试 Twitter 分析返回正确的数据结构。"""
        result = analyzer.analyze_twitter("AAPL", count=50)
        assert result["platform"] == "twitter"
        assert result["symbol"] == "AAPL"
        assert result["total"] == 50
        assert "positive" in result
        assert "negative" in result
        assert "neutral" in result
        assert "score" in result
        assert "top_keywords" in result

    def test_twitter_analysis_counts_sum(self, analyzer):
        """测试 Twitter 分析中正面+负面+中性等于总数。"""
        result = analyzer.analyze_twitter("TSLA", count=30)
        assert result["positive"] + result["negative"] + result["neutral"] == result["total"]

    def test_twitter_analysis_score_range(self, analyzer):
        """测试 Twitter 分析分数在合理范围内。"""
        result = analyzer.analyze_twitter("MSFT", count=100)
        assert 0.0 <= result["score"] <= 1.0

    def test_twitter_analysis_keywords(self, analyzer):
        """测试 Twitter 分析返回关键词列表。"""
        result = analyzer.analyze_twitter("GOOGL", count=50)
        assert isinstance(result["top_keywords"], list)
        assert len(result["top_keywords"]) > 0
        for kw in result["top_keywords"]:
            assert "word" in kw
            assert "count" in kw


# ============================================================
# 微博分析接口测试（mock）
# ============================================================

class TestWeiboAnalysis:
    """微博情绪分析接口测试。"""

    def test_weibo_analysis_returns_correct_structure(self, analyzer):
        """测试微博分析返回正确的数据结构。"""
        result = analyzer.analyze_weibo("贵州茅台", count=50)
        assert result["platform"] == "weibo"
        assert result["symbol"] == "贵州茅台"
        assert result["total"] == 50
        assert "positive" in result
        assert "negative" in result
        assert "neutral" in result
        assert "score" in result
        assert "top_keywords" in result

    def test_weibo_analysis_counts_sum(self, analyzer):
        """测试微博分析中正面+负面+中性等于总数。"""
        result = analyzer.analyze_weibo("A股", count=30)
        assert result["positive"] + result["negative"] + result["neutral"] == result["total"]

    def test_weibo_analysis_score_range(self, analyzer):
        """测试微博分析分数在合理范围内。"""
        result = analyzer.analyze_weibo("比亚迪", count=100)
        assert 0.0 <= result["score"] <= 1.0


# ============================================================
# Reddit 分析接口测试（mock）
# ============================================================

class TestRedditAnalysis:
    """Reddit 情绪分析接口测试。"""

    def test_reddit_analysis_returns_correct_structure(self, analyzer):
        """测试 Reddit 分析返回正确的数据结构。"""
        result = analyzer.analyze_reddit(subreddit="wallstreetbets", keyword="GME", count=50)
        assert result["platform"] == "reddit"
        assert result["symbol"] == "GME"
        assert result["subreddit"] == "wallstreetbets"
        assert result["total"] == 50
        assert "positive" in result
        assert "negative" in result
        assert "neutral" in result
        assert "score" in result
        assert "top_keywords" in result

    def test_reddit_analysis_default_subreddit(self, analyzer):
        """测试 Reddit 分析默认子版块。"""
        result = analyzer.analyze_reddit(keyword="BTC")
        assert result["subreddit"] == "wallstreetbets"
        assert result["symbol"] == "BTC"

    def test_reddit_analysis_no_keyword(self, analyzer):
        """测试 Reddit 分析无关键词时使用子版块名。"""
        result = analyzer.analyze_reddit(subreddit="stocks")
        assert result["symbol"] == "stocks"

    def test_reddit_analysis_counts_sum(self, analyzer):
        """测试 Reddit 分析中正面+负面+中性等于总数。"""
        result = analyzer.analyze_reddit(subreddit="crypto", keyword="ETH", count=30)
        assert result["positive"] + result["negative"] + result["neutral"] == result["total"]


# ============================================================
# 多平台情绪合并测试
# ============================================================

class TestCombinedSentiment:
    """多平台情绪合并测试。"""

    def test_combined_sentiment_structure(self, analyzer):
        """测试合并情绪报告的数据结构。"""
        twitter = analyzer.analyze_twitter("AAPL", count=50)
        weibo = analyzer.analyze_weibo("苹果", count=50)
        reddit = analyzer.analyze_reddit(subreddit="stocks", keyword="AAPL", count=50)

        combined = analyzer.get_combined_sentiment([twitter, weibo, reddit])

        assert "combined_score" in combined
        assert "label" in combined
        assert "total_platforms" in combined
        assert "total_posts" in combined
        assert "total_positive" in combined
        assert "total_negative" in combined
        assert "total_neutral" in combined
        assert "platform_details" in combined
        assert "top_keywords" in combined

    def test_combined_sentiment_platform_count(self, analyzer):
        """测试合并情绪报告的平台数量。"""
        twitter = analyzer.analyze_twitter("TSLA", count=20)
        weibo = analyzer.analyze_weibo("特斯拉", count=20)

        combined = analyzer.get_combined_sentiment([twitter, weibo])
        assert combined["total_platforms"] == 2

    def test_combined_sentiment_score_range(self, analyzer):
        """测试合并情绪分数在合理范围内。"""
        twitter = analyzer.analyze_twitter("MSFT", count=50)
        reddit = analyzer.analyze_reddit(subreddit="stocks", keyword="MSFT", count=50)

        combined = analyzer.get_combined_sentiment([twitter, reddit])
        assert 0.0 <= combined["combined_score"] <= 1.0

    def test_combined_sentiment_label(self, analyzer):
        """测试合并情绪标签是有效值。"""
        twitter = analyzer.analyze_twitter("NVDA", count=50)
        weibo = analyzer.analyze_weibo("英伟达", count=50)
        reddit = analyzer.analyze_reddit(subreddit="wallstreetbets", keyword="NVDA", count=50)

        combined = analyzer.get_combined_sentiment([twitter, weibo, reddit])
        assert combined["label"] in ("positive", "negative", "neutral")

    def test_combined_sentiment_empty_results(self, analyzer):
        """测试空结果列表的合并。"""
        combined = analyzer.get_combined_sentiment([])
        assert combined["combined_score"] == 0.5
        assert combined["label"] == "neutral"
        assert combined["total_platforms"] == 0
        assert combined["total_posts"] == 0

    def test_combined_sentiment_single_platform(self, analyzer):
        """测试单平台结果合并。"""
        twitter = analyzer.analyze_twitter("GOOGL", count=50)
        combined = analyzer.get_combined_sentiment([twitter])
        assert combined["total_platforms"] == 1
        assert combined["combined_score"] == twitter["score"]

    def test_combined_platform_details_weights(self, analyzer):
        """测试平台详情包含权重信息。"""
        twitter = analyzer.analyze_twitter("AMZN", count=30)
        weibo = analyzer.analyze_weibo("亚马逊", count=30)
        reddit = analyzer.analyze_reddit(subreddit="stocks", keyword="AMZN", count=30)

        combined = analyzer.get_combined_sentiment([twitter, weibo, reddit])

        for detail in combined["platform_details"]:
            assert "weight" in detail
            assert "platform" in detail
            assert "score" in detail
            assert 0.0 < detail["weight"] <= 1.0


# ============================================================
# 词典模块测试
# ============================================================

class TestDictionary:
    """情绪词典模块测试。"""

    def test_positive_words_en_count(self):
        """测试英文正面词数量不少于50个。"""
        assert len(POSITIVE_WORDS_EN) >= 50

    def test_negative_words_en_count(self):
        """测试英文负面词数量不少于50个。"""
        assert len(NEGATIVE_WORDS_EN) >= 50

    def test_positive_words_cn_count(self):
        """测试中文正面词数量不少于50个。"""
        assert len(POSITIVE_WORDS_CN) >= 50

    def test_negative_words_cn_count(self):
        """测试中文负面词数量不少于50个。"""
        assert len(NEGATIVE_WORDS_CN) >= 50

    def test_stop_words_en_not_empty(self):
        """测试英文停用词不为空。"""
        assert len(STOP_WORDS_EN) > 0

    def test_stop_words_cn_not_empty(self):
        """测试中文停用词不为空。"""
        assert len(STOP_WORDS_CN) > 0

    def test_get_sentiment_words_english(self):
        """测试获取英文词典。"""
        words = get_sentiment_words("en")
        assert "positive" in words
        assert "negative" in words
        assert "stop_words" in words
        assert isinstance(words["positive"], set)
        assert isinstance(words["negative"], set)

    def test_get_sentiment_words_chinese(self):
        """测试获取中文词典。"""
        words = get_sentiment_words("cn")
        assert "positive" in words
        assert "negative" in words
        assert "stop_words" in words
        assert isinstance(words["positive"], set)
        assert isinstance(words["negative"], set)

    def test_get_sentiment_words_default(self):
        """测试默认获取英文词典。"""
        words = get_sentiment_words()
        assert "positive" in words
        assert "negative" in words
