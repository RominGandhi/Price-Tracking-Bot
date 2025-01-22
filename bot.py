import discord
from discord.ext import commands, tasks
import json
import asyncio
from tracker import fetch_price_dynamic, load_products, save_products
import os


# Load selectors safely
selectors = {}

try:
    with open("selectors/selectors.json", "r") as file:
        selectors = json.load(file)
except FileNotFoundError:
    print("❌ ERROR: selectors.json not found! Make sure it's inside the 'selectors/' folder.")
except json.JSONDecodeError:
    print("❌ ERROR: selectors.json contains invalid JSON. Fix formatting and retry.")


# Retrieve the token from environment variables
bot_token = os.getenv('bot_token')

if not bot_token:
    raise ValueError("❌ ERROR: Missing bot_token! Check your environment variables.")

# Load config from config.json
with open("config.json", "r") as file:
    config = json.load(file)

channel_id = int(config["channel_id"])  # Ensure channel_id is an integer

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Required for reading messages
intents.members = True  # Enable member events (for welcoming users)
bot = commands.Bot(command_prefix="!", intents=intents)

# Track users who received a welcome message
sent_welcome = set()

### 📌 EVENT: BOT READY ###
@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    print(f"Bot is in these servers: {[guild.name for guild in bot.guilds]}")  # Debugging
    try:
        channel = await bot.fetch_channel(channel_id)
        await channel.send("🚀 Bot is now online and ready!")
    except Exception as e:
        print(f"⚠️ Could not send startup message: {e}")

    if not price_checker.is_running():
        price_checker.start()

### 📌 COMMAND: ADD PRODUCT ###
@bot.command()
async def add_product(ctx):
    """Guide the user to add a product step-by-step, preventing multiple executions."""
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel
    
    # Prevent duplicate execution
    if hasattr(ctx, "is_running") and ctx.is_running:
        return
    ctx.is_running = True  # Mark as running

    try:
        questions = [
            "🛒 **Enter the store name** (e.g., walmart.ca, amazon.ca, bestbuy.ca):",
            "📦 **Enter the product name:**",
            "🔗 **Enter the product URL:**",
            "💲 **Enter your target price:**"
        ]
        
        answers = []
        for question in questions:
            await ctx.send(question)
            msg = await bot.wait_for("message", check=check, timeout=30)
            answers.append(msg.content.strip())

        store, product_name, url, target_price = answers
        target_price = float(target_price)

        # Validate store
        if store not in selectors:
            await ctx.send(f"⚠️ **No selector found for {store}.** Add it to `selectors.json`.")
            return
        
        # Fetch price
        selector = selectors[store]["price"]
        price = await fetch_price_dynamic(url, selector)

        if not price:
            await ctx.send("⚠️ **Could not fetch the current price.** Please check the URL.")
            return

        # Save product
        products = load_products()
        products[product_name] = {"url": url, "css_selector": selector, "target_price": target_price}
        save_products(products)

        # Confirmation message
        await ctx.send(f"✅ **{product_name} added!**\n💲 **Current Price:** ${price}\n🎯 **Target Price:** ${target_price}")

    except asyncio.TimeoutError:
        await ctx.send("⏳ **You took too long to respond.** Try again!")

    finally:
        ctx.is_running = False  # Mark as completed


### 📌 COMMAND: CHECK PRODUCT PRICE ###
@bot.command()
async def check_price(ctx, product_name: str):
    """Check the current price of a product."""
    products = load_products()
    if (product := products.get(product_name)) is None:
        await ctx.send(f"⚠️ Product '{product_name}' not found.")
        return

    selector = product.get("css_selector")
    price = await fetch_price_dynamic(product["url"], selector)

    if price:
        try:
            cleaned_price = float(price)
            target_price = product.get("target_price")
            response = (
                f"**{product_name.capitalize()}**\n"
                f"💲 Current Price: ${cleaned_price:.2f}\n"
                f"🎯 Target Price: ${target_price:.2f}\n" if target_price else ""
                f"🔗 URL: {product['url']}"
            )
            await ctx.send(response)
        except ValueError:
            await ctx.send(f"⚠️ Could not parse the price for '{product_name}'. Raw value: {price}")
    else:
        await ctx.send(f"⚠️ Could not fetch the price for '{product_name}'.")

### 📌 AUTOMATED TASK: PRICE CHECKER ###
@tasks.loop(minutes=30)
async def price_checker():
    """Automatically check product prices and notify if below target."""
    products = load_products()
    channel = await bot.fetch_channel(channel_id)  # Fetch channel

    for product_name, details in products.items():
        selector = details.get("css_selector")
        price = await fetch_price_dynamic(details["url"], selector)

        if price:
            try:
                cleaned_price = float(price)
                if details.get("target_price") and cleaned_price <= details["target_price"]:
                    await channel.send(
                        f"🔥 **Price Drop Alert!** 🔥\n"
                        f"**{product_name.capitalize()}** is now ${cleaned_price:.2f}!\n"
                        f"🎯 Target Price: ${details['target_price']:.2f}\n"
                        f"🔗 URL: {details['url']}"
                    )
            except ValueError:
                print(f"⚠️ Error converting price '{price}' for {product_name}.")

# Run bot
bot.run(bot_token)
