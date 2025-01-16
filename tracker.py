import json
import os
from playwright.async_api import async_playwright
import re

DATA_FILE = "data/products.json"

def load_products():
    """Load product data from JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    else:
        return {}

def save_products(products):
    """Save product data to JSON file."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as file:
        json.dump(products, file, indent=4)
async def fetch_price_dynamic(url, selector=None):
    """
    Fetch the price dynamically from a given URL using Playwright Async API.
    :param url: URL of the product page.
    :param selector: CSS selector for the price element (optional).
    :return: Extracted price as a string or None if not found.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set to False for debugging
        page = await browser.new_page()

        try:
            print(f"Fetching URL: {url}")
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)

            if selector:
                print(f"Using selector: {selector}")
                await page.wait_for_selector(selector, timeout=30000)
                price_element = await page.query_selector(selector)
                if price_element:
                    price_text = await price_element.text_content()
                    print(f"Raw Price Text: {price_text}")

                    # Clean the extracted text
                    cleaned_price = re.sub(r"[^\d\.]", "", price_text).strip()  # Remove non-numeric characters
                    print(f"Cleaned Price: {cleaned_price}")
                    return cleaned_price

            print(f"No price found using selector '{selector}'")
            return None
        except Exception as e:
            print(f"Error fetching price: {e}")
            return None
        finally:
            await browser.close()