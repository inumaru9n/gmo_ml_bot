import configparser
import hashlib
import hmac
import json
import time
from datetime import datetime

import pandas as pd
import requests
from pytz import timezone

from utils import print_log

conf = configparser.ConfigParser()
conf.read("config.ini")
apiKey = conf["gmo"]["apiKey"]
secretKey = conf["gmo"]["secretKey"]


# ------------------------GMOコインAPIを用いた取引目的の関数------------------------#
def get_price(symbol="BTC_JPY"):
    """
    仮想通貨の現在価格を取得する関数
    params
    ============
    symbol: str
        取得する仮想通貨名
    """
    endPoint = "https://api.coin.z.com/public"
    path = f"/v1/ticker?symbol={symbol}"

    res = requests.get(endPoint + path)

    return res.json()["data"][0]["ask"]


def get_available_amount():
    """
    取引余力を取得する関数
    """
    timestamp = "{0}000".format(int(time.mktime(datetime.now().timetuple())))
    method = "GET"
    endPoint = "https://api.coin.z.com/private"
    path = "/v1/account/margin"

    text = timestamp + method + path
    sign = hmac.new(
        bytes(secretKey.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
    ).hexdigest()

    headers = {"API-KEY": apiKey, "API-TIMESTAMP": timestamp, "API-SIGN": sign}

    res = requests.get(endPoint + path, headers=headers)

    return res.json()["data"]["availableAmount"]


def build_position(
    symbol, side, executionType, size, price="", losscutPrice="", timeInForce="FAK"
):
    """
    ポジションを決める
    prameters
    =============
    symbol: str
        注文する銘柄
    executionType: MARKET LIMIT STOP
        成行、指値、逆指値
    timeInForce:
    price: int, float
        注文価格, 指値の場合は必須
    losscutPrice:
    size: int, float
        注文数量
    """
    timestamp = "{0}000".format(int(time.mktime(datetime.now().timetuple())))
    method = "POST"
    endPoint = "https://api.coin.z.com/private"
    path = "/v1/order"
    reqBody = {
        "symbol": symbol,
        "side": side,
        "executionType": executionType,
        "timeInForce": timeInForce,
        "price": price,
        "losscutPrice": losscutPrice,
        "size": size,
    }

    text = timestamp + method + path + json.dumps(reqBody)
    sign = hmac.new(
        bytes(secretKey.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
    ).hexdigest()

    headers = {"API-KEY": apiKey, "API-TIMESTAMP": timestamp, "API-SIGN": sign}

    res = requests.post(endPoint + path, headers=headers, data=json.dumps(reqBody))

    return res.json()


def get_position():
    """建玉一覧を取得"""
    timestamp = "{0}000".format(int(time.mktime(datetime.now().timetuple())))
    method = "GET"
    endPoint = "https://api.coin.z.com/private"
    path = "/v1/openPositions"

    text = timestamp + method + path
    sign = hmac.new(
        bytes(secretKey.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
    ).hexdigest()
    parameters = {"symbol": "BTC_JPY", "page": 1, "count": 100}

    headers = {"API-KEY": apiKey, "API-TIMESTAMP": timestamp, "API-SIGN": sign}

    res = requests.get(endPoint + path, headers=headers, params=parameters)

    return res.json()


def close_position(symbol, side, size, executionType, position_id):
    """決済注文を出す"""
    timestamp = "{0}000".format(int(time.mktime(datetime.now().timetuple())))
    method = "POST"
    endPoint = "https://api.coin.z.com/private"
    path = "/v1/closeOrder"
    reqBody = {
        "symbol": symbol,
        "side": side,
        "executionType": executionType,
        "timeInForce": "",
        "price": "",
        "settlePosition": [{"positionId": position_id, "size": size}],
    }

    text = timestamp + method + path + json.dumps(reqBody)
    sign = hmac.new(
        bytes(secretKey.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
    ).hexdigest()

    headers = {"API-KEY": apiKey, "API-TIMESTAMP": timestamp, "API-SIGN": sign}

    res = requests.post(endPoint + path, headers=headers, data=json.dumps(reqBody))

    return res.json()


def exe_all_position():
    """すべてのポジションを決済する"""
    position = get_position()
    if position["data"] == {}:
        print_log("ポジションはありません", notify=True)
    else:
        for i in position["data"]["list"]:
            if i["side"] == "BUY":
                close_res = close_position(
                    i["symbol"], "SELL", i["size"], "MARKET", i["positionId"]
                )
                if close_res["status"] == 0:
                    print_log("レバレッジ取引(買い注文)は決済されました", notify=True)
                else:
                    print_log(close_res, level="error", notify=True)
            elif i["side"] == "SELL":
                close_res = close_position(
                    i["symbol"], "BUY", i["size"], "MARKET", i["positionId"]
                )
                if close_res["status"] == 0:
                    print_log("レバレッジ取引(売り注文)は決済されました", notify=True)
                else:
                    print_log(close_res, level="error", notify=True)


def order_process(
    symbol, side, executionType, size, price="", losscutPrice="", timeInForce="FAK"
):
    """注文を出す"""
    build_position(
        symbol, side, executionType, size, price, losscutPrice, timeInForce="FAK"
    )

    time.sleep(1)

    price = get_position()["data"]["list"][0]["price"]
    print_log(f"ビットコインを{price}円で{side}しました", notify=True)


def get_trading_result():
    """取引の記録を取得"""
    timestamp = "{0}000".format(int(time.mktime(datetime.now().timetuple())))
    method = "GET"
    endPoint = "https://api.coin.z.com/private"
    path = "/v1/latestExecutions"

    text = timestamp + method + path
    sign = hmac.new(
        bytes(secretKey.encode("ascii")), bytes(text.encode("ascii")), hashlib.sha256
    ).hexdigest()
    parameters = {"symbol": "BTC_JPY", "page": 1, "count": 2}

    headers = {"API-KEY": apiKey, "API-TIMESTAMP": timestamp, "API-SIGN": sign}

    res = requests.get(endPoint + path, headers=headers, params=parameters)

    data_list = res.json()["data"]["list"]
    time_ = pd.Timestamp(data_list[1]["timestamp"]).astimezone(timezone("Asia/Tokyo"))
    date = f"{time_.year}-{time_.month}-{time_.day} {time_.hour}:00:00"
    side = data_list[1]["side"]
    position = -1 if side == "SELL" else 1
    order_price = int(data_list[1]["price"])
    close_price = int(data_list[0]["price"])
    loss_gain = int(data_list[0]["lossGain"])
    id = int(data_list[0]["executionId"])

    return id, date, position, order_price, close_price, loss_gain
