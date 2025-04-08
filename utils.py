import configparser
import logging

import requests

conf = configparser.ConfigParser()
conf.read("config.ini")
DISCORD_WEBHOOK_URL = conf["discord"]["DISCORD_WEBHOOK_URL"]
log_path = "./gmo_ml_bot.log"

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def print_log(message, level="info", notify=False):
    level = level.lower()
    if notify:
        url = DISCORD_WEBHOOK_URL
        data = {"content": message}
        try:
            requests.post(url, json=data)
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
