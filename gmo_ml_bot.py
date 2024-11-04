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

with open(os.path.join("models", "model.pkl"), "rb") as f:
    model = pickle.load(f)

default_available = int(get_available_amount())  # デフォルトの残高
hour = datetime.now().hour

while True:
    if hour != datetime.now().hour:  # 1時間経過したら取引を行う
        print_log("****************", notify=False)
        try:
            price = get_price()
            print_log(f"現在の{symbol}価格は{price}円です", notify=False)
        except Exception as e:  # メンテナンス時はスキップ
            print_log(f"メンテナンス中です: {e}", level="warning", notify=True)
            hour = datetime.now().hour
            continue

        exe_all_position()  # ポジションを決済

        time.sleep(1)

        # --------ポジションを決めるための予測を行う--------#
        if datetime.now().hour >= 6:  # 日本時間朝6：00に新しい日付に切り替わる
            end_date = datetime.now().strftime("%Y%m%d")
        else:
            end_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

        X = get_data_for_days(
            symbol="BTC_JPY",
            interval="1hour",
            end_date=end_date,
            days=8,
        )
        X = calc_features(X, train=False)
        X = X.loc[
            X.index
            == (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
        ].copy()
        print_log(f"\n{X.squeeze()}", notify=False)

        pred_proba = model.predict_proba(X)[0][1]
        print_log(pred_proba, notify=False)

        if pred_proba >= 0.5:
            side = "BUY"
            hour = datetime.now().hour
        elif pred_proba < 0.5:
            side = "SELL"
            hour = datetime.now().hour
        else:
            continue

        if trade_num != 0:
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
            conn = sqlite3.connect(dbname)
            cur = conn.cursor()

            # テーブルが存在しなければ作成
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
            conn.close()
            print_log("取引結果をデータベースに格納しました", notify=False)

        available = int(get_available_amount())
        profit = available - default_available
        profit_rate = profit / default_available
        print_log(f"現在の残高は{available}円で、利益は{profit}円です", notify=True)

        if profit_rate < -0.2:
            break

        # --------注文を出す--------#
        order_process(symbol=symbol, side=side, executionType=exe_type, size=0.01)

        trade_num += 1
    else:
        remaining_minutes = 60 - datetime.now().minute
        sleep_time = 60 * remaining_minutes
        print_log(f"{remaining_minutes}分スリープします", notify=False)
        time.sleep(sleep_time)

print_log("gmo_ml_botの稼働を終了します", notify=True)
