import configparser
import json
import os
import re
import time
from datetime import datetime, timedelta

from openai import OpenAI

from make_dataset import get_data_for_days
from news_analyzer import get_news_articles
from technical_analyzer import technical_analysis
from trade import exe_all_position, get_available_amount, get_price, order_process
from utils import print_log

conf = configparser.ConfigParser()
conf.read("config.ini")
os.environ["OPENAI_API_KEY"] = conf["openai"]["apiKey"]
client = OpenAI()

symbol = "BTC_JPY"
trade_num = 0  # 取引回数
dbname = "sql/trading.db"  # 取引結果を格納するテーブル
exe_type = "MARKET"  # 注文方式(成行)

# -----------------------------Bot本体の処理-----------------------------#
print_log("gmo_ml_botの稼働を開始します", notify=True)
try:
    default_available = int(get_available_amount())  # デフォルトの残高
    previous_available = default_available
except Exception as e:
    print_log(f"残高の取得中にエラーが発生しました: {e}", level="error", notify=True)
    raise

current_time = datetime.now()
hour = current_time.hour


def predict_with_llm(technical_analysis_report, news_articles):
    prompt = f"""
    あなたはプロの仮想通貨トレーダーです。
    以下に示すテクニカル分析結果とニュース記事を基に、1時間後のビットコインの価格動向を論理的かつ具体的に予測してください。

    [ビットコインの時間足チャートに基づくテクニカル分析結果]
    {json.dumps(technical_analysis_report, ensure_ascii=False)}

    [24時間以内のビットコイン関連ニュース記事]
    {json.dumps(news_articles, ensure_ascii=False, indent=2)}

    テクニカル分析とニュース情報の両方を考慮して、総合的な判断を行ってください。
    特に、テクニカル分析とニュース情報から読み取れる市場感情が矛盾する場合は、その理由と、どちらの分析をより重視するかについても説明してください。

    出力は、次のJSON形式に厳密に従って記述してください。
    {{
        "prediction": "bullish/bearish/neutral",
        "confidence": float between 0 and 100,
        "reasoning": "string"
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4.1",
        temperature=0,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )

    return response


while True:
    try:
        current_time = datetime.now()
        if hour != current_time.hour:  # 1時間経過したら取引を行う
            print_log("****************", notify=False)
            try:
                price = get_price()
                print_log(f"現在の{symbol}価格は{price}円です", notify=False)
            except Exception as e:  # メンテナンス時はスキップ
                print_log(
                    f"価格の取得中にエラーが発生しました。メンテナンス中の可能性があります: {e}",
                    level="warning",
                    notify=True,
                )
                hour = current_time.hour
                continue

            # --------ポジションを決済する--------#
            try:
                exe_all_position()
            except Exception as e:
                print_log(
                    f"ポジションの決済中にエラーが発生しました: {e}",
                    level="error",
                    notify=True,
                )
                hour = current_time.hour
                continue

            time.sleep(1)

            if trade_num > 0:
                try:
                    available = int(get_available_amount())
                    profit = available - default_available
                    profit_rate = profit / default_available
                except Exception as e:
                    print_log(
                        f"残高の取得中にエラーが発生しました: {e}",
                        level="error",
                        notify=True,
                    )

                if current_time.hour == 0:
                    daily_profit = available - previous_available
                    print_log(
                        f"{(current_time - timedelta(days=1)).strftime('%Y-%m-%d')}\n損益: {daily_profit}円\n残高: {available}円",
                        notify=True,
                    )
                    previous_available = available

                if profit_rate < -0.2:
                    print_log(
                        f"利益率が -20% を下回りました: {profit_rate}", notify=True
                    )
                    break

            # --------ポジションを決めるための予測を行う--------#
            try:
                if current_time.hour > 6:  # 日本時間朝6：00に新しい日付に切り替わる
                    end_date = current_time.strftime("%Y%m%d")
                else:
                    end_date = (current_time - timedelta(days=1)).strftime("%Y%m%d")

                X = get_data_for_days(
                    symbol=symbol,
                    interval="1hour",
                    end_date=end_date,
                    days=10,
                )

                target_time = (current_time - timedelta(hours=1)).strftime(
                    "%Y-%m-%d %H:00:00"
                )
                if target_time not in X.index:
                    raise ValueError("予測データが存在しません")

                X = X.loc[:target_time]

                technical_analysis_report = technical_analysis(X)
                # prediction = technical_analysis_report["signal"]
                print_log(
                    json.dumps(technical_analysis_report, ensure_ascii=False),
                    notify=False,
                )

                news_articles = get_news_articles()
                print_log(
                    json.dumps(news_articles, ensure_ascii=False, indent=2),
                    notify=False,
                )

                response = predict_with_llm(technical_analysis_report, news_articles)
                response_content = response.choices[0].message.content

                try:
                    # まずJSONパースを試みる
                    response_json = json.loads(response_content)
                    prediction = response_json["prediction"]
                    confidence = response_json["confidence"]
                    reasoning = response_json["reasoning"]
                except json.JSONDecodeError:
                    print_log(
                        f"JSONパースエラーが発生しました。正規表現で抽出を試みます。\nLLMの出力: {response_content}",
                        level="warning",
                        notify=False,
                    )

                    # デフォルト値を設定
                    prediction = "neutral"
                    confidence = 50
                    reasoning = "抽出失敗"

                    # 正規表現で抽出
                    # prediction抽出 (bullish/bearish/neutral)
                    prediction_match = re.search(
                        r'"prediction"[^\w]*:?[^\w]*"(bullish|bearish|neutral)"',
                        response_content,
                        re.IGNORECASE,
                    )
                    if prediction_match:
                        prediction = prediction_match.group(1).lower()

                    # confidence抽出 (0-100の数値)
                    confidence_match = re.search(
                        r'"confidence"[^\w]*:?[^\w]*(\d+(?:\.\d+)?)', response_content
                    )
                    if confidence_match:
                        try:
                            confidence = float(confidence_match.group(1))
                        except ValueError:
                            pass

                    # reasoning抽出 (引用符で囲まれた文字列)
                    reasoning_match = re.search(
                        r'"reasoning"[^\w]*:?[^\w]*"([^"]*)"', response_content
                    )
                    if reasoning_match:
                        reasoning = reasoning_match.group(1)

                print_log(
                    f"予測結果: {prediction}\n信頼度: {confidence}\n理由: {reasoning}",
                    notify=False,
                )

                if prediction == "bullish":
                    side = "BUY"
                    hour = current_time.hour
                elif prediction == "bearish":
                    side = "SELL"
                    hour = current_time.hour
                elif prediction == "neutral":
                    hour = current_time.hour
                    continue
                else:
                    raise ValueError("予測結果が不正です")
            except Exception as e:
                print_log(
                    f"予測中にエラーが発生しました: {e}", level="error", notify=True
                )
                hour = current_time.hour
                continue

            # --------注文を出す--------#
            try:
                order_process(
                    symbol=symbol, side=side, executionType=exe_type, size=0.01
                )
                trade_num += 1
            except Exception as e:
                print_log(
                    f"注文中にエラーが発生しました: {e}", level="error", notify=True
                )
                continue

        else:
            remaining_minutes = 60 - current_time.minute
            sleep_time = 60 * remaining_minutes
            print_log(f"{remaining_minutes}分スリープします", notify=False)
            time.sleep(sleep_time)
    except Exception as e:
        print_log(f"想定外のエラーが発生しました: {e}", level="error", notify=True)
        break

print_log("gmo_ml_botの稼働を終了します", notify=True)
