import requests
from urllib.parse import unquote, parse_qs


class BalanceTransportCard:
    def __init__(self, system: str, number: str):
        self.pay_system = system
        self.number = number

    async def get_balance(self):
        if self.pay_system == "АЛҒА":
            return await self.get_balance_alga(self.number)

    async def get_balance_alga(self, number: str):
        URL = "https://alga-card.ru/balance/"
        URL_BRSC = "https://pay.brsc.ru/Alga.pay/GoldenCrownSite.php"
        CARD = number

        session = requests.Session()
        session.get(URL)

        headers = {
            "Referer": URL_BRSC,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"cardnumber": CARD}

        response = session.post(URL_BRSC, headers=headers, data=data, allow_redirects=False)

        params = parse_qs(unquote(response.headers["Location"]))
        try:
            if params.get('allow')[0] == 'yes':
                return params.get('sum')[0]
            else:
                return '--'
        except:
            return '--'
