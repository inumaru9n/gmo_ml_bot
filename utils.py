import configparser
import logging

import requests

conf = configparser.ConfigParser()
conf.read("config.ini")
LINE_NOTIFY_TOKEN = conf["line"]["LINE_NOTIFY_TOKEN"]
log_path = "./gmo_ml_bot.log"

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def print_log(message, level="info", notify=False):
    level = level.lower()
    if notify:
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
        data = {"message": f" {message}"}
        try:
            requests.post(url, headers=headers, data=data)
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send notification: {e}")

    if level == "debug":
        logging.debug(message)
    elif level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    elif level == "critical":
        logging.critical(message)
    else:
        logging.info(message)
