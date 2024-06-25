import base64
import datetime
import json
from typing import Any, Dict, Optional
import uuid
import requests
import cryptography
from cryptography.hazmat.primitives.asymmetric import ed25519
import time
import os

API_KEY = os.getenv('RH_API_KEY')
BASE64_PRIVATE_KEY = os.getenv('RH_PRIVATE_KEY')

class CryptoAPITrading:
    def __init__(self):
        self.api_key = API_KEY
        private_bytes = base64.b64decode(BASE64_PRIVATE_KEY)
        # Note that the cryptography library used here only accepts a 32 byte ed25519 private key
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes[:32])
        self.base_url = "https://trading.robinhood.com"
         
        # storing buying/selling data in memory for prototyping
        # this data should be stored in a database in a production environment
        self.btc_last_price_bought = 0
        self.btc_last_price_sold = 0
        self.btc_last_quantity_bought = 0
        self.btc_last_quantity_sold = 0
        self.btc_last_price_checked = 0


    @staticmethod
    def _get_current_timestamp() -> int:
        return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())


    @staticmethod
    def get_query_params(key: str, *args: Optional[str]) -> str:
        if not args:
            return ""

        params = []
        for arg in args:
            params.append(f"{key}={arg}")

        return "?" + "&".join(params)


    def make_api_request(self, method: str, path: str, body: str = "") -> Any:
        timestamp = self._get_current_timestamp()
        headers = self.get_authorization_header(method, path, body, timestamp)
        url = self.base_url + path

        try:
            response = {}
            if method == "GET":
                # print(url)
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json.loads(body), timeout=10)
            return response.json()
        except requests.RequestException as e:
            print(f"Error making API request: {e}")
            return None


    def get_authorization_header(
            self, method: str, path: str, body: str, timestamp: int
    ) -> Dict[str, str]:
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
       
        signature = self.private_key.sign(message_to_sign.encode("utf-8"))
       
        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }


    def get_account(self) -> Any:
        path = "/api/v1/crypto/trading/accounts/"
        return self.make_api_request("GET", path)


    # The symbols argument must be formatted in trading pairs, e.g "BTC-USD", "ETH-USD". If no symbols are provided,
    # all supported symbols will be returned
    def get_trading_pairs(self, *symbols: Optional[str]) -> Any:
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/trading/trading_pairs/{query_params}"
        return self.make_api_request("GET", path)


    # The asset_codes argument must be formatted as the short form name for a crypto, e.g "BTC", "ETH". If no asset
    # codes are provided, all crypto holdings will be returned
    def get_holdings(self, *asset_codes: Optional[str]) -> Any:
        query_params = self.get_query_params("asset_code", *asset_codes)
        path = f"/api/v1/crypto/trading/holdings/{query_params}"
        return self.make_api_request("GET", path)


    # The symbols argument must be formatted in trading pairs, e.g "BTC-USD", "ETH-USD". If no symbols are provided,
    # the best bid and ask for all supported symbols will be returned
    def get_best_bid_ask(self, *symbols: Optional[str]) -> Any:
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/marketdata/best_bid_ask/{query_params}"
        return self.make_api_request("GET", path)


    # The symbol argument must be formatted in a trading pair, e.g "BTC-USD", "ETH-USD"
    # The side argument must be "bid", "ask", or "both".
    # Multiple quantities can be specified in the quantity argument, e.g. "0.1,1,1.999".
    def get_estimated_price(self, symbol: str, side: str, quantity: str) -> Any:
        path = f"/api/v1/crypto/marketdata/estimated_price/?symbol={symbol}&side={side}&quantity={quantity}"
        return self.make_api_request("GET", path)


    def place_order(
            self,
            client_order_id: str,
            side: str,
            order_type: str,
            symbol: str,
            order_config: Dict[str, str],
    ) -> Any:
        body = {
            "client_order_id": client_order_id,
            "side": side,
            "type": order_type,
            "symbol": symbol,
            f"{order_type}_order_config": order_config,
        }
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("POST", path, json.dumps(body))
    
    def cancel_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        return self.make_api_request("POST", path)


    def get_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        return self.make_api_request("GET", path)


    def get_orders(self) -> Any:
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("GET", path)

    def check_buying_power(self) -> Any:
        path = "/api/v1/crypto/trading/accounts/"
        response = self.make_api_request("GET", path)
        buying_power = response.get("buying_power")
        print(buying_power)
        return float(buying_power)

        # get current bitcoin holdings
        btc_holdings = self.get_holdings("BTC")
        print("bitcoin holdings", btc_holdings)
            
        # if bitcoin holdings == zero, then...
        if btc_holdings == 0:
            print("No bitcoin holdings")
            # get the current price of bitcoin
            btc_price = self.get_best_bid_ask("BTC-USD")
            self.btc_last_price_checked = btc_price
            print("bitcoin price", btc_price)

            # if last price bought does not = 0 (not first time buying bitcoin)
            if self.btc_last_price_sold != 0:
                # check to see if the current price is 3% less than the last price sold
                if btc_price < self.btc_last_price_sold * 0.97:
                    # calculate btc quantity the equates to $10
                    btc_quantity = 10 / btc_price
                    print("btc quantity", btc_quantity)
                    
                    # place order
                    order = self.place_order_by_dollar_amount(
                        str(uuid.uuid4()),
                        "buy",
                        "market",
                        "BTC-USD",
                        btc_quantity,
                    )
                    print(order)

                    # capture the last price bought
                    self.btc_last_price_bought = 
                    # capture the last quantity bought
                    # capture the date/time bought
            # else buy bitcoin (this is the first time buying bitcoin)
            else:
                qty = .01
                # buy bitcoin ((this is the first time buying bitcoin)
                order = self.place_order(
                    str(uuid.uuid4()),
                    "buy",
                    "market",
                    "BTC-USD",
                    ,{asset_quantity: qty}
                )
                print(order)
                # store the last price bought
                self.btc_last_price_bought = btc_price
                # store the last quantity bought
                self.btc_last_quantity_bought = 10

            
        
        # else (bitcoin holdings are greater than zero)
            # if there are any open orders
                # if so, compare curernt price to the last price checked
                # if the current price is greater than 1% of the last price checked, cancel the order 
                # and place a new order for .5% below the current price

            # else, check to see if the current price is 3% more than the last price bought
                # if so, place a limit order to sell bitcoin at .5% below the current price
                # capture the last price sold
                # capture the last quantity sold
                # capture the date/time sold


            # buy bitcoin
            order = self.place_order_by_dollar_amount(
                str(uuid.uuid4()),
                "buy",
                "market",
                "BTC-USD",
                10,
            )
            print(order)
            # store the last price bought
            self.btc_last_price_bought = btc_price
            # store the last quantity bought
            self.btc_last_quantity_bought = 10
        # get the current price of bitcoin
        btc_price = self.get_best_bid_ask("BTC-USD")
        print(btc_price)

        # if last price bought is 0
