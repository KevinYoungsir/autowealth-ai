"""
情绪词典模块 - 提供中英文正面/负面情绪词典及停用词表。
"""

# ============================================================
# 英文正面词列表
# ============================================================
POSITIVE_WORDS_EN = {
    "good", "great", "excellent", "amazing", "wonderful", "fantastic",
    "awesome", "outstanding", "brilliant", "superb", "perfect", "love",
    "happy", "joy", "beautiful", "nice", "best", "better", "positive",
    "success", "successful", "win", "winner", "profit", "profitable",
    "growth", "grow", "growing", "gain", "bull", "bullish", "rally",
    "surge", "soar", "boom", "thrive", "thriving", "strong", "strength",
    "improve", "improvement", "rise", "rising", "up", "upward", "boost",
    "opportunity", "optimistic", "optimism", "confident", "confidence",
    "breakthrough", "innovation", "innovative", "leading", "leader",
    "dominant", "dominate", "impressive", "remarkable", "exceptional",
    "solid", "stable", "reliable", "trust", "trusted", "valuable",
    "value", "undervalued", "cheap", "bargain", "dividend", "yield",
    "momentum", "upgrade", "buy", "long", "outperform", "outperforming",
    "beat", "beating", "exceed", "exceeded", "record", "high",
    "all-time high", " ATH", "moon", "diamond", "hands", "to the moon",
    "lambo", "rocket", "green", "pump", "pumping", "hodl", "accumulate",
    "accumulation", "support", "resistance breakout", "golden cross",
    "recovery", "recover", "rebound", "bounce", "bounce back",
}

# ============================================================
# 英文负面词列表
# ============================================================
NEGATIVE_WORDS_EN = {
    "bad", "terrible", "horrible", "awful", "worst", "poor", "negative",
    "fail", "failure", "lose", "losing", "loss", "loser", "crash",
    "crashing", "drop", "dropping", "fall", "falling", "decline",
    "declining", "down", "downward", "bear", "bearish", "dump", "dumping",
    "plunge", "plunging", "collapse", "collapsing", "panic", "fear",
    "scared", "worry", "worried", "risk", "risky", "danger", "dangerous",
    "threat", "threaten", "crisis", "recession", "depression", "inflation",
    "debt", "bankrupt", "bankruptcy", "fraud", "scam", "manipulation",
    "manipulate", "overvalued", "expensive", "bubble", "burst", "bursting",
    "weak", "weakness", "volatile", "volatility", "uncertain", "uncertainty",
    "unstable", "unreliable", "disappoint", "disappointing", "disappointed",
    "miss", "missed", "below", "downgrade", "sell", "selling", "short",
    "shorting", "underperform", "underperforming", "warning", "alert",
    "concern", "concerned", "trouble", "problem", "issue", "negative",
    "pessimistic", "pessimism", "doubt", "skeptical", "skepticism",
    "red", "blood", "rekt", "liquidation", "liquidated", "margin call",
    "stop loss", "cut losses", "bagholder", "rug pull", "ponzi",
    "delist", "delisted", "hack", "hacked", "exploit", "vulnerability",
    "regulation", "ban", "banned", "restrict", "restricted", "sanction",
    "investigation", "investigate", "probe", "audit", "lawsuit", "SEC",
    "fine", "penalty", "illegal", "seize", "frozen", "freeze",
}

# ============================================================
# 中文正面词列表
# ============================================================
POSITIVE_WORDS_CN = {
    "好", "很好", "不错", "优秀", "出色", "卓越", "极好", "完美",
    "喜欢", "爱", "开心", "高兴", "快乐", "美丽", "漂亮", "赞",
    "牛", "厉害", "强大", "稳定", "可靠", "信任", "增长", "涨",
    "上涨", "拉升", "暴涨", "飙升", "突破", "新高", "历史新高",
    "盈利", "赚钱", "利润", "收益", "回报", "分红", "红利",
    "看好", "乐观", "信心", "强势", "强劲", "支撑", "反弹",
    "回升", "复苏", "恢复", "好转", "改善", "进步", "发展",
    "繁荣", "兴旺", "成功", "胜利", "领先", "优势", "机会",
    "潜力", "低估", "便宜", "价值", "优质", "蓝筹", "龙头",
    "买入", "做多", "持有", "加仓", "建仓", "抄底", "囤积",
    "利好", "好消息", "正面", "积极", "正面消息", "利好消息",
    "牛市", "多头", "翻倍", "暴涨", "大涨", "红盘", "涨停",
    "金叉", "突破阻力", "放量上涨", "均线多头", "趋势向好",
    "基本面好", "业绩增长", "超预期", "不及预期", "符合预期",
    "推荐", "强烈推荐", "增持", "超配", "跑赢", "跑赢大盘",
}

