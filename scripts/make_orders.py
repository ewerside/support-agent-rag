"""Generate 300 synthetic orders and load them into support_agent.orders. Run: python -m scripts.make_orders"""

import random
import string
import unicodedata
from collections import Counter
from datetime import date, timedelta

import psycopg
from faker import Faker
from psycopg.types.json import Jsonb

import config

SEED = 7
ORDER_COUNT = 300
FIRST_ORDER_NUMBER = 10001
# A fixed date keeps the output the same on every run. It is the day the sample data was made.
TODAY = date(2026, 11, 5)
EMAIL_DOMAINS = ["example.com", "example.org", "example.net"]
REPEAT_CUSTOMER_RATE = 0.15

# sku, name, price in USD
CATALOG = [
    ("WF-ESP-SOLO", "Wrenfield Solo Espresso Machine", 649.00),
    ("WF-ESP-DUO", "Wrenfield Duo Espresso Machine", 1149.00),
    ("WF-ESP-COMPACT", "Wrenfield Compact Espresso Machine", 449.00),
    ("WF-GRN-F64", "Wrenfield F64 Grinder", 399.00),
    ("WF-GRN-MINI", "Wrenfield Mini Grinder", 229.00),
    ("WF-KTL-GOOSE", "Wrenfield Gooseneck Kettle", 99.00),
    ("WF-SCL-BREW", "Wrenfield Brew Scale", 59.00),
    ("WF-TMP-CAL", "Wrenfield Calibrated Tamper", 39.00),
    ("WF-PCH-MILK", "Wrenfield Milk Pitcher", 24.00),
    ("WF-KBX", "Wrenfield Knock Box", 34.00),
    ("WF-DSC-4", "Wrenfield Descaler, 4 sachets", 18.00),
    ("WF-CLN-POWDER", "Wrenfield Espresso Cleaning Powder", 16.00),
    ("WF-FLT-3", "Wrenfield Water Filter Cartridges, 3 pack", 29.00),
    ("CF-HOUSE-340", "House Espresso Blend, 340 g", 17.00),
    ("CF-GUJI-340", "Ethiopia Guji Single Origin, 340 g", 21.00),
]
CONSUMABLE_SKUS = {
    "WF-DSC-4",
    "WF-CLN-POWDER",
    "WF-FLT-3",
    "CF-HOUSE-340",
    "CF-GUJI-340",
}

# Shipping prices, free shipping thresholds, carriers and standard transit times match kb/facts.yaml.
COUNTRIES = {
    "United States": {
        "locale": "en_US",
        "currency": "USD",
        "usd_rate": 1.0,
        "shipping": 6.95,
        "free_over": 75,
        "carriers": ["UPS", "USPS"],
        "transit_days": 5,
        "weight": 60,
    },
    "Canada": {
        "locale": "en_CA",
        "currency": "CAD",
        "usd_rate": 1.35,
        "shipping": 12.95,
        "free_over": 100,
        "carriers": ["Canada Post", "UPS"],
        "transit_days": 8,
        "weight": 20,
    },
    "United Kingdom": {
        "locale": "en_GB",
        "currency": "GBP",
        "usd_rate": 0.80,
        "shipping": 4.95,
        "free_over": 60,
        "carriers": ["Royal Mail"],
        "transit_days": 3,
        "weight": 20,
    },
}
STATUS_WEIGHTS = {
    "delivered": 55,
    "shipped": 20,
    "processing": 10,
    "returned": 8,
    "cancelled": 7,
}
# Days before TODAY that an order with this status shipped.
SHIPPED_DAYS_AGO = {"shipped": (0, 2), "delivered": (10, 60), "returned": (25, 90)}


def local_price(usd: float, rate: float) -> float:
    if rate == 1.0:
        return usd
    return round(usd * rate) - 0.01


def last_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def add_business_days(day: date, count: int) -> date:
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def tracking_number(rng: random.Random, carrier: str) -> str:
    def digits(n: int) -> str:
        return "".join(rng.choices(string.digits, k=n))

    if carrier == "UPS":
        return (
            "1Z"
            + "".join(rng.choices(string.ascii_uppercase + string.digits, k=6))
            + digits(10)
        )
    if carrier == "USPS":
        return "9400" + digits(18)
    if carrier == "Canada Post":
        return digits(16)
    return "".join(rng.choices(string.ascii_uppercase, k=2)) + digits(9) + "GB"


