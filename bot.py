import discord
from discord.ext import commands, tasks
from tracker import fetch_price_dynamic, load_products, save_products
import json
import os

# Load config
with open("config.json", "r") as file:
    config = json.load(file)

bot_token = os.getenv("DISCORD_BOT_TOKEN")  # Ensure this matches Heroku's variable

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Required if reading message content
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    if not price_checker.is_running():
        price_checker.start()

@bot.command()
async def add_product(ctx, product_name: str, url: str, selector: str = None, target_price: float = None):
    """Add a product to track."""
    products = load_products()
    products[product_name] = {
        "url": url,
        "css_selector": selector,
        "target_price": target_price
    }
    save_products(products)
    await ctx.send(f"Added '{product_name}' with target price {target_price}.")

@bot.command()
async def check_price(ctx, product_name: str):
    """Check the current price of a product."""
    products = load_products()
    if product_name not in products:
        await ctx.send(f"Product '{product_name}' not found.")
        return

    details = products[product_name]
    selector = details.get("css_selector")
    price = await fetch_price_dynamic(details["url"], selector)  # Ensure fetch_price_dynamic is async

    if price:
        try:
            cleaned_price = float(price)
            target_price = float(details["target_price"])

            await ctx.send(
                f"**{product_name.capitalize()}**\n"
                f"Current Price: ${cleaned_price:.2f}\n"
                f"Target Price: ${target_price:.2f}\n"
                f"URL: {details['url']}"
            )
        except ValueError:
            await ctx.send(f"Could not parse the price for '{product_name}'. Raw value: {price}")
    else:
        await ctx.send(f"Could not fetch the price for '{product_name}'.")

@tasks.loop(minutes=30)
async def price_checker():
    """Automatically check product prices."""
    products = load_products()
    channel = await bot.fetch_channel(int(config["channel_id"]))  # Use fetch_channel()

    for product_name, details in products.items():
        selector = details.get("css_selector")
        price = await fetch_price_dynamic(details["url"], selector)  # Ensure this function is async

        if price:
            try:
                cleaned_price = float(price)
                if details.get("target_price") and cleaned_price <= details["target_price"]:
                    await channel.send(
                        f"🔥 **Price Drop Alert!** 🔥\n"
                        f"**{product_name.capitalize()}** is now ${cleaned_price:.2f}!\n"
                        f"Target Price: ${details['target_price']:.2f}\n"
                        f"URL: {details['url']}"
                    )
            except ValueError:
                print(f"Error converting price '{price}' for {product_name}.")

# Ensure bot token exists
if not bot_token:
    raise ValueError("❌ ERROR: Missing DISCORD_BOT_TOKEN! Set it as an environment variable.")

bot.run(bot_token)
