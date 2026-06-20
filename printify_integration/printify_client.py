import requests

class PrintifyClient:
    BASE = "https://api.printify.com/v1"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get_shops(self):
        r = self.session.get(f"{self.BASE}/shops.json", timeout=30)
        r.raise_for_status()
        return r.json()

    def list_products(self, shop_id: str, limit=100, page=1):
        r = self.session.get(
            f"{self.BASE}/shops/{shop_id}/products.json",
            params={"limit": limit, "page": page},
            timeout=30
        )
        r.raise_for_status()
        return r.json()
