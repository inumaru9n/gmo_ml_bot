import os
import pickle
import sqlite3
import time
from datetime import datetime, timedelta

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
dbname = "sql/trading.db"  # 取引結果を格納するテーブル
exe_type = "MARKET"  # 注文方式(成行)

feature_cols = [
    "return",
    "return_std_5",
    "sharpe_5",
]

# -----------------------------Bot本体の処理-----------------------------#
print_log("gmo_ml_botの稼働を開始します", notify=True)

models = []
try:
    model_files = [f for f in os.listdir("models") if f.endswith(".pkl")]
    for model_file in model_files:
        with open(os.path.join("models", model_file), "rb") as f:
            models.append(pickle.load(f))
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
    previous_available = default_available
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
                # try:
                #     (
                #         tmp_id,
                #         tmp_date,
                #         tmp_position,
                #         tmp_order_price,
                #         tmp_close_price,
                #         tmp_loss_gain,
                #     ) = get_trading_result()  # 取引結果

                #     # データベースに格納
                #     cur.execute(
                #         "INSERT INTO trading values(?, ?, ?, ?, ?, ?)",
                #         (
                #             tmp_id,
                #             tmp_date,
                #             tmp_position,
                #             tmp_order_price,
                #             tmp_close_price,
                #             tmp_loss_gain,
                #         ),
                #     )
                #     conn.commit()
                #     print_log(
                #         f"取引結果をデータベースに格納しました: id={tmp_id}, date={tmp_date}, position={tmp_position}, order_price={tmp_order_price}, close_price={tmp_close_price}, loss_gain={tmp_loss_gain}",
                #         notify=False,
                #     )
                # except Exception as e:
                #     print_log(
                #         f"取引結果の格納中にエラーが発生しました: {e}",
                #         level="error",
                #         notify=True,
                #     )

                try:
                    available = int(get_available_amount())
                    profit = available - default_available
                    profit_rate = profit / default_available
                    # print_log(
                    #     f"決済損益は{tmp_loss_gain}で、現在の残高は{available}円です",
                    #     notify=False,
                    # )
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
                    days=3,
                )
                X = calc_features(X, train=False)
                X = X.loc[
                    X.index
                    == (current_time - timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")
                ].copy()

                if X.empty:
                    raise ValueError("予測データが存在しません")

                print_log(f"\n{X.squeeze()}", notify=False)

                pred_proba = 0
                for model in models:
                    pred_proba += model.predict_proba(X[feature_cols])[0][1]

                pred_proba /= len(models)
                print_log(pred_proba, notify=False)

                if pred_proba >= 0.5:
                    side = "BUY"
                    hour = current_time.hour
                elif pred_proba < 0.5:
                    side = "SELL"
                    hour = current_time.hour
                else:
                    raise ValueError("予測確率が不正です")
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

            # # --------日次で損益をレポーティング--------#
            # if current_time.hour == 0:
            #     try:
            #         cur.execute(
            #             "SELECT SUM(loss_gain) FROM trading WHERE DATE(date) = DATE('now', 'localtime', '-1 day')"
            #         )
            #         daily_profit = cur.fetchone()[0] or 0

            #         cur.execute(
            #             "SELECT COUNT(*) FROM trading WHERE DATE(date) = DATE('now', 'localtime', '-1 day')"
            #         )
            #         daily_trades = cur.fetchone()[0]

            #         cur.execute(
            #             "SELECT COUNT(*) FROM trading WHERE DATE(date) = DATE('now', 'localtime', '-1 day') AND loss_gain > 0"
            #         )
            #         daily_wins = cur.fetchone()[0]

            #         daily_win_rate = (
            #             daily_wins / daily_trades if daily_trades > 0 else 0
            #         )

            #         cur.execute("SELECT SUM(loss_gain) FROM trading")
            #         cumulative_profit = cur.fetchone()[0] or 0

            #         print_log(
            #             f"{(current_time - timedelta(days=1)).strftime('%Y-%m-%d')}\n損益: {daily_profit}円\n勝率: {daily_win_rate * 100:.1f}%({daily_wins}/{daily_trades})\n累積損益: {cumulative_profit}円",
            #             notify=True,
            #         )
            #     except Exception as e:
            #         print_log(
            #             f"日次損益の計算中にエラーが発生しました: {e}",
            #             level="error",
            #             notify=True,
            #         )

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
