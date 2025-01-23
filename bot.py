import discord
from discord.ext import commands, tasks
import json
import asyncio
import os
from tracker import fetch_price_dynamic, load_products, save_products

# Load selectors safely
selectors = {}
try:
    with open("selectors/selectors.json", "r") as file:
        selectors = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    print("❌ ERROR: Invalid or missing selectors.json! Ensure it exists and is properly formatted.")

# Retrieve the token from environment variables
bot_token = os.getenv("bot_token")
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

# Track active commands to prevent duplicate execution
active_commands = set()
bot_started = False  # Prevent multiple instances

### 📌 EVENT: BOT READY ###
@bot.event
async def on_ready():
    global bot_started
    if bot_started:
        return  # Prevent multiple executions
    bot_started = True  # Set flag to True

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
    if ctx.author.id in active_commands:
        await ctx.send("⚠️ **You already have an active add_product command!**")
        return
    active_commands.add(ctx.author.id)  # Mark as running

    try:
        questions = [
            "🛒 **Enter the store name** (e.g., walmart.ca, amazon.ca, bestbuy.ca):",
            "📦 **Enter the product name:**",
            "🔗 **Enter the product URL:**",
            "💲 **Enter your target price:**",
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
        if price:
            try:
                price = round(float(price), 2)  # Ensure correct formatting
            except ValueError:
                await ctx.send("⚠️ **Error: Price value is invalid.**")
                return


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
        active_commands.discard(ctx.author.id)  # Remove user to allow new commands


### 📌 COMMAND: CHECK PRODUCT PRICE ###
@bot.command()
async def check_price(ctx, product_name: str):
    """Check the current price of a product."""
    products = load_products()
    if (product := products.get(product_name)) is None:
        await ctx.send(f"⚠️ **Product '{product_name}' not found.**")
        return

    selector = product.get("css_selector")
    price = await fetch_price_dynamic(product["url"], selector)

    if price:
        try:
            cleaned_price = round(float(price), 2)  # Ensure rounded price
            target_price = product.get("target_price")
            response = f"""**{product_name.capitalize()}**
            💲 **Current Price:** ${cleaned_price:.2f}
            🎯 **Target Price:** ${target_price:.2f}""" if target_price else ""

            response += f"\n🔗 [Product Link]({product['url']})"
            await ctx.send(response)

        except ValueError:
            await ctx.send(f"⚠️ **Could not parse the price for '{product_name}'.** Raw value: {price}")
    else:
        await ctx.send(f"⚠️ **Could not fetch the price for '{product_name}'.**")


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
                cleaned_price = round(float(price), 2)  # Ensure rounded price
                if details.get("target_price") and cleaned_price <= details["target_price"]:
                    await channel.send(
                        f"🔥 **Price Drop Alert!** 🔥\n"
                        f"**{product_name.capitalize()}** is now ${cleaned_price:.2f}!\n"
                        f"🎯 Target Price: ${details['target_price']:.2f}\n"
                        f"🔗 [Product Link]({details['url']})"
                    )
            except ValueError:
                print(f"⚠️ **Error converting price '{price}' for {product_name}.**")


# Run bot
bot.run(bot_token)
