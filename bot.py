import discord
from discord.ext import commands, tasks
import json
import asyncio
import os
import psycopg2
import re
from tracker import fetch_price_dynamic  # Ensure this module is correctly implemented

# ✅ Load selectors safely
selectors = {}
try:
    with open("selectors/selectors.json", "r") as file:
        selectors = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    print("❌ ERROR: Invalid or missing selectors.json! Ensure it exists and is properly formatted.")

# ✅ Retrieve bot token from environment variables
bot_token = os.getenv("bot_token")
if not bot_token:
    raise ValueError("❌ ERROR: Missing bot_token! Check your environment variables.")

# ✅ Retrieve database connection URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERROR: Missing DATABASE_URL! Check Railway environment variables.")

# ✅ Connect to PostgreSQL Database
try:
    conn = psycopg2.connect(DATABASE_URL)
    c = conn.cursor()
    print("✅ Connected to PostgreSQL!")

    # ✅ Create table if it does not exist
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            store TEXT,
            product_name TEXT,
            url TEXT,
            css_selector TEXT,
            target_price REAL
        )
    """)
    conn.commit()

except Exception as e:
    print("❌ Database connection failed:", e)
    exit(1)  # Exit if the database connection fails

# ✅ Load config from config.json
with open("config.json", "r") as file:
    config = json.load(file)

channel_id = int(config["channel_id"])  # Ensure channel_id is an integer

# ✅ Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Required for reading messages
intents.members = True  # Enable member events (for welcoming users)
bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Track active commands to prevent duplicate execution
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
    """Guide the user to add a product step-by-step, storing the user ID."""
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel

    if ctx.author.id in active_commands:
        await ctx.send("⚠️ **You already have an active add_product command!**")
        return
    active_commands.add(ctx.author.id)

    try:
        # Store user responses
        answers = {}

        # ✅ Step 1: Store Name
        await ctx.send("🛒 **Enter the store name** (e.g., walmart.ca, amazon.ca, bestbuy.ca):")
        msg = await bot.wait_for("message", check=check, timeout=30)
        store = msg.content.strip().lower()

        if store not in selectors:
            await ctx.send(f"⚠️ **No selector found for {store}.** Add it to `selectors.json`.")
            return
        answers["store"] = store

        # ✅ Step 2: Product Name
        await ctx.send("📦 **Enter the product name:**")
        msg = await bot.wait_for("message", check=check, timeout=30)
        answers["product_name"] = msg.content.strip()

        # ✅ Step 3: Product URL (Validate)
        while True:
            await ctx.send("🔗 **Enter the product URL:**")
            msg = await bot.wait_for("message", check=check, timeout=30)
            url = msg.content.strip()

            if not re.match(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", url):
                await ctx.send("⚠️ **Invalid URL! Please enter a valid product link.**")
                continue  # Ask again if invalid

            answers["url"] = url
            break  # Break loop if valid

        # ✅ Step 4: Target Price (Validate)
        while True:
            await ctx.send("💲 **Enter your target price:**")
            msg = await bot.wait_for("message", check=check, timeout=30)
            try:
                target_price = float(msg.content.strip())
                answers["target_price"] = target_price
                break  # Break loop if valid
            except ValueError:
                await ctx.send("⚠️ **Invalid price! Please enter a valid number.**")

        # ✅ Fetch Price
        selector = selectors[store]["price"]
        price = await fetch_price_dynamic(url, selector)

        if not price:
            await ctx.send("⚠️ **Could not fetch the current price.** Please check the URL.")
            return

        # ✅ Save to Database
        c.execute("""
            INSERT INTO products (user_id, store, product_name, url, css_selector, target_price)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (ctx.author.id, store, answers["product_name"], answers["url"], selector, answers["target_price"]))
        conn.commit()

        # ✅ Confirmation Message
        await ctx.send(f"✅ **{ctx.author.mention} {answers['product_name']} added!**\n💲 **Current Price:** ${price}\n🎯 **Target Price:** ${answers['target_price']}")

    except asyncio.TimeoutError:
        await ctx.send("⏳ **You took too long to respond.** Try again!")

    finally:
        active_commands.discard(ctx.author.id)


### 📌 AUTOMATED TASK: PRICE CHECKER ###
@tasks.loop(minutes=30)
async def price_checker():
    """Automatically check product prices and notify if below target."""
    channel = await bot.fetch_channel(channel_id)  # Fetch channel

    # ✅ Retrieve products from database
    c.execute("SELECT * FROM products")
    products = c.fetchall()

    for product in products:
        product_id, user_id, store, product_name, url, css_selector, target_price = product
        price = await fetch_price_dynamic(url, css_selector)

        if price:
            cleaned_price = float(price)

            # ✅ If price drops below target, notify user
            if cleaned_price <= target_price:
                mention = f"<@{user_id}>"
                await channel.send(
                    f"🔥 **{mention} Price Drop Alert!** 🔥\n"
                    f"**{product_name.capitalize()}** is now **${cleaned_price:.2f}!**\n"
                    f"🎯 **Target Price:** ${target_price:.2f}\n"
                    f"🔗 [Product Link]({url})"
                )


### 🛑 COMMAND: SHUTDOWN BOT (Owner Only) ###
@bot.command()
async def shutdown(ctx):
    """Allow the bot owner to safely shut down the bot."""
    if ctx.author.id != YOUR_DISCORD_USER_ID:
        await ctx.send("❌ **You do not have permission to shut down the bot.**")
        return

    await ctx.send("🛑 **Shutting down bot...**")
    await bot.close()


# ✅ Run bot
bot.run(bot_token)
