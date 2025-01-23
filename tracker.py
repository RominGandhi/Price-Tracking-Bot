import json
import os
from playwright.async_api import async_playwright
import re

DATA_FILE = "data/products.json"

def load_products():
    """Load product data from JSON file safely."""
    if not os.path.exists(DATA_FILE):
        return {}  # Return an empty dictionary if no file exists
    
    try:
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}  # Return empty dictionary if JSON is corrupted

def save_products(products):
    """Save product data to JSON file safely."""
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
        browser = await p.chromium.launch(headless=True)  # Headless mode for Railway
        page = await browser.new_page()

        try:
            print(f"🔍 Debug: Fetching URL: {url}")
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)

            if selector:
                print(f"🔍 Debug: Using Selector: {selector}")
                await page.wait_for_selector(selector, timeout=30000)
                price_element = await page.query_selector(selector)
                
                if price_element:
                    price_text = await price_element.text_content()
                    print(f"💰 Raw Price Text: {price_text}")

                    # Clean and format the extracted price
                    cleaned_price = re.sub(r"[^\d\.]", "", price_text).strip()  # Remove non-numeric characters
                    if cleaned_price:
                        return round(float(cleaned_price), 2)  # Ensure valid price format

            print(f"❌ Debug: No price element found using selector '{selector}'")
            return None
        except Exception as e:
            print(f"❌ Debug: Error fetching price: {e}")
            return None
        finally:
            await browser.close()
