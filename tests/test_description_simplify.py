#!/usr/bin/env python3
"""
测试视频描述简化功能
"""

import re

import pytest


def simplify_video_description(description: str, max_length: int = 300) -> str:
    """
    简化视频描述，去除多余的链接和重复内容

    Args:
        description: 原始视频描述
        max_length: 简化后的最大长度

    Returns:
        简化后的描述
    """
    if not description:
        return ""

    # 移除多余的空白字符
    text = re.sub(r"\s+", " ", description.strip())

    # 移除URL链接
    text = re.sub(r"https?://[^\s]+", "", text)

    # 移除常见的社交媒体标签和提醒
    patterns_to_remove = [
        r"关注我们?[：:].*?(?=\n|$)",
        r"订阅[：:].*?(?=\n|$)",
        r"点赞.*?(?=\n|$)",
        r"转发.*?(?=\n|$)",
        r"微博[：:].*?(?=\n|$)",
        r"微信[：:].*?(?=\n|$)",
        r"QQ群[：:].*?(?=\n|$)",
        r"官方.*?群[：:].*?(?=\n|$)",
        r"更多.*?关注.*?(?=\n|$)",
        r"欢迎.*?关注.*?(?=\n|$)",
        r"Follow.*?(?=\n|$)",
        r"Subscribe.*?(?=\n|$)",
        r"Like.*?(?=\n|$)",
        r"@\w+",  # 移除@用户名
        r"#\w+",  # 移除话题标签
    ]

    for pattern in patterns_to_remove:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # 移除重复的句子或短语
    sentences = re.split(r"[。！？\n]", text)
    unique_sentences = []
    seen = set()

    for original_sentence in sentences:
        stripped_sentence = original_sentence.strip()
        if stripped_sentence and len(stripped_sentence) > 10:  # 忽略太短的句子
            # 简单的去重逻辑
            sentence_key = re.sub(r"[^\w\u4e00-\u9fff]", "", stripped_sentence.lower())
            if sentence_key not in seen:
                seen.add(sentence_key)
                unique_sentences.append(stripped_sentence)

    # 重新组合文本
    simplified = "。".join(unique_sentences[:3])  # 最多保留3个主要句子

    # 最终长度控制
    if len(simplified) > max_length:
        simplified = simplified[:max_length] + "..."

    return simplified.strip() or "简介信息已简化"


class TestDescriptionSimplification:
    """测试视频描述简化功能"""

    def test_simplify_description_with_links_and_social_media(self):
        """测试包含链接和社交媒体标签的描述"""
        description = """lidang 立党 （全网劝人卖房、劝人学CS、劝人买SP500和NASDAQ100第一人） - 什么叫菀菀类卿？  这个女人长得99%复刻郭老师，还拿郭老师的语音配音对口型，经常让人误以为郭老师回来了，仔细一看，原来只是长得像。  像不像是一回事，但别让人误会。还是不要利用郭老师的语音和造型去恰烂钱了，毕竟郭老师不在了。
关注我们：https://twitter.com/lidangzzz
微博：@立党今天买什么
QQ群：123456789
#股票 #投资 @某用户"""

        result = simplify_video_description(description)

        # 验证链接被移除
        assert "https://twitter.com" not in result
        # 验证社交媒体标签被移除
        assert "@某用户" not in result
        assert "#股票" not in result
        # 验证长度合理
        assert len(result) <= 300
        # 验证核心内容保留
        assert "立党" in result
        assert "郭老师" in result

    def test_simplify_description_with_repetitive_content(self):
        """测试重复内容的描述"""
        description = """这是一个测试视频。这是一个测试视频。内容很精彩。内容很精彩。请大家点赞关注。请大家点赞关注。
订阅：https://youtube.com/example
微信：test123
更多精彩内容请关注我们的频道"""

        result = simplify_video_description(description)

        # 重复内容应该被去重或简化为默认信息
        assert result == "简介信息已简化" or "测试视频" in result
        assert len(result) <= 300

    def test_simplify_normal_description(self):
        """测试正常描述"""
        description = """今天我们来讲解Python编程的基础知识。这节课主要介绍变量和数据类型。希望大家能够认真学习，有问题可以在评论区留言。"""

        result = simplify_video_description(description)

        # 正常描述应该基本保持不变
        assert "Python编程" in result
        assert "变量和数据类型" in result
        assert len(result) <= 300

    def test_simplify_empty_description(self):
        """测试空描述"""
        result = simplify_video_description("")
        assert result == ""

    def test_simplify_description_max_length(self):
        """测试最大长度限制"""
        long_description = "这是一个很长的视频描述，包含了很多重要的信息。我们需要确保它能够被正确地截断到指定的长度。这里有更多的内容来确保超过长度限制。"
        result = simplify_video_description(long_description, max_length=50)

        assert len(result) <= 53  # 50 + "..."
        # 对于正常内容（非重复），应该会被截断并添加省略号
        if result != "简介信息已简化":
            assert result.endswith("...")

    def test_simplify_description_only_urls(self):
        """测试只包含URL的描述"""
        description = """https://example.com/video1 https://youtube.com/watch https://twitter.com/user"""
        result = simplify_video_description(description)

        # 应该返回默认信息，因为没有有效内容
        assert result == "简介信息已简化"


if __name__ == "__main__":
    # 兼容直接运行
    pytest.main([__file__, "-v"])
