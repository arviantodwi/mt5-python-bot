import time

import mt5_wrapper as mt5

from .config import Config
from .helper import clear_and_print, colorize_text, with_mt5_error, with_tag


class Trader:
    def __init__(self) -> None:
        try:
            self.account_info = self.__login()
        except RuntimeError as e:
            raise e

    def get_account_balance(self) -> float:
        return self.account_info.balance

    def set_ta(self):
        pass

    def post_buy_order(self):
        pass

    def post_sell_order(self):
        pass

    # entry_price: int, stop_loss: int, tick_value_per_lot: int
    def __compute_lot_size(self):
        pass

    def __login(self) -> mt5.AccountInfo:
        print(with_tag("Authenticating trader account..."), end="\r")
        time.sleep(1)

        # Attempt to login
        is_authorized = mt5.login(Config.ACCOUNT_USER, Config.ACCOUNT_PASS, Config.SERVER_URL, timeout=5_000)
        if not is_authorized:
            raise RuntimeError(with_mt5_error("Unable to authorize user.", "FATAL"))

        # Fetch account information
        if (account_info_dict := mt5.account_info()) is None:
            raise RuntimeError(with_mt5_error("Unable to fetch account information."))

        clear_and_print(
            with_tag(
                f"Trader account authorized. Welcome, {colorize_text(account_info_dict.name)} ({account_info_dict.login}).",
                "OK",
            )
        )

        return account_info_dict