def ascii_slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in plain.lower() if c.isalpha())


def new_customer(
    rng: random.Random, fake: Faker, country: str, used_emails: set[str]
) -> dict:
    person = fake[COUNTRIES[country]["locale"]]
    while True:
        first, last = person.first_name(), person.last_name()
        email = f"{ascii_slug(first)}.{ascii_slug(last)}{rng.randint(1, 99)}@{rng.choice(EMAIL_DOMAINS)}"
        if email not in used_emails:
            used_emails.add(email)
            return {"name": f"{first} {last}", "email": email, "country": country}


def make_items(rng: random.Random, country: str) -> list[dict]:
    rate = COUNTRIES[country]["usd_rate"]
    lines = rng.choices([1, 2, 3], weights=[55, 30, 15])[0]
    items = []
    for sku, name, usd in rng.sample(CATALOG, lines):
        qty = rng.randint(1, 3) if sku in CONSUMABLE_SKUS else 1
        items.append(
            {"sku": sku, "name": name, "qty": qty, "unit_price": local_price(usd, rate)}
        )
    return items


def make_order(rng: random.Random, number: int, customer: dict) -> dict:
    country = COUNTRIES[customer["country"]]
    items = make_items(rng, customer["country"])
    subtotal = sum(i["qty"] * i["unit_price"] for i in items)
    shipping = 0 if subtotal > country["free_over"] else country["shipping"]
    status = rng.choices(list(STATUS_WEIGHTS), weights=list(STATUS_WEIGHTS.values()))[0]
    order = {
        "order_id": f"WCG-{number}",
        "email": customer["email"],
        "customer_name": customer["name"],
        "country": customer["country"],
        "status": status,
        "carrier": None,
        "tracking_number": None,
        "shipped_at": None,
        "eta": None,
        "items": Jsonb(items),
        "total": round(subtotal + shipping, 2),
        "currency": country["currency"],
    }
    if status in SHIPPED_DAYS_AGO:
        shipped_at = last_weekday(
            TODAY - timedelta(days=rng.randint(*SHIPPED_DAYS_AGO[status]))
        )
        carrier = rng.choice(country["carriers"])
        order |= {
            "carrier": carrier,
            "tracking_number": tracking_number(rng, carrier),
            "shipped_at": shipped_at,
            "eta": add_business_days(shipped_at, country["transit_days"]),
        }
    return order


def make_orders() -> list[dict]:
    rng = random.Random(SEED)
    Faker.seed(SEED)
    fake = Faker([c["locale"] for c in COUNTRIES.values()])
    names = list(COUNTRIES)
    weights = [c["weight"] for c in COUNTRIES.values()]
    customers: list[dict] = []
    used_emails: set[str] = set()
    orders = []
    for number in range(FIRST_ORDER_NUMBER, FIRST_ORDER_NUMBER + ORDER_COUNT):
        if customers and rng.random() < REPEAT_CUSTOMER_RATE:
            customer = rng.choice(customers)
        else:
            country = rng.choices(names, weights=weights)[0]
            customer = new_customer(rng, fake, country, used_emails)
            customers.append(customer)
        orders.append(make_order(rng, number, customer))
    return orders


def main() -> None:
    orders = make_orders()
    columns = list(orders[0])
    insert = (
        f"insert into support_agent.orders ({', '.join(columns)}) "
        f"values ({', '.join(['%s'] * len(columns))})"
    )
    with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn:
        # Replace everything so a rerun gives the same 300 rows, not duplicates.
        conn.execute("delete from support_agent.orders")
        with conn.cursor() as cur:
            cur.executemany(insert, [[o[c] for c in columns] for o in orders])
        total = conn.execute("select count(*) from support_agent.orders").fetchone()[0]
        by_status = conn.execute(
            "select status, count(*) from support_agent.orders group by status order by 2 desc"
        ).fetchall()
    print(f"orders in table: {total}")
    for status, count in by_status:
        print(f"  {status:<11} {count}")
    print("by country:", dict(Counter(o["country"] for o in orders)))
    print(
        "repeat customers:",
        sum(1 for n in Counter(o["email"] for o in orders).values() if n > 1),
    )


if __name__ == "__main__":
    main()
