import os
import re
import json
import time
import random
import string
import traceback
import requests
from faker import Faker
from playwright.sync_api import sync_playwright

TARGET_URL = "https://futures.waitlist.atlasfunded.com/"
MAILTM = "https://api.mail.tm"
RUN_TIMEOUT = 240
fake = Faker()

os.makedirs("screenshots", exist_ok=True)
os.makedirs("responses", exist_ok=True)
os.makedirs("html_dump", exist_ok=True)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_json(filename, data):
    with open(f"responses/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_screenshot(page, filename):
    try:
        page.screenshot(
            path=f"screenshots/{filename}",
            full_page=True
        )
    except:
        pass


def dump_html(page):
    try:
        with open(
            "html_dump/error.html",
            "w",
            encoding="utf-8"
        ) as f:
            f.write(page.content())
    except:
        pass


def random_username():
    return "".join(
        random.choices(
            string.ascii_lowercase,
            k=8
        )
    ) + str(random.randint(100, 999))


def random_phone():
    return "98765" + "".join(
        random.choices(
            string.digits,
            k=5
        )
    )


def random_password():
    return "".join(
        random.choices(
            string.ascii_letters + string.digits,
            k=14
        )
    )


# ---------------------------
# PROXY POOL
# ---------------------------

PROXY_POOL = []


def refill_proxy_pool():
    global PROXY_POOL

    if not os.path.exists("proxy.txt"):
        raise Exception("proxy.txt missing")

    with open("proxy.txt", "r") as f:
        proxies = [
            line.strip()
            for line in f.readlines()
            if line.strip()
        ]

    if not proxies:
        raise Exception("proxy.txt empty")

    random.shuffle(proxies)
    PROXY_POOL = proxies.copy()

    log(f"Proxy pool refilled: {len(PROXY_POOL)} proxies")


def get_next_proxy():
    global PROXY_POOL

    if not PROXY_POOL:
        refill_proxy_pool()

    proxy = PROXY_POOL.pop(0)

    log(f"Using proxy: {proxy}")
    return proxy


def parse_proxy(proxy):
    if "@" in proxy:
        creds, host = proxy.split("@", 1)
        username, password = creds.split(":", 1)
        ip, port = host.rsplit(":", 1)

        return {
            "server": f"http://{ip}:{port}",
            "username": username,
            "password": password
        }

    else:
        return {
            "server": f"http://{proxy}"
        }


def requests_proxy(playwright_proxy):
    if not playwright_proxy:
        return None

    if "username" in playwright_proxy:
        auth = (
            f"{playwright_proxy['username']}:"
            f"{playwright_proxy['password']}@"
        )
    else:
        auth = ""

    server = playwright_proxy["server"].replace(
        "http://",
        ""
    )

    proxy_url = f"http://{auth}{server}"

    return {
        "http": proxy_url,
        "https": proxy_url
    }


# ---------------------------
# MAIL API
# ---------------------------

def create_temp_email(req_proxy):
    log("Fetching mail.tm domains")

    domains_res = requests.get(
        f"{MAILTM}/domains",
        timeout=30,
        proxies=req_proxy
    )
    domains_res.raise_for_status()

    domains = domains_res.json()
    save_json("domains.json", domains)

    domain = domains["hydra:member"][0]["domain"]

    email = f"{random_username()}@{domain}"
    password = random_password()

    log(f"Creating temp email: {email}")

    account_res = requests.post(
        f"{MAILTM}/accounts",
        json={
            "address": email,
            "password": password
        },
        timeout=30,
        proxies=req_proxy
    )

    if account_res.status_code not in [200, 201]:
        raise Exception(account_res.text)

    token_res = requests.post(
        f"{MAILTM}/token",
        json={
            "address": email,
            "password": password
        },
        timeout=30,
        proxies=req_proxy
    )

    token_res.raise_for_status()

    token = token_res.json()["token"]

    return email, token
def fetch_latest_message(token, req_proxy):
    headers = {
        "Authorization": f"Bearer {token}"
    }

    inbox_res = requests.get(
        f"{MAILTM}/messages",
        headers=headers,
        timeout=30,
        proxies=req_proxy
    )

    inbox_res.raise_for_status()

    inbox = inbox_res.json()
    save_json("inbox.json", inbox)

    messages = inbox.get("hydra:member", [])

    if not messages:
        return None

    msg_id = messages[0]["id"]

    msg_res = requests.get(
        f"{MAILTM}/messages/{msg_id}",
        headers=headers,
        timeout=30,
        proxies=req_proxy
    )

    msg_res.raise_for_status()

    msg = msg_res.json()
    save_json("email_message.json", msg)

    return msg


def extract_otp(message):
    text = message.get("text", "") or ""

    html = ""

    if message.get("html"):
        if isinstance(message["html"], list):
            html = message["html"][0]

    combined = text + "\n" + html

    match = re.search(
        r"\b(\d{4,8})\b",
        combined
    )

    if match:
        return match.group(1)

    return None


def wait_for_otp(
    token,
    req_proxy,
    timeout_sec=180
):
    log("Waiting for OTP")

    start = time.time()

    while time.time() - start < timeout_sec:
        try:
            msg = fetch_latest_message(
                token,
                req_proxy
            )

            if msg:
                otp = extract_otp(msg)

                if otp:
                    log(f"OTP received: {otp}")
                    return otp

        except Exception as e:
            log(f"OTP polling error: {e}")

        time.sleep(5)

    raise Exception("OTP timeout")


# ---------------------------
# PLAYWRIGHT HELPERS
# ---------------------------

def safe_click(locator):
    locator.wait_for(timeout=15000)
    locator.click(force=True)


def safe_fill(locator, value):
    locator.wait_for(timeout=15000)
    locator.fill(value)


def enter_otp(page, otp):
    log("Entering OTP")

    otp_input = page.locator(
        "input[placeholder='Enter OTP']"
    )

    safe_fill(otp_input, otp)

    save_screenshot(
        page,
        "otp_filled.png"
    )

    verify_btn = page.get_by_role(
        "button",
        name="Verify"
    )

    safe_click(verify_btn)

    log("OTP verify clicked")

    page.wait_for_selector(
        "text=Completed tasks",
        timeout=30000
    )

    save_screenshot(
        page,
        "dashboard_loaded.png"
    )


def complete_all_tasks(page):
    log("Completing tasks")

    page.wait_for_selector(
        "text=Completed tasks",
        timeout=30000
    )

    task_buttons = page.locator(
        "div:has-text('Completed tasks') button"
    )

    total = task_buttons.count()

    log(f"Found {total} buttons")

    for i in range(total):
        try:
            btn = task_buttons.nth(i)

            if not btn.is_visible():
                continue

            log(f"Task {i+1}")

            with page.context.expect_page(
                timeout=15000
            ) as popup:
                btn.click(force=True)

            new_tab = popup.value

            try:
                new_tab.wait_for_load_state(
                    "domcontentloaded",
                    timeout=10000
                )

                time.sleep(3)
                new_tab.close()

            except:
                pass

            page.bring_to_front()
            page.wait_for_timeout(5000)

            verify = page.locator(
                "button:has-text('Verify')"
            )

            if verify.count() > 0:
                verify.first.click(force=True)
                log(f"Verified task {i+1}")

            save_screenshot(
                page,
                f"task_{i+1}.png"
            )

            page.wait_for_timeout(3000)

        except Exception as e:
            log(f"Task failed: {e}")


# ---------------------------
# WATCHDOG
# ---------------------------

def timed_out(start_time):
    return (
        time.time() - start_time
    ) > RUN_TIMEOUT
def run_single_cycle():
    start_time = time.time()
    browser = None
    context = None

    proxy_raw = get_next_proxy()
    playwright_proxy = parse_proxy(proxy_raw)
    req_proxy = requests_proxy(playwright_proxy)

    username = random_username()
    fullname = fake.name()
    phone = random_phone()

    result = {
        "success": False,
        "proxy": proxy_raw,
        "username": username,
        "name": fullname
    }

    try:
        email, token = create_temp_email(req_proxy)
        result["email"] = email

        with sync_playwright() as p:
            if timed_out(start_time):
                raise Exception("Timed out before browser launch")

            browser = p.chromium.launch(
                headless=True,
                proxy=playwright_proxy,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                    "--single-process"
                ]
            )

            context = browser.new_context(
                viewport={
                    "width": 1440,
                    "height": 1200
                }
            )

            page = context.new_page()

            log("Opening site")

            page.goto(
                TARGET_URL,
                wait_until="networkidle",
                timeout=60000
            )

            if timed_out(start_time):
                raise Exception("Timed out after site load")

            save_screenshot(
                page,
                "01_homepage.png"
            )

            log("Click waitlist")

            safe_click(
                page.get_by_role(
                    "button",
                    name="Join the Waitlist"
                )
            )

            page.wait_for_timeout(2000)

            save_screenshot(
                page,
                "02_popup_open.png"
            )

            log("Fill form")

            safe_fill(
                page.locator("#username"),
                username
            )

            safe_fill(
                page.locator("#fullName"),
                fullname
            )

            safe_fill(
                page.locator("#email"),
                email
            )

            page.locator(
                'select[name="mobileNumberCountry"]'
            ).select_option("IN")

            safe_fill(
                page.locator("#mobileNumber"),
                phone
            )

            save_screenshot(
                page,
                "03_form_filled.png"
            )

            log("Submit form")

            safe_click(
                page.locator(
                    "button[type='submit']"
                )
            )

            page.wait_for_timeout(4000)

            if timed_out(start_time):
                raise Exception("Timed out after submit")

            otp = wait_for_otp(
                token,
                req_proxy
            )

            result["otp"] = otp

            enter_otp(page, otp)

            if timed_out(start_time):
                raise Exception("Timed out after OTP")

            complete_all_tasks(page)

            save_screenshot(
                page,
                "done.png"
            )

            result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        result["trace"] = traceback.format_exc()

    finally:
        try:
            if context:
                context.close()
        except:
            pass

        try:
            if browser:
                browser.close()
        except:
            pass

        log(json.dumps(result))


def worker():
    log("Worker started")

    while True:
        try:
            run_single_cycle()
        except Exception as e:
            log(f"Cycle crash: {e}")

        time.sleep(5)


if __name__ == "__main__":
    worker()
