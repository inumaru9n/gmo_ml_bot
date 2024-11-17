import os
import pickle
import sqlite3
import time
from datetime import datetime, timedelta

import pandas as pd

from make_dataset import calc_features, get_data_for_days
from trade import (
    exe_all_position,
    get_available_amount,
    get_price,
    get_trading_result,
    order_process,
)
from utils import print_log

symbol = "BTC_JPY"
trade_num = 0  # 取引回数
result_df = pd.DataFrame(
    columns=["id", "date", "position", "order_price", "close_price", "loss_gain"]
)  # 取引結果を格納するデータフレーム
dbname = "sql/trading.db"  # 取引結果を格納するテーブル
exe_type = "MARKET"  # 注文方式(成行)


# -----------------------------Bot本体の処理-----------------------------#
print_log("gmo_ml_botの稼働を開始します", notify=True)

try:
    with open(os.path.join("models", "model.pkl"), "rb") as f:
        model = pickle.load(f)
except Exception as e:
    print_log(
        f"モデルの読み込み中にエラーが発生しました: {e}", level="error", notify=True
    )
    raise

try:
    conn = sqlite3.connect(dbname)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trading (
            trade_id INTEGER,
            date STRING,
            position INTEGER,
            order_price INTEGER,
            close_price INTEGER,
            loss_gain INTEGER
        )
        """
    )
except Exception as e:
    print_log(
        f"データベースの接続中にエラーが発生しました: {e}", level="error", notify=True
    )
    raise

try:
    default_available = int(get_available_amount())  # デフォルトの残高
except Exception as e:
    print_log(f"残高の取得中にエラーが発生しました: {e}", level="error", notify=True)
    raise

current_time = datetime.now()
hour = current_time.hour

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

            try:
                exe_all_position()  # ポジションを決済
            except Exception as e:
                print_log(
                    f"ポジションの決済中にエラーが発生しました: {e}",
                    level="error",
                    notify=True,
                )
                hour = current_time.hour
                continue

            # --------ポジションを決めるための予測を行う--------#
            try:
                if current_time.hour > 6:  # 日本時間朝6：00に新しい日付に切り替わる
                    end_date = current_time.strftime("%Y%m%d")
                else:
                    end_date = (current_time - timedelta(days=1)).strftime("%Y%m%d")

                X = get_data_for_days(
                    symbol="BTC_JPY",
                    interval="1hour",
                    end_date=end_date,
                    days=8,
                )
                X = calc_features(X, train=False)
                X = X.loc[
                    X.index
                    == (current_time - timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
                ].copy()
                print_log(f"\n{X.squeeze()}", notify=False)

                pred_proba = model.predict_proba(X)[0][1]
                print_log(pred_proba, notify=False)

                if pred_proba >= 0.5:
                    side = "BUY"
                    hour = current_time.hour
                elif pred_proba < 0.5:
                    side = "SELL"
                    hour = current_time.hour
                else:
                    continue
            except Exception as e:
                print_log(
                    f"予測中にエラーが発生しました: {e}", level="error", notify=True
                )
                hour = current_time.hour
                continue

            if trade_num > 0:
                try:
                    (
                        tmp_id,
                        tmp_date,
                        tmp_position,
                        tmp_order_price,
                        tmp_close_price,
                        tmp_loss_gain,
                    ) = get_trading_result()  # 取引結果の取得
                    tmp_df = pd.DataFrame(
                        columns=[
                            "id",
                            "date",
                            "position",
                            "order_price",
                            "close_price",
                            "loss_gain",
                        ],
                        data=[
                            [
                                tmp_id,
                                tmp_date,
                                tmp_position,
                                tmp_order_price,
                                tmp_close_price,
                                tmp_loss_gain,
                            ]
                        ],
                    )
                    result_df = pd.concat([result_df, tmp_df])

                    # データベースに格納
                    cur.execute(
                        "INSERT INTO trading values(?, ?, ?, ?, ?, ?)",
                        (
                            tmp_id,
                            tmp_date,
                            tmp_position,
                            tmp_order_price,
                            tmp_close_price,
                            tmp_loss_gain,
                        ),
                    )
                    conn.commit()
                    print_log("取引結果をデータベースに格納しました", notify=False)
                except Exception as e:
                    print_log(
                        f"取引結果の格納中にエラーが発生しました: {e}",
                        level="error",
                        notify=True,
                    )

            try:
                available = int(get_available_amount())
                profit = available - default_available
                profit_rate = profit / default_available
                print_log(
                    f"現在の残高は{available}円で、利益は{profit}円です", notify=True
                )
            except Exception as e:
                print_log(
                    f"残高の取得中にエラーが発生しました: {e}",
                    level="error",
                    notify=True,
                )

            if profit_rate < -0.2:
                print_log(f"利益率が -20% を下回りました: {profit_rate}", notify=True)
                break

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
        else:
            remaining_minutes = 60 - current_time.minute
            sleep_time = 60 * remaining_minutes
            print_log(f"{remaining_minutes}分スリープします", notify=False)
            time.sleep(sleep_time)
    except Exception as e:
        print_log(f"想定外のエラーが発生しました: {e}", level="error", notify=True)
        break

conn.close()

print_log("gmo_ml_botの稼働を終了します", notify=True)
