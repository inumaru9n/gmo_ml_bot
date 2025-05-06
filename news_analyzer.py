import datetime
import re

import feedparser

from utils import print_log


def fetch_rss_feed(url):
    """
    RSSフィードからニュース記事を取得する関数

    Args:
        url: RSSフィードのURL

    Returns:
        list: ニュース記事のリスト（タイトル、リンク、説明、公開日時を含む辞書）
    """
    try:
        # RSSフィードを取得
        feed = feedparser.parse(url)

        # 記事を格納するリスト
        articles = []

        # 現在の日時
        now = datetime.datetime.now()

        # 24時間前の日時
        day_ago = now - datetime.timedelta(hours=24)

        # 各記事の情報を取得
        for entry in feed.entries:
            title = entry.title if hasattr(entry, "title") else ""
            link = entry.link if hasattr(entry, "link") else ""
            description = entry.description if hasattr(entry, "description") else ""

            # pubDateを解析
            pub_date = None
            if hasattr(entry, "published_parsed"):
                pub_date = datetime.datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed"):
                pub_date = datetime.datetime(*entry.updated_parsed[:6])

            pub_date_str = entry.published if hasattr(entry, "published") else ""

            # 24時間以内の記事のみを対象とする
            if pub_date and pub_date > day_ago:
                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "description": clean_html(description),
                        "pub_date": pub_date_str,
                    }
                )

        return articles
    except Exception as e:
        print_log(f"RSSフィードの取得中にエラーが発生しました: {e}", level="error")
        return []


def clean_html(html_text):
    """
    HTMLタグを除去する関数

    Args:
        html_text: HTMLタグを含むテキスト

    Returns:
        str: HTMLタグを除去したテキスト
    """
    if not html_text:
        return ""

    # HTMLタグを除去
    clean_text = re.sub(r"<.*?>", "", html_text)

    # 連続する空白を1つの空白に置換
    clean_text = re.sub(r"\s+", " ", clean_text)

    return clean_text.strip()


def get_news_articles(rss_url="https://jp.cointelegraph.com/rss/tag/bitcoin"):
    """
    RSSフィードからニュース記事を取得する関数

    Args:
        rss_url: RSSフィードのURL

    Returns:
        list: ニュース記事のリスト
    """
    # RSSフィードからニュース記事を取得
    articles = fetch_rss_feed(rss_url)

    # 最新の5記事のみを返す
    return articles[:5]


if __name__ == "__main__":
    # テスト用コード
    articles = get_news_articles()
    for article in articles:
        print(f"タイトル: {article['title']}")
        print(f"リンク: {article['link']}")
        print(f"内容: {article['description']}")
        print(f"公開日時: {article['pub_date']}")
        print("---")
