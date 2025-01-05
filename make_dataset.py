from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests


def get_1day_data(symbol="BTC_JPY", interval="1hour", date=""):
    endPoint = "https://api.coin.z.com/public"
    path = f"/v1/klines?symbol={symbol}&interval={interval}&date={date}"

    res = requests.get(endPoint + path)

    res_json = res.json()
    if res.status_code != 200 or "data" not in res_json:
        raise Exception(f"Error fetching data: {res_json}")

    data = pd.json_normalize(res_json["data"])

    if len(data) != 0:
        data["openTime"] = pd.to_datetime(
            data["openTime"].astype(int),
            unit="ms",
            utc=True,
        )
        data.set_index("openTime", inplace=True)
        data.index = data.index.tz_convert("Asia/Tokyo")
    else:
        raise Exception(f"Error fetching data: {res_json}")

    return data


def get_data_for_days(symbol="BTC_JPY", interval="1hour", end_date="", days=450):
    all_data = pd.DataFrame()
    current_date = datetime.strptime(end_date, "%Y%m%d")

    for _ in range(days):
        date_str = current_date.strftime("%Y%m%d")
        data = get_1day_data(symbol=symbol, interval=interval, date=date_str)
        all_data = pd.concat([data, all_data])
        current_date -= timedelta(days=1)

    all_data = all_data.sort_index()
    all_data = all_data[~all_data.index.duplicated(keep="last")]  # 念のため重複削除

    return all_data


def calc_features(df, train=True):
    df[df.columns] = df[df.columns].astype(float)

    df["return"] = np.log(df["close"] / df["open"])

    # df["open2close"] = df["close"] / df["open"]
    # df["high2low"] = df["high"] / df["low"]
    # mean_price = df[["open", "high", "low", "close"]].mean(axis=1)
    # median_price = df[["open", "high", "low", "close"]].median(axis=1)
    # df["high2mean"] = df["high"] / mean_price
    # df["low2mean"] = df["low"] / mean_price
    # df["high2median"] = df["high"] / median_price
    # df["low2median"] = df["low"] / median_price

    rolling_windows = [5, 13, 25]  # 予測時のget_data_for_daysと合わせること
    for window in rolling_windows:
        df[f"return_mean_{window}"] = df["return"].rolling(window, 2).mean()  # 移動平均
        df[f"return_std_{window}"] = df["return"].rolling(window, 2).std()  # 標準偏差
        df[f"sharpe_{window}"] = (
            df[f"return_mean_{window}"] / df[f"return_std_{window}"]
        )  # シャープレシオ
        df[f"return_mean_gap_{window}"] = (
            df["close"] / df[f"return_mean_{window}"]
        )  # 移動平均乖離率

    df = df.iloc[max(rolling_windows) - 1 :].copy()

    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    if train:
        df["target_return"] = df["return"].shift(-1)  # ターゲット（リターン）
        df["target_return_sign"] = df["target_return"].apply(
            lambda x: 1 if x >= 0 else 0
        )  # ターゲット（リターンの正負）
        df["target_price_diff"] = (df["close"] - df["open"]).shift(
            -1
        )  # ターゲット（価格差）

        df.dropna(subset=["target_return"], inplace=True)

    # 使用しない特徴量を削除
    drop_cols = ["open", "high", "low", "close", "volume"]
    df.drop(columns=drop_cols, inplace=True)

    # 欠損値を補完
    df.fillna(-999, inplace=True)

    return df
