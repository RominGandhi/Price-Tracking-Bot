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

        # ✅ Fetch Current Price
        selector = selectors[store]["price"]
        current_price = await fetch_price_dynamic(url, selector)

        if not current_price:
            await ctx.send("⚠️ **Could not fetch the current price.** Please check the URL.")
            return

        # ✅ Save to Database
        c.execute("""
            INSERT INTO products (user_id, store, product_name, url, css_selector, target_price)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (ctx.author.id, store, answers["product_name"], answers["url"], selector, answers["target_price"]))
        conn.commit()

        # ✅ Confirmation Message with Current Price
        await ctx.send(
            f"✅ **{ctx.author.mention} {answers['product_name']} added!**\n"
            f"💲 **Current Price:** ${current_price:.2f}\n"
            f"🎯 **Target Price:** ${answers['target_price']:.2f}\n"
            f"🔗 [Product Link]({url})"
        )

    except asyncio.TimeoutError:
        await ctx.send("⏳ **You took too long to respond.** Try again!")

    finally:
        active_commands.discard(ctx.author.id)


### 📌 COMMAND: CHECK PRICE ###
@bot.command()
async def check_price(ctx, product_name: str):
    """Allow users to manually check the current price of their saved product."""
    c.execute("SELECT url, css_selector FROM products WHERE user_id = %s AND product_name ILIKE %s", 
              (ctx.author.id, product_name))
    product = c.fetchone()

    if not product:
        await ctx.send(f"⚠️ **No product found with the name '{product_name}' for you.**")
        return

    url, selector = product
    price = await fetch_price_dynamic(url, selector)

    if price:
        await ctx.send(f"✅ **{ctx.author.mention} The current price of '{product_name}' is:** 💲${price:.2f}\n🔗 [Product Link]({url})")
    else:
        await ctx.send(f"⚠️ **Could not fetch the price for '{product_name}'.** Please check the URL or try again later.")


### 📌 AUTOMATED PRICE CHECK ###
@tasks.loop(minutes=30)
async def price_checker():
    """Automatically check product prices and notify if below or at the target price."""
    channel = await bot.fetch_channel(channel_id)

    c.execute("SELECT * FROM products")
    products = c.fetchall()

    for product in products:
        product_id, user_id, store, product_name, url, css_selector, target_price = product
        price = await fetch_price_dynamic(url, css_selector)

        if price:
            mention = f"<@{user_id}>"
            if price < target_price:
                await channel.send(f"🔥 **{mention} Price Drop Alert!** {product_name} is now ${price:.2f}!\n🔗 {url}")
            elif price == target_price:
                await channel.send(f"🎯 **{mention} Your target price matched!** {product_name} is now ${price:.2f}!\n🔗 {url}")



### 📌 COMMAND: SET TARGET PRICE ###
@bot.command()
async def set_target(ctx, product_name: str, target_price: float):
    """Allow users to update their target price for a specific product."""
    c.execute("SELECT * FROM products WHERE user_id = %s AND product_name ILIKE %s", 
              (ctx.author.id, product_name))
    product = c.fetchone()

    if not product:
        await ctx.send(f"⚠️ **No product found with the name '{product_name}' for you.**")
        return

    c.execute("UPDATE products SET target_price = %s WHERE user_id = %s AND product_name ILIKE %s",
              (target_price, ctx.author.id, product_name))
    conn.commit()

    await ctx.send(f"✅ **{ctx.author.mention} Your target price for '{product_name}' has been updated to ${target_price:.2f}!**")


### 📌 COMMAND: REMOVE PRODUCT ###
@bot.command()
async def remove_product(ctx, product_name: str):
    """Allow users to stop tracking a product."""
    c.execute("DELETE FROM products WHERE user_id = %s AND product_name ILIKE %s", 
              (ctx.author.id, product_name))
    
    if c.rowcount == 0:
        await ctx.send(f"⚠️ **No product found with the name '{product_name}' for you.**")
        return

    conn.commit()
    await ctx.send(f"🗑️ **{ctx.author.mention} You have successfully stopped tracking '{product_name}'.**")


### 📌 COMMAND: VIEW ACTIVE ALERTS ###
@bot.command()
async def alerts(ctx):
    """Show all active price alerts for the user."""
    c.execute("SELECT product_name, target_price FROM products WHERE user_id = %s", (ctx.author.id,))
    products = c.fetchall()

    if not products:
        await ctx.send(f"⚠️ **You have no active price alerts.** Use `!add_product` to start tracking.")
        return

    alert_list = "\n".join([f"🔹 **{name}** → 🎯 Target Price: **${price:.2f}**" for name, price in products])
    
    embed = discord.Embed(
        title="📢 Your Active Price Alerts",
        description=alert_list,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


### 📌 COMMAND: LIST TRACKED PRODUCTS ###
@bot.command()
async def list_products(ctx):
    """Show all products the user is currently tracking."""
    c.execute("SELECT product_name, url FROM products WHERE user_id = %s", (ctx.author.id,))
    products = c.fetchall()

    if not products:
        await ctx.send(f"⚠️ **You are not tracking any products.** Use `!add_product` to start tracking.")
        return

    product_list = "\n".join([f"🔹 **[{name}]({url})**" for name, url in products])

    embed = discord.Embed(
        title="🛍️ Your Tracked Products",
        description=product_list,
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)




@bot.command()
@bot.command(name="help_menu")
async def help_menu(ctx):
    """Engaging help command with categories and emojis."""
    
    embed = discord.Embed(
        title="📌 Price Tracking Bot - Help Menu",
        description="Welcome to the **Price Tracking Bot**! 🛍️ Get notified when product prices drop!\n\n"
                    "🔹 **Use the commands below to track products, check prices, and manage your alerts.**",
        color=discord.Color.blue()
    )

    # ✅ Product Tracking Commands
    embed.add_field(
        name="🛒 **Product Tracking**",
        value=(
            "**`!add_product`** → Add a new product for tracking.\n"
            "**`!check_price <product>`** → Check the current price of a saved product.\n"
            "**`!list_products`** → View all products you are tracking."
        ),
        inline=False
    )

    # ✅ Price Alert Commands
    embed.add_field(
        name="📉 **Price Alerts**",
        value=(
            "**`!set_target <product> <price>`** → Set a target price for a product.\n"
            "**`!remove_product <product>`** → Stop tracking a product.\n"
            "**`!alerts`** → View all your active price alerts."
        ),
        inline=False
    )

    # ✅ Bot Management
    embed.add_field(
        name="⚙️ **Bot Management**",
        value=(
            "**`!help_menu`** → Show this help menu.\n"
            "**`!shutdown`** → (Admin only) Shut down the bot."
        ),
        inline=False
    )

    embed.set_footer(text="🚀 Stay notified and save money on your favorite products!")
    
    await ctx.send(embed=embed)















### 🛑 SHUTDOWN BOT ###
@bot.command()
async def shutdown(ctx):
    if ctx.author.id != YOUR_DISCORD_USER_ID:
        await ctx.send("❌ You don't have permission to shut down the bot.")
        return
    await ctx.send("🛑 Shutting down bot...")
    await bot.close()


# ✅ Run bot
bot.run(bot_token)