# ============================================================
# 中文负面词列表
# ============================================================
NEGATIVE_WORDS_CN = {
    "坏", "差", "糟糕", "恶劣", "最差", "垃圾", "烂", "渣",
    "不喜欢", "讨厌", "恨", "难过", "伤心", "失望", "愤怒",
    "跌", "下跌", "暴跌", "崩盘", "崩塌", "大跌", "跳水",
    "暴跌", "暴跌", "阴跌", "持续下跌", "破位", "跌破",
    "亏损", "亏钱", "赔钱", "损失", "套牢", "被套", "深套",
    "看空", "悲观", "恐慌", "害怕", "担心", "忧虑", "焦虑",
    "弱势", "疲软", "乏力", "压力", "阻力", "跌破支撑",
    "风险", "危险", "危机", "衰退", "萧条", "泡沫", "泡沫破裂",
    "债务", "违约", "破产", "倒闭", "欺诈", "骗局", "诈骗",
    "操纵", "内幕", "造假", "财务造假", "虚增",
    "高估", "贵", "溢价", "泡沫", "过热", "不稳定", "不确定",
    "利空", "坏消息", "负面", "消极", "利空消息",
    "熊市", "空头", "做空", "减仓", "清仓", "止损", "割肉",
    "暴跌", "跌停", "绿盘", "死叉", "放量下跌", "均线空头",
    "趋势恶化", "基本面差", "业绩下滑", "不及预期",
    "减持", "抛售", "砸盘", "跑路", "爆仓", "强平", "爆雷",
    "退市", "停牌", "监管", "处罚", "罚款", "调查", "立案",
    "违规", "违法", "冻结", "查封", "黑天鹅", "灰犀牛",
    "骗局", "割韭菜", "庄家", "杀跌", "踩踏", "恐慌性抛售",
}

# ============================================================
# 英文停用词
# ============================================================
STOP_WORDS_EN = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his",
    "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which",
    "who", "whom", "this", "that", "these", "those", "am", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
    "or", "because", "as", "until", "while", "of", "at", "by", "for",
    "with", "about", "against", "between", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "s", "t", "can",
    "will", "just", "don", "should", "now", "d", "ll", "m", "o", "re",
    "ve", "y", "ain", "aren", "couldn", "didn", "doesn", "hadn", "hasn",
    "haven", "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn",
    "wasn", "weren", "won", "wouldn",
    # 社交媒体常见词
    "https", "http", "www", "com", "org", "net", "like", "get", "got",
    "would", "could", "one", "also", "much", "many", "way", "still",
    "even", "well", "back", "make", "made", "know", "think", "see",
    "say", "said", "go", "going", "come", "came", "take", "took",
    "really", "thing", "things", "something", "anything", "everything",
    "nothing", "people", "time", "day", "new", "old", "first", "last",
    "long", "great", "right", "big", "little", "lot", "let",
}

# ============================================================
# 中文停用词
# ============================================================
STOP_WORDS_CN = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
    "那", "个", "吗", "吧", "呢", "啊", "哦", "嗯", "呀", "哈",
    "把", "被", "让", "给", "从", "对", "向", "以", "为", "但",
    "而", "且", "或", "如果", "因为", "所以", "虽然", "但是", "不过",
    "可以", "能", "能够", "应该", "可能", "已经", "正在", "将",
    "还", "又", "再", "才", "只", "更", "最", "非常", "比较",
    "什么", "怎么", "哪", "哪里", "为什么", "多少", "几",
    "这个", "那个", "这些", "那些", "自己", "什么", "怎么",
    "我们", "你们", "他们", "她们", "它们",
    "得", "地", "过", "来", "去", "起", "下", "中", "里", "外",
    "前", "后", "时", "时候", "年", "月", "日", "号", "点",
    "大", "小", "多", "少", "第", "每", "各", "某", "该",
    "其", "此", "之", "所", "等", "等等", "么", "啦", "呗",
    "呢", "嘛", "呗", "罢了", "而已", "一般", "一起", "一直",
    "一下", "一些", "一样", "一次", "一直", "于是", "然后",
    "接着", "总之", "另外", "此外", "同时", "并且", "以及",
    "或者", "还是", "关于", "通过", "根据", "按照", "随着",
    "除了", "由于", "对于", "至于", "尽管", "即使", "无论",
    "只要", "只有", "除非", "假如", "倘若", "既然", "因而",
    "从而", "不过", "然而", "可是", "但是", "虽然", "尽管",
    # 社交媒体常见词
    "转发", "评论", "回复", "分享", "链接", "视频", "图片", "照片",
    "点击", "查看", "详情", "全文", "网页", "微博", "搜索",
}


def get_sentiment_words(language="en"):
    """
    获取指定语言的正面和负面情绪词典。

    Args:
        language: 语言代码，"en" 表示英文，"cn" 表示中文。

    Returns:
        dict: 包含 "positive" 和 "negative" 键的字典，值为词集合。
    """
    if language == "cn":
        return {
            "positive": POSITIVE_WORDS_CN,
            "negative": NEGATIVE_WORDS_CN,
            "stop_words": STOP_WORDS_CN,
        }
    else:
        return {
            "positive": POSITIVE_WORDS_EN,
            "negative": NEGATIVE_WORDS_EN,
            "stop_words": STOP_WORDS_EN,
        }