def buy_avax():
    api_trading_client = CryptoAPITrading()

    #  check buying power to see if there is enough to trade
    buying_power = api_trading_client.check_buying_power()
    # buying_power = float(buying_power)
    if buying_power >= 1:
        print("Buying power is greater than 1: ", buying_power)
    
    qty = ".05"
    order = api_trading_client.place_order_by_dollar_amount(
        str(uuid.uuid4()),
        "buy",
        "market",
        "AVAX-USD",
        {"asset_quantity": qty},
        
    )

def main():
    api_trading_client = CryptoAPITrading()

    while True:

        #  check buying power to see if there is enough to trade
        buying_power = api_trading_client.check_buying_power()
        # buying_power = float(buying_power)
        if buying_power >= 10:
            print("Buying power is greater than 10: ", buying_power)
            api_trading_client.check_bitcoin()

        # sleep for 20 minutes
        time.sleep(1200)

    print(api_trading_client.get_account())
    # print(api_trading_client.get_estimated_price("BTC-USD", "ask", "1"))


    # print(api_trading_client._get_current_timestamp())
    # print(api_trading_client.get_estimated_price("BTC-USD", "bid", "0.1"))


    """
    BUILD YOUR TRADING STRATEGY HERE

    order = api_trading_client.place_order(
          str(uuid.uuid4()),
          "buy",
          "market",
          "AVAX-USD",
          {"asset_quantity": "0.0001"}
    )
    """


if __name__ == "__main__":
    main()
    buy_avax()

    # COMP = compound
    # BTC = bitcoin
    # ETH = ethereum
    # AVAX = avalanche
    # UNI = uniswap
    # LINK = chainlink
    # AAVE = aave
    # SHIB = shiba inu
    # DOGE = dogecoin