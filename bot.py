import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import asyncio
import random
import string
from datetime import datetime, timezone
import logging
import aiohttp
import os
import json
from discord import app_commands
import html



logging.basicConfig(level=logging.INFO)

# ---------------- ALLOWED SERVERS CHECK ----------------
ALLOWED_GUILDS = [1278435741973745735, 1436801793924403234, 1436832738723365004]

def allowed_server():
    async def predicate(ctx):
        if ctx.guild and ctx.guild.id in ALLOWED_GUILDS:
            return True
        await ctx.send("This bot only works in approved servers.", ephemeral=True)
        return False
    return commands.check(predicate)

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)


# ---------------- TRADING SYSTEM ----------------
class TradeModal(Modal):
    def __init__(self, action):
        super().__init__(title=f"{action} Request")
        self.action = action
        self.username_input = TextInput(label="Enter your username")
        self.item_input = TextInput(label="Item Name")
        self.ms_input = TextInput(label="Amount (m/s)")
        self.add_item(self.username_input)
        self.add_item(self.item_input)
        self.add_item(self.ms_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        item_name = self.item_input.value
        try:
            ms_amount = int(self.ms_input.value)
        except:
            return await interaction.response.send_message("Invalid m/s amount.", ephemeral=True)

        transaction_id = random_transaction_id()
        transactions[transaction_id] = {
            "user": interaction.user.mention,
            "username": username,
            "item": item_name,
            "ms": ms_amount,
            "action": self.action,
            "status": "Pending"
        }

        if self.action == "Buy":
            price_text = f"{ms_amount} m/s ≈ ${ms_amount*0.25:,.2f}"
        else:
            anchors = [(1,50),(10,125),(50,290),(100,600),(150,900)]
            def brainrot_price(ms: int) -> int:
                for i in range(len(anchors)-1):
                    m1,r1 = anchors[i]
                    m2,r2 = anchors[i+1]
                    if m1 <= ms <= m2:
                        return round(r1 + (r2-r1)/(m2-m1)*(ms-m1))
                return anchors[-1][1]
            rbx = brainrot_price(ms_amount)
            price_text = f"We offer to buy your brainrot for {rbx} Robux"

        embed = discord.Embed(
            title=f"{self.action} Offer: {item_name}",
            description=price_text,
            color=MAIN_COLOR
        )
        profile_link = f"https://www.roblox.com/search/users?keyword={username}"
        embed.add_field(name="Username", value=f"[{username}]({profile_link})", inline=True)
        embed.add_field(name="Transaction ID", value=transaction_id)
        embed.set_thumbnail(url=SERVER_ICON)

        view = View()
        view.add_item(Button(label="Accept", style=discord.ButtonStyle.green, custom_id=f"accept_{transaction_id}"))
        view.add_item(Button(label="Decline", style=discord.ButtonStyle.red, custom_id=f"decline_{transaction_id}"))

        await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    custom_id = interaction.data.get("custom_id")
    if not custom_id:
        return

    if custom_id in ["buy","sell"]:
        action = "Buy" if custom_id=="buy" else "Sell"
        await interaction.response.send_modal(TradeModal(action))
        return

    if custom_id.startswith(("accept_","decline_")):
        tid = custom_id.split("_")[1]
        if tid not in transactions:
            return await interaction.response.send_message("Transaction not found.", ephemeral=True)

        transaction = transactions[tid]
        channel = interaction.channel
        if custom_id.startswith("accept_"):
            transaction["status"] = "Accepted"
            message_text = "Offer accepted. Wait until a staff responds."
        else:
            transaction["status"] = "Declined"
            message_text = "Offer declined. DM staff if needed."

        await interaction.response.send_message(message_text, ephemeral=True)

@bot.command()
async def transaction(ctx, tid: str):
    if tid not in transactions:
        return await ctx.send("Transaction ID not found.")
    t = transactions[tid]
    embed = discord.Embed(
        title=f"Transaction {tid} Details",
        description=f"Status: {t['status']}\nAction: {t['action']}\nItem: {t['item']}\nAmount: {t['ms']}\nUsername: {t['username']}\nUser: {t['user']}",
        color=MAIN_COLOR
    )
    await ctx.send(embed=embed)

# ---------------- TICKET PANEL ----------------
@bot.command()
async def ticketpanel(ctx):
    if TICKET_CATEGORY is None:
        return await ctx.send("Ticket system not set up yet.")
    embed = discord.Embed(
        title="Open a Ticket",
        description="Click the button below to open a private ticket.",
        color=MAIN_COLOR
    )
    view = View()
    async def open_ticket_callback(interaction: discord.Interaction):
        ticket_name = f"ticket-{interaction.user.name}"
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await TICKET_CATEGORY.create_text_channel(ticket_name, overwrites=overwrites)
        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)
    btn = Button(label="Open Ticket", style=discord.ButtonStyle.green)
    btn.callback = open_ticket_callback
    view.add_item(btn)
    await ctx.send(embed=embed, view=view)

# ---------------- BOT EVENTS ----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    send_fake_embed.start()


# --------------------
# Brainrot anchors / tiers
# --------------------
anchors = [(1, 50), (10, 125), (50, 290), (100, 600), (150, 900)]
ROB_TO_EURO = 3.45 / 1000  # 1000 Robux = 3.45€


# --------------------
# Pending orders / waitlist
# --------------------
pending_orders = {}
latest_orders = {}
WAITLIST_CHANNEL_ID = 1434550699919806577

# --------------------
# Brainrot / Currency Commands
#
WAITLIST_ROLE = 1280146581948989482
REMOVEW_ROLE = 1434566190340112525


async def clear_roles_and_add(member: discord.Member, role_id: int):
    try:
        roles_to_remove = [r for r in member.roles if r != member.guild.default_role]
        await member.remove_roles(*roles_to_remove, reason="waitlist/removew command")
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role, reason="waitlist/removew command")
    except Exception:
        pass  # stay silent


@bot.command()
@commands.has_permissions(manage_roles=True)
async def waitlist(ctx, member: discord.Member):
    await ctx.message.delete()
    await clear_roles_and_add(member, WAITLIST_ROLE)


@bot.command()
@commands.has_permissions(manage_roles=True)
async def removew(ctx, member: discord.Member):
    await ctx.message.delete()
    await clear_roles_and_add(member, REMOVEW_ROLE)


# optional: silent error handling
@waitlist.error
@removew.error
async def silent_error(ctx, error):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    # ignore everything silently


@bot.command()
@allowed_server()
async def robux(ctx, amount: float):
    euro = amount * ROB_TO_EURO
    embed = discord.Embed(title="Robux → Euro", description=f"{amount:.0f} Robux ≈ €{euro:.2f}", color=MAIN_COLOR)
    await ctx.send(embed=embed)

@bot.command()
@allowed_server()
async def euro(ctx, amount: float):
    robux_amount = round(amount / ROB_TO_EURO)
    embed = discord.Embed(title="Euro → Robux", description=f"€{amount:.2f} ≈ {robux_amount} Robux", color=MAIN_COLOR)
    await ctx.send(embed=embed)

# --------------------
# Utility / Info / Menu Commands
@bot.command()
async def c(ctx):
    text = """```# Buying your brainrots
`1m/s = 50 robux
10m/s = 125 robux
50m/s = 290 robux
100m/s = 600 robux
150m/s = 900 robux`

**__If you need proof or vouches type proof__**```"""

    embed = discord.Embed(
        title="Brainrot Price Menu",
        description=text,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


OWNER_ID = 1416513969689989211  # your id (int)

def owner_only():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)



@bot.command(name="invitescam")
@commands.is_owner()
async def invitescam(ctx):
    await ctx.message.delete()

    embed = discord.Embed(
        title="You have been scammed by Our Team | Join us",
        description=(
            "We are sorry that you have been scammed\n\n"
            "You are now invited to become a hitter.\n"
            "You get to keep most of your profits and earn a lot of money\n"
            "You can earn thousands of Robux and Brainrots by joining our marketplace.\n"
            "Use `$join 1234` to join our scamming group or `$leave` to leave."
        ),
        color=discord.Color.from_rgb(255, 255, 255)
    )

    # fallback-safe avatar handling
    try:
        avatar = ctx.author.avatar_url
    except AttributeError:
        avatar = None

    embed.set_footer(
        text=f"Invited by {ctx.author}",
        icon_url=avatar
    )

    await ctx.send(embed=embed)



SETUP_ROLE_ID = 1434634819136127046  # role allowed to use $copy

def has_c_permission():
    async def predicate(ctx):
        role_ids = [role.id for role in ctx.author.roles]
        return SETUP_ROLE_ID in role_ids or ctx.author.guild_permissions.administrator
    return commands.check(predicate)

def admin_only():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)


@bot.command()
@admin_only()
async def add(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send("Usage: `$add @user`")

    try:
        # give member permission to view and send messages in this channel
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"{member.mention} has been added to the ticket.")
    except Exception as e:
        await ctx.send(f"Failed to add {member.mention}: `{e}`")

codes = {}
role_id = 1434634819136127046  # role that can use $code

@bot.command()
async def code(ctx):
    if role_id not in [role.id for role in ctx.author.roles]:
        await ctx.send("you don’t have permission to use this command.")
        return

    new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    codes[new_code] = ctx.author.id

    embed = discord.Embed(
        title="Special Code Generated",
        description=f"Your code: **{new_code}**\n\nInvite people using this link:\nhttps://discord.gg/CetndyXTyX\n\nTell them to use:\n`$redeem {new_code}` to get a discount.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command()
async def redeem(ctx, code: str = None):
    if not code:
        await ctx.send("you need to provide a code.")
        return

    if code not in codes:
        await ctx.send("invalid or expired code.")
        return

    creator_id = codes[code]
    embed = discord.Embed(
        title="Code Redeemed",
        description=f"Successfully redeemed `{code}`!\nCode belongs to <@{creator_id}>.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command()
async def cs(ctx, *, name: str):
    await ctx.channel.edit(name=name)
    await ctx.send("👍")


import discord
from discord.ext import commands
import io
import uuid
from datetime import datetime
import html as htmllib  # for escaping

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="$", intents=intents)

def build_discord_html(saved_by, source_channel, saved_at_iso, entries, tx_id):
    """Return bytes of a full HTML page showing the conversation in Discord style."""
    css = """
    body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; background:#36393f; color:#dcddde; margin:0; padding:0; }
    .container { max-width:900px; margin:20px auto; padding:20px; background:#2f3136; border-radius:8px; }
    .header { margin-bottom:20px; }
    .header h1 { font-size:20px; margin:0; }
    .meta { font-size:12px; color:#72767d; }
    .msg { display:flex; margin-bottom:15px; }
    .avatar { width:40px; height:40px; border-radius:50%; margin-right:10px; }
    .content { max-width:850px; }
    .author { font-weight:600; color:#fff; }
    .time { font-size:11px; color:#72767d; margin-left:6px; }
    .text { font-size:14px; line-height:1.4; margin-top:2px; white-space:pre-wrap; }
    .attachments img { max-width:400px; border-radius:5px; margin-top:5px; }
    .attachments a { color:#00b0f4; font-size:12px; display:block; margin-top:2px; word-break:break-all; }
    footer { margin-top:20px; font-size:12px; color:#72767d; }
    """

    html_entries = []
    for e in entries:
        author_html = htmllib.escape(e["author_name"])
        discrim_html = htmllib.escape(e["discriminator"])
        ts_html = htmllib.escape(e["timestamp"])
        content_html = htmllib.escape(e["content"]).replace("\n", "<br>")
        avatar_url = htmllib.escape(e["avatar_url"])

        attachments_html = ""
        if e["attachments"]:
            parts = []
            for a in e["attachments"]:
                safe_url = htmllib.escape(a)
                if any(a.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                    parts.append(f'<div class="attachments"><img src="{safe_url}" alt="attachment"></div>')
                else:
                    parts.append(f'<div class="attachments"><a href="{safe_url}" target="_blank">{safe_url}</a></div>')
            attachments_html = "".join(parts)

        html_entries.append(
            f'<div class="msg">'
            f'<img class="avatar" src="{avatar_url}" alt="avatar">'
            f'<div class="content">'
            f'<div class="author">{author_html}#{discrim_html}<span class="time"> • {ts_html}</span></div>'
            f'<div class="text">{content_html}</div>'
            f'{attachments_html}'
            f'</div>'
            f'</div>'
        )

    html_body = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Transaction {htmllib.escape(tx_id)}</title>
<style>{css}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Saved Conversation — Transaction {htmllib.escape(tx_id)}</h1>
    <div class="meta">Saved by {htmllib.escape(saved_by)} on {htmllib.escape(saved_at_iso)}</div>
    <div class="meta">Source channel: {htmllib.escape(source_channel)}</div>
  </div>
  {"".join(html_entries)}
  <footer>Generated {htmllib.escape(saved_at_iso)}</footer>
</div>
</body>
</html>"""
    return html_body.encode("utf-8")

@bot.command()
async def save(ctx, limit: int = 500):
    """Save recent conversation into a Discord-style HTML 'website'."""
    msgs = []
    async for m in ctx.channel.history(limit=limit):
        timestamp = m.created_at.astimezone().isoformat(timespec='seconds')
        author_name = m.author.name
        discriminator = m.author.discriminator
        content = m.content or ""
        avatar_url = m.author.avatar.url if m.author.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        attachments = [a.url for a in m.attachments] if m.attachments else []
        msgs.append((m.created_at, {"timestamp": timestamp, "author_name": author_name,
                                    "discriminator": discriminator, "content": content,
                                    "avatar_url": avatar_url, "attachments": attachments}))

    if not msgs:
        await ctx.reply("No messages found to save.")
        return

    msgs.sort(key=lambda t: t[0])
    entries = [item for _, item in msgs]

    tx_id = uuid.uuid4().hex[:12]
    saved_at_iso = datetime.now().isoformat(timespec='seconds')
    saved_by = f"{ctx.author} ({ctx.author.id})"
    source_channel = f"{ctx.channel} ({ctx.channel.id})"

    html_bytes = build_discord_html(saved_by, source_channel, saved_at_iso, entries, tx_id)
    filename = f"transaction_{tx_id}.html"
    file_obj = io.BytesIO(html_bytes)
    file_obj.seek(0)

    target_channel_id = 1434482848299094036
    target_channel = bot.get_channel(target_channel_id)
    if target_channel is None:
        try:
            target_channel = await bot.fetch_channel(target_channel_id)
        except Exception as e:
            await ctx.reply(f"Failed to find target channel `{target_channel_id}`: {e}")
            return

    try:
        sent_msg = await target_channel.send(content=f"Transaction ID: `{tx_id}`", file=discord.File(fp=file_obj, filename=filename))
    except Exception as e:
        await ctx.reply(f"Failed to send to target channel: {e}")
        return

    link = sent_msg.attachments[0].url if sent_msg.attachments else "link unavailable"

    embed = discord.Embed(
        title="Conversation Saved (Discord Style HTML)",
        description=f"Transaction created and uploaded to <#{target_channel_id}>.",
        color=discord.Color.green()
    )
    embed.add_field(name="Transaction ID", value=tx_id, inline=False)
    embed.add_field(name="Open HTML", value=link, inline=False)
    embed.set_footer(text=f"Requested by {ctx.author.id}")

    await ctx.reply(embed=embed)


@bot.command()
async def howto(ctx):
    # howto ref
    footer_ref = f"Requested by {ctx.author.id}."

    # embed with placeholders only (no actionable instructions)
    embed = discord.Embed(
        title='Want to know how to hit?',
        description='Read this full guide to do hit',
        color=discord.Color.from_rgb(255, 255, 255)
    )

    embed.add_field(
        name="# FULL GUIDE",
        value=(
            """Quick Tutorial on what we do: \n
    `1.` Find Trades In any trading server \n
    `2.` Send them the server and tell them that you will do the trade there \n 
    `3.` Send them this server and make a fake ticket \n
    `4.` Use $create  @discorduser / discord user id  (inside  https://discord.com/channels/1278435741973745735/1436683576648400988) \n
    `4.` We scam them and split u 50/50 \n
    `5.` Here you go you made your first scam \n
         **Full guide** \n
||https://sendvid.com/c34ady11?secret=85f705ed-ae65-4412-9002-b6828bfedec8||"""
        ),
        inline=False
    )

    embed.set_footer(text='SCAMMER MARKETPLACE • EARN QUICKLY')

    await ctx.send(embed=embed)

brainrot_prices = {
    1: 50,
    10: 125,
    50: 290,
    100: 600,
    150: 900
}

@bot.command()
async def dmc(ctx):
    msg = (
        "**Step 1:** Find target servers.\n"
        "**Step 2:** Paste this message there:\n\n"
        "```# Buying your brainrots\n"
        "1m/s = 50 Robux\n"
        "10m/s = 125 Robux\n"
        "50m/s = 290 Robux\n"
        "100m/s = 600 Robux\n"
        "150m/s = 900 Robux```\n"
        "**If you need proof or vouches, type `proof`.**\n\n"
        "**Step 3:** Once someone DMs you, tell them to join the server:**\n"
        "https://discord.gg/CetndyXTyX\n\n"
        "**Step 4:** Ask them to redeem your code using:**\n"
        "`$redeem (your code)`"
    )
    embed = discord.Embed(
        title="Direct Message Campaign Guide",
        description=msg,
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)



@bot.command()
@allowed_server()
async def sc(ctx):
    message = """```# Selling my brainrots
`1m/s = 0,05$
10m/s = 0,25$
50m/s = 1$
100m/s = 2$
150m/s = 4$`

**__If you need proof or vouches type proof__**
**__These are all estimated prices - Real prices in dms__**```"""
    await ctx.send(message)



@bot.command(name="sell")
@allowed_server()
async def sell(ctx, amount: int):
    """
    Sell command that calculates USD price for given amount (m/s).
    Shows a 'discount' style — final price is 40% bump but displayed as a sale.
    """
    if amount < 1 or amount > 1_000_000_000:
        await ctx.send("Amount must be between 1 and 1,000,000,000 m/s")
        return

    # USD anchors from your rates
    usd_anchors = [
        (1, 0.05),
        (10, 0.25),
        (50, 1.00),
        (100, 2.00),
        (150, 4.00),
    ]

    def usd_price(ms: int) -> float:
        for m, u in usd_anchors:
            if ms == m:
                return float(u)

        for i in range(len(usd_anchors) - 1):
            m1, u1 = usd_anchors[i]
            m2, u2 = usd_anchors[i + 1]
            if m1 < ms < m2:
                slope = (u2 - u1) / (m2 - m1)
                return float(u1 + slope * (ms - m1))

        last_m, last_u = usd_anchors[-1]
        prev_m, prev_u = usd_anchors[-2]
        slope = (last_u - prev_u) / (last_m - prev_m)
        return float(last_u + slope * (ms - last_m))

    base_usd = usd_price(amount)
    bumped_usd = base_usd * 1.40  # +40%

    # make the fake “original” price about 25% higher than the bumped one
    original_usd = bumped_usd * 1.25

    def fmt(x: float) -> str:
        return f"${x:,.2f}"

    embed = discord.Embed(
        title="🔥 Sell Calculator - Limited Time Sale 🔥",
        color=discord.Color.from_rgb(0, 122, 255)
    )
    embed.add_field(name="Amount", value=f"{amount} m/s", inline=True)
    embed.add_field(
        name="Original Price",
        value=f"~~{fmt(original_usd)}~~",
        inline=True
    )
    embed.add_field(
        name="Now",
        value=f"{fmt(bumped_usd)}",
        inline=True
    )
    embed.set_footer(text="Sale ends soon. Don't miss out!")

    await ctx.send(embed=embed)

# --------------------
# Brainrot → Robux
# --------------------
@bot.command()
@allowed_server()
async def brainrot(ctx, amount: int):
    if amount < 1 or amount > 1_000_000_000:
        await ctx.send("Amount must be between 1 and 1,000,000,000 m/s")
        return

    # anchors: (m/s, robux)
    anchors = [(1,50),(10,125),(50,290),(100,600),(150,900)]

    def brainrot_price(ms: int) -> int:
        if ms < 1: return 0
        for i in range(len(anchors)-1):
            m1, r1 = anchors[i]
            m2, r2 = anchors[i+1]
            if m1 <= ms <= m2:
                return round(r1 + (r2-r1)/(m2-m1)*(ms-m1))
        last_m, last_r = anchors[-1]
        prev_m, prev_r = anchors[-2]
        increment = (last_r-prev_r)/(last_m-prev_m)
        return round(last_r + (ms-last_m)*increment)

    rbx = brainrot_price(amount)
    embed = discord.Embed(title="Brainrot Calculator",
                          description=f"{amount} m/s ≈ {rbx} Robux",
                          color=discord.Color.green()
                          )
    await ctx.send(embed=embed)


@bot.command()
async def join(ctx, code: str):
        role = ctx.guild.get_role(1434634819136127046)
        await ctx.author.add_roles(role)
        await ctx.send(f"**Welcome!**\nThank you {ctx.author.mention} for joining us")

@bot.command()
async def leave(ctx):
    await ctx.author.ban(reason="User chose to leave")



@bot.command()
async def gamepass(ctx):
    # delete user command message
    await ctx.message.delete()

    # create embed
    embed = discord.Embed(
        title="Robux Gifting Info",
        description="Learn how we handle Robux gifting and why we avoid Pls Donate.",
        color=discord.Color.from_rgb(255, 255, 255)  # white side color
    )

    embed.add_field(
        name="1. Gamepass Gifting",
        value=(
            "- You create a gamepass in your own Roblox game.\n"
            "- We buy your gamepass for the Robux amount agreed.\n"
            "- Roblox takes a 30% tax, so you receive 70% after pending Robux clears.\n"
            "- It takes about 3–5 days for pending Robux to arrive."
        ),
        inline=False
    )

    embed.add_field(
        name="2. In-Game Gifting",
        value=(
            "- We gift Robux through a Roblox game’s donation board or developer product.\n"
            "- Same 30% Roblox tax applies, but it’s faster and more direct."
        ),
        inline=False
    )

    embed.add_field(
        name="3. Why We Don’t Use Pls Donate",
        value=(
            "- Pls Donate adds its own 10% fee on top of Roblox’s 30% tax.\n"
            "- You lose 40% total instead of 30%.\n"
            "- Gamepass or in-game gifting saves Robux and gives you more."
        ),
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command()
async def adduser(ctx, username):
    fake_id = random.randint(1000000, 9999999)

    embed = discord.Embed(
        title="✨ Add User System",
        description=f"🔍 Logging into **ID {fake_id}**...",
        color=discord.Color.blurple()
    )
    msg = await ctx.send(embed=embed)

    await asyncio.sleep(1.5)
    embed.description = f"✅ Logged into **ID {fake_id}**\n⏳ Checking for friend request from **{username}**..."
    embed.color = discord.Color.gold()
    await msg.edit(embed=embed)

    await asyncio.sleep(2)
    embed.description = (
        f"✅ Logged into **ID {fake_id}**\n"
        f"✅ Friend request from **{username}** found\n\n"
        f"🎉 Successfully added **{username}**!\n\n"
        f"[Join me on Roblox](https://www.roblox.com/share?code=f6c7fa32ecf3754eab7bd137935ef71a&type=Server)"
    )
    embed.color = discord.Color.green()
    embed.set_footer(text="Speclift Tools Service • Roblox Connection System 💻")
    await msg.edit(embed=embed)


 # dodgerblue
DB = {}  # simple in-memory database, replace with real DB if needed

SETUP_ROLE_ID = 1434634819136127046  # role allowed to use $setup


def has_setup_permission():
    async def predicate(ctx):
        role_ids = [role.id for role in ctx.author.roles]
        return SETUP_ROLE_ID in role_ids or ctx.author.guild_permissions.administrator
    return commands.check(predicate)


@bot.command()
async def channel(ctx, channel_id: int):
    guild_id = 1278435741973745735
    link = f"https://discord.com/channels/{guild_id}/{channel_id}"
    await ctx.send(f"Here’s your channel link: {link}")




DB_FILE = "db.json"

# load DB from file
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        DB = json.load(f)
else:
    DB = {}

# helper to save DB
def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(DB, f)

# delete a user's setup
@bot.command()
@commands.has_permissions(administrator=True)  # replace with your own permission check if needed
async def dsetup(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    if str(member.id) in DB:
        del DB[str(member.id)]
        save_db()
        await ctx.send(f"{member.mention}'s setup has been deleted.")
    else:
        await ctx.send(f"{member.mention} has no setup to delete.")


# db placeholder
DB = {}

def save_db():
    pass  # replace with your saving logic


# -------------------- SETUP COMMAND --------------------
@bot.command()
async def setup(ctx):
    await ctx.send("Enter your Roblox username:")

    def check_username(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        username_msg = await bot.wait_for("message", check=check_username, timeout=60)
        username = username_msg.content.strip()
    except:
        return await ctx.send("Timeout. Setup cancelled.")

    # fixed private server link
    server_link = "https://www.roblox.com/share?code=f6c7fa32ecf3754eab7bd137935ef71a&type=Server"

    # save to db
    DB[str(ctx.author.id)] = {"username": username, "server_link": server_link}
    save_db()

    await ctx.send(
        f"Welcome {ctx.author.mention}\nYour Roblox username: {username}\nYour private server link: {server_link}"
    )

# -------------------- SCAMMERS COMMAND --------------------
@bot.command()
@commands.has_permissions(administrator=True)
async def scammers(ctx):
    if not DB:
        return await ctx.send("No users have setup yet.")

    for user_id, data in DB.items():
        uid_str = str(user_id)
        username = data.get("username", "N/A")
        server_link = "https://www.roblox.com/share?code=f6c7fa32ecf3754eab7bd137935ef71a&type=Server"
        roblox_search_url = f"https://www.roblox.com/search/users?keyword={username}"

        # try to resolve member in the guild
        member = ctx.guild.get_member(int(uid_str)) if uid_str.isdigit() else None
        if member:
            discord_display = f"{member.name} ({member.mention})"
        else:
            discord_display = f"User ID: {uid_str} (<@{uid_str}>)"

        embed = discord.Embed(title="Scammer Info", color=0x22DD22)
        embed.add_field(name="Discord", value=discord_display, inline=False)
        embed.add_field(name="Discord ID", value=uid_str, inline=True)
        embed.add_field(name="Roblox Username", value=f"[{username}]({roblox_search_url})", inline=True)
        embed.add_field(name="Private Server Link", value=f"[Join]({server_link})", inline=False)

        embed.set_footer(text="Saved in db.json")
        embed.timestamp = datetime.now(timezone.utc)

        try:
            await ctx.send(embed=embed)
        except Exception:
            text = (
                f"Discord: {discord_display}\n"
                f"Discord ID: {uid_str}\n"
                f"Roblox: {username} ({roblox_search_url})\n"
                f"Server: {server_link}\n"
            )
            await ctx.send(f"```{text}```")

# -------------------- MESSAGE TRACKING --------------------
last_bot_message = {}  # key: channel_id, value: message object

async def send_single(ctx, content=None, embed=None):
    """
    Sends a message or embed and deletes the previous bot message in the same channel
    """
    channel_id = ctx.channel.id

    # delete previous bot message in this channel
    if channel_id in last_bot_message:
        try:
            await last_bot_message[channel_id].delete()
        except:
            pass

    # send new message
    msg = await ctx.send(embed=embed) if embed else await ctx.send(content)

    # store message
    last_bot_message[channel_id] = msg
    return msg


@bot.command()
async def hoffer(ctx, member: discord.Member, *, payment_and_item: str):
    role_ids = [role.id for role in ctx.author.roles]
    if SETUP_ROLE_ID not in role_ids and not ctx.author.guild_permissions.administrator:
        return await ctx.send("You do not have permission to use this command.")

    user_data = DB.get(ctx.author.id)
    if not user_data:
        return await ctx.send("You need to use $setup first to register your username and server link.")

    try:
        await ctx.message.delete()
    except:
        pass

    if "," not in payment_and_item:
        return await ctx.send("Use the format: `$offer @user payment, item>`")

    payment, item = map(str.strip, payment_and_item.split(",", 1))
    if not payment or not item:
        return await ctx.send("Both payment and item are required.")

    embed = discord.Embed(
        title="💰 Trade Offer",
        description=f"{ctx.author.mention} ({user_data['username']}) is offering to buy **{item}** for **{payment}**.",
        color=MAIN_COLOR
    )
    embed.add_field(name="Private Server Link", value=user_data['server_link'], inline=False)
    embed.add_field(name="Instructions", value="Reply with `$accept` to accept this offer or `$decline` to decline.", inline=False)
    embed.set_footer(text="Make sure to follow the rules")
    await ctx.send(embed=embed)



@bot.command()
@allowed_server()
async def complete(ctx, member: discord.Member, *, payment_and_item: str):
    try:
        await ctx.message.delete()
    except:
        pass

    if "," not in payment_and_item:
        return await ctx.send("Use the format: `$complete @user payment, item>`")

    payment, item = map(str.strip, payment_and_item.split(",", 1))
    if not payment or not item:
        return await ctx.send("Both payment and item are required.")

    # safe avatar handling
    try:
        avatar = ctx.author.display_avatar.url
    except AttributeError:
        avatar = str(ctx.author.avatar) if ctx.author.avatar else None

    # give "Customers" role to buyer and staff
    role = discord.utils.get(ctx.guild.roles, name="Customers")
    if role:
        await member.add_roles(role)
        await ctx.author.add_roles(role)

    # initial processing embed
    start_embed = discord.Embed(
        title="🟢 Trading Bot Signing In...",
        description=f"Preparing transaction for {member.mention}...",
        color=MAIN_COLOR
    )
    msg = await ctx.send(embed=start_embed)

    # fake processing animation
    for dots in [".", "..", "..."]:
        await asyncio.sleep(0.8)
        await msg.edit(embed=discord.Embed(
            title=f"💰 Processing payout{dots}",
            description=f"Verifying amount: **{payment}**\nChecking item: **{item}**",
            color=MAIN_COLOR
        ))

    # instructions embed
    instructions = discord.Embed(
        title="📦 Transaction Logged",
        description=(
            f"**Transaction prepared.**\n\n"
            f"**Payment:** {payment}\n"
            f"**Item:** {item}\n"
            f"**Receiver:** {member.mention}\n\n"
            f"The payment will be delivered in **5–10 minutes** via **pls donate** or **gamepass link.**\n\n"
            f"**Important:** The user must **vouch before receiving**.\n\n"
            f"Copy and paste this vouch into **#〃✅・vouches**:\n"
            f"```vouch {ctx.author.mention} paid {payment} for {item}```"
        ),
        color=MAIN_COLOR
    )

    # safe footer
    footer_kwargs = {"text": f"Logged by {ctx.author}"}
    if avatar and avatar.startswith("http"):
        footer_kwargs["icon_url"] = avatar
    instructions.set_footer(**footer_kwargs)
    instructions.timestamp = datetime.utcnow()

    # send instructions
    await ctx.send(embed=instructions)

    # optional: send to waitlist/log channel
    waitlist = bot.get_channel(WAITLIST_CHANNEL_ID)
    if waitlist:
        await waitlist.send(embed=instructions)

    # final message telling staff next step
    await ctx.send(f"{ctx.author.mention}, now wait for the user to vouch. After that, run `$pay @{member.display_name}>` to complete the transaction.")

# ---------------- CONFIG ----------------
ICON_URL = "https://images-ext-1.discordapp.net/external/JeJ5jkOf50ohxX5IdtJOy5_WaADNWhGUdBQog8qTcVA/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1278435741973745735/810c2f3c6cb30d501c298ecbd06add0d.png?format=webp&quality=lossless&width=176&height=176"
STOCK_LINK = "https://discord.com/channels/1278435741973745735/1434971767197143190"
PAYMENT_LINK = "https://discord.com/channels/1278435741973745735/1280138248433303632"
TRANSACTION_CHANNEL_ID = 1434482848299094036
CLAIM_USER_ID = 1267041599775571979

# ---------------- STORAGE ----------------
transactions = {}
running_channels = set()  # prevent duplicate embeds


# ---------------- START SYSTEM ----------------
async def start_trading_system(channel: discord.TextChannel):
    if channel.id in running_channels:
        return
    running_channels.add(channel.id)

    # delete all messages in the channel first
    try:
        await channel.purge(limit=None)
    except:
        pass


    # first embed: welcome
    welcome_embed = discord.Embed(
        title="Kimchi's Trading System",
        description=(
            "Welcome to our automated trading system.\n"
            "All messages here are securely encrypted and logged.\n"
            "Transactions are tracked to avoid confusion or disputes.\n"
            "Follow the instructions below to safely buy or sell.\n"
            "Our system ensures fairness and transparency in all trades."
        ),
        color=MAIN_COLOR
    )

    welcome_embed.set_thumbnail(url="https://i.pinimg.com/originals/84/8c/34/848c342a56e7854dec45b9349c21dfe5.gif")
    welcome_embed.set_footer(text="Kimchi Trading | Automated System")



    await asyncio.sleep(1.5)
    await channel.send(embed=welcome_embed)

    # second embed: trading options
    await asyncio.sleep(2.5)
    options_embed = discord.Embed(
        title="Trading Options",
        description=(
            "Select one of the options below to proceed with your transaction:\n"
            "- Buy items securely from our stock.\n"
            "- Sell your items safely for guaranteed rates.\n"
            "Click the buttons below to start."
        ),
        color=MAIN_COLOR
    )
    options_embed.set_thumbnail(url=ICON_URL)
    options_embed.set_footer(text="Kimchi Trading | Secure & Encrypted")

    view = View()
    view.add_item(Button(label="Buy", style=discord.ButtonStyle.green, custom_id="buy"))
    view.add_item(Button(label="Sell", style=discord.ButtonStyle.red, custom_id="sell"))

    await channel.send(embed=options_embed, view=view)


# ---------------- AUTO START ON CHANNEL CREATE ----------------
@bot.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.TextChannel):
        await start_trading_system(channel)


# ---------------- MODAL ----------------
class TradeModal(Modal):
    def __init__(self, action):
        super().__init__(title=f"{action} Request")
        self.action = action
        self.username_input = TextInput(label="Enter your username", style=discord.TextStyle.short)
        self.item_input = TextInput(label="Item Name", placeholder="Enter item name", style=discord.TextStyle.short)
        self.ms_input = TextInput(label="Amount (m/s)", placeholder="Enter amount as number", style=discord.TextStyle.short)
        self.add_item(self.username_input)
        self.add_item(self.item_input)
        self.add_item(self.ms_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value
        item_name = self.item_input.value
        try:
            ms_amount = int(self.ms_input.value)
            if ms_amount <= 0:
                raise ValueError
        except:
            return await interaction.response.send_message("Invalid m/s amount.", ephemeral=True)

        transaction_id = generate_transaction_id()
        transactions[transaction_id] = {
            "user": interaction.user.mention,
            "username": username,
            "item": item_name,
            "ms": ms_amount,
            "action": self.action,
            "status": "Pending"
        }

        # price calculation
        if self.action == "Buy":
            usd_anchors = [(1,0.05),(10,0.25),(50,1.00),(100,2.00),(150,4.00)]
            def usd_price(ms: int) -> float:
                for m,u in usd_anchors:
                    if ms == m:
                        return float(u)
                for i in range(len(usd_anchors)-1):
                    m1,u1 = usd_anchors[i]
                    m2,u2 = usd_anchors[i+1]
                    if m1 < ms < m2:
                        slope = (u2-u1)/(m2-m1)
                        return float(u1 + slope*(ms-m1))
                last_m,last_u = usd_anchors[-1]
                prev_m,prev_u = usd_anchors[-2]
                slope = (last_u-prev_u)/(last_m-prev_m)
                return float(last_u + slope*(ms-last_m))
            base_usd = usd_price(ms_amount)
            discounted_usd = base_usd * 1.40
            original_usd = discounted_usd * 1.25
            price_text = f"{ms_amount} m/s ≈ ${discounted_usd:,.2f} (original: ${original_usd:,.2f})"
        else:
            anchors = [(1,50),(10,125),(50,290),(100,600),(150,900)]
            def brainrot_price(ms: int) -> int:
                if ms < 1: return 0
                for i in range(len(anchors)-1):
                    m1,r1 = anchors[i]
                    m2,r2 = anchors[i+1]
                    if m1 <= ms <= m2:
                        return round(r1 + (r2-r1)/(m2-m1)*(ms-m1))
                last_m,last_r = anchors[-1]
                prev_m,prev_r = anchors[-2]
                increment = (last_r-prev_r)/(last_m-prev_m)
                return round(last_r + (ms-last_m)*increment)
            rbx = brainrot_price(ms_amount)
            price_text = f"We offer to buy your brainrot for {rbx} Robux"

        # embed for transaction
        embed = discord.Embed(
            title=f"{self.action} Offer: {item_name}",
            description=price_text + f"\n\nStock: {STOCK_LINK}\nOur vouches: {PAYMENT_LINK}",
            color=MAIN_COLOR
        )
        profile_link = f"https://www.roblox.com/search/users?keyword={username}"
        embed.add_field(name="Username", value=f"[{username}]({profile_link})", inline=True)
        embed.add_field(name="Transaction ID", value=transaction_id)
        embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/JeJ5jkOf50ohxX5IdtJOy5_WaADNWhGUdBQog8qTcVA/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1278435741973745735/810c2f3c6cb30d501c298ecbd06add0d.png?format=webp&quality=lossless&width=279&height=279")

        view = View()
        view.add_item(Button(label="Accept", style=discord.ButtonStyle.green, custom_id=f"accept_{transaction_id}"))
        view.add_item(Button(label="Decline", style=discord.ButtonStyle.red, custom_id=f"decline_{transaction_id}"))

        await interaction.response.send_message(embed=embed, view=view)


# ---------------- INTERACTIONS ----------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    custom_id = interaction.data.get("custom_id")
    if not custom_id:
        return

    if custom_id in ["buy","sell"]:
        action = "Buy" if custom_id=="buy" else "Sell"
        await interaction.response.send_modal(TradeModal(action))
        return

    if custom_id.startswith(("accept_","decline_")):
        tid = custom_id.split("_")[1]
        if tid not in transactions:
            return await interaction.response.send_message("Transaction not found.", ephemeral=True)

        transaction = transactions[tid]
        channel = interaction.channel
        if custom_id.startswith("accept_"):
            transaction["status"] = "Accepted"
            try:
                await channel.edit(name=f"✅-{tid}")
            except:
                pass
            message_text = "Offer accepted. Wait until a staff responds to complete the transaction."
        else:
            transaction["status"] = "Declined"
            try:
                await channel.edit(name=f"❌-{tid}")
            except:
                pass
            message_text = "DM staff to tell us why you declined the offer."

        transaction_channel = bot.get_channel(TRANSACTION_CHANNEL_ID)
        if transaction_channel:
            embed_log = discord.Embed(
                title=f"Transaction {tid} - {transaction['status']}",
                description=f"Item: {transaction['item']}\nAmount: {transaction['ms']}\nAction: {transaction['action']}\nUser: {transaction['user']}\nUsername: {transaction['username']}",
                color=MAIN_COLOR
            )
            await transaction_channel.send(embed=embed_log)

        await interaction.response.send_message(message_text, ephemeral=True)


# ---------------- TRANSACTION HISTORY ----------------
@bot.command()
async def transaction(ctx, tid: str):
    if tid not in transactions:
        return await ctx.send("Transaction ID not found.")
    t = transactions[tid]
    embed = discord.Embed(
        title=f"Transaction {tid} Details",
        description=f"Status: {t['status']}\nAction: {t['action']}\nItem: {t['item']}\nAmount: {t['ms']}\nUsername: {t['username']}\nUser: {t['user']}",
        color=MAIN_COLOR
    )
    await ctx.send(embed=embed)




def random_robux():
    return random.randint(50, 5000)


def robux_to_usd(robux):
    return round((robux / 1000) * 4, 2)


def random_user_id():
    return random.randint(100000000, 999999999)


def random_transaction_id():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))


@bot.command()
async def rs(ctx):
    try:
        await ctx.message.delete()

        robux_amount = random_robux()
        usd_value = robux_to_usd(robux_amount)
        sender = random_user_id()
        receiver = random_user_id()
        transaction_id = random_transaction_id()

        embed = discord.Embed(
            title="Roblox Deal Completed",
            color=MAIN_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=IMAGE_URL)
        embed.add_field(
            name="💰 Amount",
            value=f"`{robux_amount}` Rbx (${usd_value} USD) ",
            inline=False
        )
        embed.add_field(
            name="👤 Sender",
            value=f"`{sender}`",
            inline=True
        )
        embed.add_field(
            name="👥 Receiver",
            value=f"`{receiver}`",
            inline=True
        )
        embed.add_field(
            name="🆔 Transaction ID",
            value=f"`{transaction_id}`",
            inline=False
        )
        embed.set_footer(text="Roblox Transaction Logger")
        embed.set_author(name="System")

        await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error running rs command: {e}")


@bot.command()
@allowed_server()
async def rates(ctx):
    embed = discord.Embed(title="Brainrot Rates (15% Off)", color=MAIN_COLOR)
    for ms, price in anchors:
        embed.add_field(name=f"{ms}m/s", value=f"{price} Robux", inline=True)
    embed.set_footer(text="Juno Brainrot Value System")
    await ctx.send(embed=embed)

# --------------------
# Username / Waitlist Commands
# --------------------
user_roblox_data = {}  # stores {discord_id: {"username": str}}

@bot.command()
@allowed_server()
async def username(ctx, username: str = None):
    if not username:
        await ctx.send("Usage: `$username roblox_username`")
        return

    user_roblox_data[ctx.author.id] = {"username": username}

    embed = discord.Embed(title="✅ Roblox Username Saved", color=MAIN_COLOR)
    embed.add_field(name="Discord User", value=ctx.author.mention, inline=False)
    embed.add_field(name="Roblox Username", value=username, inline=True)
    embed.add_field(name="Profile Link", value=f"https://www.roblox.com/users/profile?username={username}", inline=False)
    embed.set_footer(text=f"Saved by {ctx.author}", icon_url=getattr(ctx.author.avatar, 'url', None))

    await ctx.send(embed=embed)


@bot.command()
async def d(ctx):
    await ctx.channel.delete()

import random
import string

def generate_transaction_id(length=10):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))





TICKET_CATEGORY_ID = 1432000945159405608

@bot.command()
async def create(ctx, user: discord.Member):
    category = discord.utils.get(ctx.guild.categories, id=TICKET_CATEGORY_ID)
    if not category:
        return await ctx.send("Ticket category not found.")

    # generate random number 250-1000
    rand_num = random.randint(250, 1000)
    channel_name = f"ticket-{rand_num}"

    # create channel
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),  # block everyone
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),  # allow target user
        ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)  # allow bot
    }

    channel = await ctx.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

    # send confirmation embed inside ticket
    embed = discord.Embed(
        title="Ticket Created",
        description=f"{user.mention}, your ticket has been created: {channel.mention}",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Kimchi Ticket System")
    await channel.send(embed=embed)

    # notify in original channel
    await ctx.send(f"Ticket created for {user.mention}: {channel.mention}")


# channel id to send to
CHANNEL_IDS = [1436833619892109322, 1436708163993866311]

# main embed color
# image url
IMAGE_URL = "https://images-ext-1.discordapp.net/external/JeJ5jkOf50ohxX5IdtJOy5_WaADNWhGUdBQog8qTcVA/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1278435741973745735/810c2f3c6cb30d501c298ecbd06add0d.png?format=webp&quality=lossless&width=279&height=279"

@bot.command()
async def send(ctx):
    tickets_category = bot.get_channel(1436834411890081842)  # tickets category id
    if not tickets_category or not isinstance(tickets_category, discord.CategoryChannel):
        return await ctx.send("Tickets category not found.")

    embed = discord.Embed(
        title="Start a Deal",
        description=(
            "Click the button below to start a deal to sell/buy brainrots.\n\n"
            "**Important:**\n"
            "- This is not a MM\n"
            "- All vouches are listed here: https://discord.com/channels/1436832738723365004/1436833782648017007\n"
            "- Starting a deal ≠ Ending a deal\n"
            "- Please follow all discord TOS\n"
        ),
        color=MAIN_COLOR
    )

    embed.set_thumbnail(url=IMAGE_URL)  # set thumbnail

    view = discord.ui.View()

    async def start_deal_callback(interaction: discord.Interaction):
        # create private channel inside tickets category
        channel_name = f"deal-{interaction.user.name}"
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        deal_channel = await tickets_category.create_text_channel(channel_name, overwrites=overwrites)
        await interaction.response.send_message(f"Your deal channel has been created: {deal_channel.mention}", ephemeral=True)

    button = discord.ui.Button(label="Start Deal", style=discord.ButtonStyle.blurple)  # blue button
    button.callback = start_deal_callback
    view.add_item(button)


    await ctx.send(embed=embed, view=view)

def random_robux_amount():
    # random robux between 50 and 5000 for example
    return random.randint(50, 5000)

def usd_value(robux):
    # 1000 robux = 4 USD
    return round((robux / 1000) * 4, 2)

def random_user_id():
    return ''.join(random.choices(string.digits, k=18))

def random_transaction_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

async def send_random_embed():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found")
        return

    while True:
        robux = random_robux_amount()
        usd = usd_value(robux)
        embed = discord.Embed(title="Roblox Deal Completed", color=MAIN_COLOR)
        embed.set_thumbnail(url=IMAGE_URL)
        embed.add_field(name="Amount:", value=f"`{robux} Robux` (${usd})", inline=False)
        embed.add_field(name="Sender:", value=random_user_id(), inline=True)
        embed.add_field(name="Receiver:", value=random_user_id(), inline=True)
        embed.add_field(name="Transaction id:", value=random_transaction_id(), inline=False)

        await channel.send(embed=embed)

        wait_time = random.randint(60, 300)  # 1 to 5 minutes
        await asyncio.sleep(wait_time)


CHANNEL_ID = 1436708163993866311  # target channel

def random_robux():
    return random.randint(50, 5000)

def robux_to_usd(robux):
    return round((robux / 1000) * 4, 2)

def random_user_id():
    return random.randint(100000000, 999999999)

def random_transaction_id():
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))

@bot.event
async def on_ready():
    print(f"logged in as {bot.user}")
    send_fake_embed.start()

@tasks.loop(seconds=60)
async def send_fake_embed():
    wait_time = random.randint(60, 300)  # 1-5 minutes
    await asyncio.sleep(wait_time)

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    robux_amount = random_robux()
    usd_value = robux_to_usd(robux_amount)
    sender = random_user_id()
    receiver = random_user_id()
    transaction_id = random_transaction_id()

    embed = discord.Embed(
        title=" Roblox Deal Completed ",
        color=MAIN_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=IMAGE_URL)
    embed.add_field(
        name="💰 Amount",
        value=f"`{robux_amount}` Rbx (${usd_value} USD)",
        inline=False
    )
    embed.add_field(
        name="👤 Sender",
        value=f"`{sender}`",
        inline=True
    )
    embed.add_field(
        name="👥 Receiver",
        value=f"`{receiver}`",
        inline=True
    )
    embed.add_field(
        name="🆔 Transaction ID",
        value=f"`{transaction_id}`",
        inline=False
    )
    embed.set_footer(text="Roblox Transaction Logger")
    embed.set_author(name="System")

    await channel.send(embed=embed)




PAYMENTS_CHANNEL_ID = 1434482848299094036

@bot.command()
@allowed_server()
async def pay(ctx, member: discord.Member):
    """Fake pay flow. Usage: $pay @user"""
    try:
        await ctx.message.delete()
    except:
        pass

    # check if user has linked roblox username
    roblox_info = user_roblox_data.get(member.id)
    if not roblox_info or not roblox_info.get("username"):
        return await ctx.send(
            f"{ctx.author.mention} that user has no linked Roblox username. "
            f"Use `$us @user <roblox_username>` to link one."
        )

    username = roblox_info["username"]

    # trader bot starting embed
    embed = discord.Embed(
        title="🤖 Trader Bot Signing In...",
        description=f"Preparing payout for {member.mention}\nTarget Roblox account: **{username}**",
        color=MAIN_COLOR
    )
    msg = await ctx.send(embed=embed)

    # fake progress
    steps = [
        ("🔍 Locating account", 3.0),
        ("🔐 Verifying payment", 2.0),
        ("💸 Initiating transfer", 4.0),
        ("⏳ Finalizing. almost done", 15.0)
    ]
    for text, wait in steps:
        await asyncio.sleep(wait)
        progress = discord.Embed(
            title="🤖 Trader Bot Signing In...",
            description=f"{text}\nTarget Roblox: **{username}**\nReceiver: {member.mention}",
            color=MAIN_COLOR
        )
        await msg.edit(embed=progress)

    # success embed
    success = discord.Embed(
        title="✅ Payment Sent",
        description=(
            f"Payment successfully recorded for **{username}** ({member.mention}).\n"
            f"Payout status: **pending**\n"
            f"Expect delivery in **5–6 days** (pending Roblox processing).\n"
            f"If payment was through gamepass or in-game gift, pending Robux must clear first."
        ),
        color=MAIN_COLOR
    )

    success.add_field(name="Receiver", value=member.mention, inline=True)
    success.add_field(name="Roblox Username", value=username, inline=True)

    # safe footer + timestamp
    footer_text = f"Processed by {ctx.author}"
    footer_icon = None
    try:
        if hasattr(ctx.author, "display_avatar"):
            icon_url = ctx.author.display_avatar.url
            if icon_url and icon_url.startswith("http"):
                footer_icon = icon_url
    except Exception:
        pass

    if footer_icon:
        success.set_footer(text=footer_text, icon_url=footer_icon)
    else:
        success.set_footer(text=footer_text)


    # edit progress msg into success
    await msg.edit(embed=success)

    # send log to payment channel if exists
    try:
        log_channel = bot.get_channel(PAYMENTS_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=success)
    except Exception:
        pass

    # short confirmation
    await ctx.send(f"{ctx.author.mention} payout recorded. Wait for pending Robux to clear (5–6 days).")


# assume data.json exists and has structure: {"staff": {}, "log_channel": None}

class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # set log channel
    @app_commands.command(name="setinvitelog", description="Set the log channel for invites")
    @commands.has_permissions(administrator=True)
    async def setinvitelog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        with open("data.json", "r") as f:
            data = json.load(f)
        data["log_channel"] = channel.id
        with open("data.json", "w") as f:
            json.dump(data, f, indent=4)
        await interaction.response.send_message(f"✅ invite log channel set to {channel.mention}", ephemeral=True)

    # add staff
    @app_commands.command(name="setstaff", description="Add a staff member")
    @commands.has_permissions(administrator=True)
    async def setstaff(self, interaction: discord.Interaction, member: discord.Member):
        with open("data.json", "r") as f:
            data = json.load(f)
        if str(member.id) not in data["staff"]:
            data["staff"][str(member.id)] = {"name": member.name, "invites": 0, "history": []}
        with open("data.json", "w") as f:
            json.dump(data, f, indent=4)
        await interaction.response.send_message(f"✅ {member.mention} added as staff", ephemeral=True)

    # remove staff
    @app_commands.command(name="removestaff", description="Remove a staff member")
    @commands.has_permissions(administrator=True)
    async def removestaff(self, interaction: discord.Interaction, member: discord.Member):
        with open("data.json", "r") as f:
            data = json.load(f)
        if str(member.id) in data["staff"]:
            del data["staff"][str(member.id)]
            with open("data.json", "w") as f:
                json.dump(data, f, indent=4)
            await interaction.response.send_message(f"❌ removed {member.mention} from staff", ephemeral=True)
        else:
            await interaction.response.send_message(f"{member.mention} not found in staff list", ephemeral=True)

    # show all staff
    @app_commands.command(name="stafflist", description="Show all staff members")
    async def stafflist(self, interaction: discord.Interaction):
        with open("data.json", "r") as f:
            data = json.load(f)
        staff = data["staff"]
        if not staff:
            await interaction.response.send_message("no staff found", ephemeral=True)
            return
        msg = "**staff list:**\n"
        for s in staff.values():
            msg += f"- {s['name']} ({s['invites']} invites)\n"
        await interaction.response.send_message(msg, ephemeral=True)

    # reset staff invites
    @app_commands.command(name="resetinvites", description="Reset a staff member's invite data")
    @commands.has_permissions(administrator=True)
    async def resetinvites(self, interaction: discord.Interaction, member: discord.Member):
        with open("data.json", "r") as f:
            data = json.load(f)
        if str(member.id) in data["staff"]:
            data["staff"][str(member.id)]["invites"] = 0
            data["staff"][str(member.id)]["history"] = []
            with open("data.json", "w") as f:
                json.dump(data, f, indent=4)
            await interaction.response.send_message(f"🔁 reset {member.mention}'s invites", ephemeral=True)
        else:
            await interaction.response.send_message("not in staff list", ephemeral=True)

    # view invites
    @app_commands.command(name="invites", description="Check how many invites a staff has")
    async def invites(self, interaction: discord.Interaction, member: discord.Member):
        with open("data.json", "r") as f:
            data = json.load(f)
        if str(member.id) in data["staff"]:
            invites = data["staff"][str(member.id)]["invites"]
            await interaction.response.send_message(f"{member.mention} has {invites} invites", ephemeral=True)
        else:
            await interaction.response.send_message("not a staff member", ephemeral=True)

    # leaderboard
    @app_commands.command(name="leaderboard", description="Show top inviters")
    async def leaderboard(self, interaction: discord.Interaction):
        with open("data.json", "r") as f:
            data = json.load(f)
        staff = data["staff"]
        if not staff:
            await interaction.response.send_message("no data", ephemeral=True)
            return
        sorted_staff = sorted(staff.items(), key=lambda x: x[1]["invites"], reverse=True)
        msg = "**leaderboard:**\n"
        for i, (sid, sdata) in enumerate(sorted_staff[:10], start=1):
            msg += f"{i}. {sdata['name']} - {sdata['invites']} invites\n"
        await interaction.response.send_message(msg, ephemeral=True)

    # staff history
    @app_commands.command(name="staffhistory", description="Show invite history for a staff member")
    async def staffhistory(self, interaction: discord.Interaction, member: discord.Member):
        with open("data.json", "r") as f:
            data = json.load(f)
        if str(member.id) not in data["staff"]:
            await interaction.response.send_message("not a staff member", ephemeral=True)
            return
        history = data["staff"][str(member.id)]["history"]
        if not history:
            await interaction.response.send_message("no invite history", ephemeral=True)
            return
        msg = f"**invite history for {member.name}:**\n"
        for entry in history[-10:]:  # last 10
            msg += f"- {entry['user']} joined at {entry['joined_at']}\n"
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Staff(bot))





@bot.command()
async def explain(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="💰 Trading Tax",
        description=(
            "A 30% tax applies on every Robux purchase made in USD.\n"
            "This tax comes from the seller who handles the currency conversion.\n"
            "Each separate payment requires a new conversion, which repeats the 30% fee.\n"
            "To prevent multiple taxes, all items or brainrots for sale should be listed together before payment.\n"
            "Paying for everything at once allows one conversion instead of several, keeping prices higher for sellers.\n"
            "This process ensures fair payouts and avoids unnecessary fee losses during multiple small transactions.\n\n"
            "**Trading policy explanation.**"
        ),
        color=discord.Color.from_rgb(255, 255, 255)
    )



    embed.set_footer(text="Trading policy explanation")
    await ctx.send(embed=embed)


@bot.command()
async def delete(ctx):
    ARCHIVE_CHANNEL_ID = 1436836546912325763  # channel to send transcripts
    channel = ctx.channel
    messages = []

    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    if not messages:
        await ctx.send("No messages to save.")
        return

    creator = messages[0].author  # assume first message author is creator
    closer = ctx.author  # user who ran $delete

    # create HTML transcript
    html_lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Discord Ticket Transcript</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;background:#2c2f33;color:#fff;padding:20px;}",
        ".message{margin:10px 0;padding:5px;border-bottom:1px solid #444;}",
        ".author{font-weight:bold;color:#00b0f4;}",
        ".timestamp{color:#aaa;font-size:0.9em;margin-left:5px;}",
        ".content{margin-left:40px;white-space:pre-wrap;}",
        ".avatar{width:32px;height:32px;border-radius:50%;vertical-align:middle;margin-right:5px;}",
        "a{color:#00b0f4;text-decoration:none;}",
        "</style></head><body>",
        f"<h2>Ticket Closed</h2>",
        f"<p><b>Closed by:</b> {html.escape(str(closer))} (ID: {closer.id})</p>",
        f"<p><b>Ticket created by:</b> {html.escape(str(creator))} (ID: {creator.id})</p>",
        f"<p><b>Channel:</b> #{html.escape(channel.name)}</p>",
        f"<p><b>Deleted at:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>",
        "<hr>"
    ]

    for msg in messages:
        author_name = html.escape(str(msg.author))
        author_id = msg.author.id
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        content = html.escape(msg.content)
        avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else ""

        html_lines.append(
            f"<div class='message'>"
            f"<img src='{avatar_url}' class='avatar'>"
            f"<span class='author'>{author_name} (ID: {author_id})</span>"
            f"<span class='timestamp'>[{timestamp}]</span>"
            f"<div class='content'>{content}</div>"
        )

        for attach in msg.attachments:
            html_lines.append(f"<div class='content'>Attachment: <a href='{attach.url}' target='_blank'>{attach.filename}</a></div>")

        html_lines.append("</div>")

    html_lines.append("</body></html>")
    html_content = "\n".join(html_lines)

    # save to temporary HTML file
    filename = f"transcript-{channel.name}-{channel.id}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    # send as attachment to archive channel
    archive_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if archive_channel:
        await archive_channel.send(file=discord.File(filename, filename="transcript.html"))

    # delete local file
    import os
    os.remove(filename)

    # delete the ticket channel
    await channel.delete()


@bot.command()
@allowed_server()
async def us(ctx, member: discord.Member = None, username: str = None):
    if not member or not username:
        await ctx.send("Usage: `<us @user roblox_username`")
        return

    user_roblox_data[member.id] = {"username": username}
    embed = discord.Embed(title="Roblox Username Linked", color=MAIN_COLOR)
    embed.add_field(name="Discord User", value=member.mention, inline=False)
    embed.add_field(name="Roblox Username", value=username, inline=True)
    embed.add_field(name="Profile Link", value=f"https://www.roblox.com/users/profile?username={username}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@allowed_server()
async def bl(ctx, member: discord.Member = None, *, item: str = None):
    if not member or not item:
        await ctx.send("Usage: `<bl @user item`")
        return

    roblox_info = user_roblox_data.get(member.id)
    if not roblox_info:
        await ctx.send("No Roblox info saved for this user. Use `<us @user roblox_username` first.")
        return

    log_channel = bot.get_channel(1434482848299094036)
    if not log_channel:
        await ctx.send("Log channel not found.")
        return

    embed = discord.Embed(title="⚠️ Scammed", color=MAIN_COLOR)
    embed.add_field(name="Scammed", value=member.mention, inline=False)
    embed.add_field(name="Item", value=item, inline=False)
    embed.add_field(name="Discord Info", value=f"User ID: `{member.id}`\nMention: {member.mention}", inline=False)
    embed.add_field(name="Roblox Info", value=f"Username: `{roblox_info['username']}`", inline=False)
    embed.add_field(name="Roblox Profile", value=f"https://www.roblox.com/users/profile?username={roblox_info['username']}", inline=False)

    await log_channel.send(embed=embed)

    # try to mute the member fully
    try:
        # try to find or create a mute role
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False, speak=False))
            # apply permission overwrite to all channels
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, add_reactions=False, speak=False, connect=False, create_public_threads=False, create_private_threads=False)

        # assign the mute role
        await member.add_roles(mute_role, reason=f"Scamming: {item}")

        # extra safeguard: deny permissions for each channel directly
        for channel in ctx.guild.channels:
            await channel.set_permissions(member, send_messages=False, add_reactions=False, speak=False, connect=False, create_public_threads=False, create_private_threads=False, send_messages_in_threads=False)

    except Exception as e:
        await ctx.send(f"Failed to fully mute {member.mention}: `{e}`")

    # try deleting the command channel
    try:
        await ctx.channel.delete()
    except:
        pass



@bot.command()
async def pls(ctx, subcommand: str = None, roblox_user: str = None):
    if subcommand != "donate" or not roblox_user:
        await ctx.send("Usage: <pls donate username>")
        return

    order = latest_orders.get(ctx.author.id)
    if not order:
        await ctx.send("No recent order found. Use <complete> first.")
        return

    embed = discord.Embed(title="Waitlist Order", color=MAIN_COLOR)
    embed.add_field(name="Roblox User", value=roblox_user, inline=False)
    embed.add_field(name="Item", value=order["item"], inline=False)
    embed.add_field(name="Robux", value=str(order["robux"]), inline=False)
    embed.add_field(name="Status", value="Ready for PLS Donate", inline=False)

    channel = bot.get_channel(WAITLIST_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

    await ctx.send(f"PLS Donate embed sent for {roblox_user}")
    latest_orders.pop(ctx.author.id, None)

# --------------------
# Trade Commands
# --------------------
# universal roblox trade system

TRADE_RULES = """
- No time wasting.
- Join me immediately when instructed.
- Follow instructions carefully.
- Only text communication unless specified.
"""

@bot.command()
async def offer(ctx, member: discord.Member, *, payment_and_item: str):
    try:
        await ctx.message.delete()
    except:
        pass

    if "," not in payment_and_item:
        return await ctx.send("Use the format: `<offer @user payment, item>`")

    payment, item = map(str.strip, payment_and_item.split(",", 1))
    if not payment or not item:
        return await ctx.send("Both payment and item are required.")

    embed = discord.Embed(
        title="💰 Trade Offer",
        description=f"{ctx.author.mention} is offering to buy **{item}** for **{payment}**.",
        color=MAIN_COLOR
    )
    embed.add_field(
        name="Instructions",
        value=f"Reply with `$accept` to accept or `$decline` to decline.\n\nRules:\n{TRADE_RULES}",
        inline=False
    )
    embed.set_footer(text="Follow the rules for a smooth trade")
    await ctx.send(embed=embed)

@bot.command()
async def accept(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    accepted_embed = discord.Embed(
        title="✅ Offer Accepted",
        description="Offer accepted. Follow the rules below carefully.",
        color=MAIN_COLOR
    )
    accepted_embed.add_field(
        name="Rules",
        value=TRADE_RULES,
        inline=False
    )
    accepted_embed.add_field(
        name="👤 Add This User",
        value=f"**Username:** Helo26253\n**Profile:** https://www.roblox.com/users/1150511735/profile",
        inline=False
    )
    await ctx.send(embed=accepted_embed)

@bot.command()
async def decline(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    embed = discord.Embed(
        title="❌ Offer Declined",
        description=f"{ctx.author.mention} has declined the offer.",
        color=MAIN_COLOR
    )
    await ctx.send(embed=embed)

@bot.command()
async def confirm(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="✅ Confirmed",
        description="You can now join the private server. Make sure to follow the rules above.",
        color=MAIN_COLOR
    )
    embed.add_field(
        name="🔗 Private Server Link",
        value="[Join Server](https://www.roblox.com/share?code=f6c7fa32ecf3754eab7bd137935ef71a&type=Server)",
        inline=False
    )
    embed.add_field(
        name="Rules",
        value=TRADE_RULES,
        inline=False
    )
    await ctx.send(embed=embed)


# ------------------ clear command ------------------
@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 100):
    """Deletes messages in a channel. Default 100."""
    try:
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"✅ Cleared {len(deleted)} messages.")
        await msg.delete(delay=5)
    except Exception as e:
        await ctx.send(f"Failed to clear messages: {e}")

KB_ROLE_ID = 1434634819136127046  # make sure this is int

@bot.command()
async def joinkb(ctx):
    role = ctx.guild.get_role(KB_ROLE_ID)
    if not role:
        return await ctx.send("Role not found.")

    if role in ctx.author.roles:
        return await ctx.send("You already have the KB role!")

    await ctx.author.add_roles(role)

    embed = discord.Embed(
        title="Welcome to the KB Team",
        description=f"{ctx.author.mention}, use `$howto` to see what to do next!",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)

    await ctx.send(embed=embed)


# --------------------
# Misc Utility Commands
# --------------------
@bot.command()
@allowed_server()
async def calc(ctx, *, expr: str):
    try:
        # WARNING: eval is dangerous. This mirrors original behavior.
        result = eval(expr)
        embed = discord.Embed(title="🧮 Calculator", description=f"`{expr}` = **{result}**", color=MAIN_COLOR)
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("Invalid expression.")

@bot.command()
@allowed_server()
async def ping(ctx):
    embed = discord.Embed(title="🏓 Pong!", description=f"{round(bot.latency*1000)}ms", color=MAIN_COLOR)
    await ctx.send(embed=embed)

@bot.command()
@allowed_server()
async def info(ctx):
    embed = discord.Embed(title="Bot Info", color=MAIN_COLOR)
    embed.add_field(name="Prefix", value="<", inline=True)
    embed.add_field(name="Creator", value="Juno Shop", inline=True)
    embed.add_field(name="Guilds", value=f"{len(bot.guilds)}", inline=True)
    await ctx.send(embed=embed)

@bot.command()
@allowed_server()
async def today(ctx):
    embed = discord.Embed(title="📅 Current Time", description=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), color=MAIN_COLOR)
    await ctx.send(embed=embed)

@bot.command()
async def s(ctx, *, message: str):
    try:
        await ctx.message.delete()
    except:
        pass
    embed = discord.Embed(title="System", description=message, color=MAIN_COLOR)
    await ctx.send(embed=embed)

@bot.command()
async def ss(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    embed = discord.Embed(title="Screenshot", description="Please show a **clear screenshot** of the items you want to sell.", color=MAIN_COLOR)
    await ctx.send(embed=embed)

# --------------------
# Order System
# --------------------
@bot.command()
async def received(ctx, member: discord.Member, item: str, robux: int, *, payout: str = "pls donate"):
    order_id = random.randint(1000,9999)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    pending_orders[order_id] = {"staff": ctx.author, "user": member, "item": item, "robux": robux, "payout": payout, "time": timestamp}
    log_channel = bot.get_channel(WAITLIST_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=f"📝 New Order | ID #{order_id}", color=MAIN_COLOR,
                              description=f"**Staff:** {ctx.author.mention}\n**User:** {member.mention}\n**Item:** {item}\n**Robux:** {robux}\n**Payout:** {payout}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/icons/1278435741973745735/e1811230cde8b1f563da7906f296b6ea.png?size=160&quality=lossless")
        embed.set_footer(text=f"Received at: {timestamp} | Payout ETA: 1-12 hours")
        await log_channel.send(embed=embed)
    await ctx.send(f"✅ Order logged with ID: {order_id}")

@bot.command()
async def paid(ctx, order_id: int):
    if order_id not in pending_orders:
        return await ctx.send(f"❌ Order ID {order_id} not found.")
    order = pending_orders.pop(order_id)
    log_channel = bot.get_channel(WAITLIST_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=f"✅ Payout Confirmed | Order #{order_id}", color=MAIN_COLOR,
                              description=f"**Staff:** {order['staff'].mention}\n**User:** {order['user'].mention}\n**Item:** {order['item']}\n**Robux:** {order['robux']}\n**Payout:** {order['payout']}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/icons/1278435741973745735/e1811230cde8b1f563da7906f296b6ea.png?size=160&quality=lossless")
        embed.set_footer(text=f"Paid at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await log_channel.send(embed=embed)
    await ctx.send(f"✅ Payout for order {order_id} confirmed.")

# --------------------
# Additional helper commands that mirror original behaviour
# --------------------
@bot.command()
@allowed_server()
async def pending(ctx):
    if not pending_orders:
        await ctx.send("No pending orders.")
        return
    lines = []
    for oid, data in pending_orders.items():
        lines.append(f"ID {oid} | User: {data['user'].mention} | Item: {data['item']} | Robux: {data['robux']} | Staff: {data['staff'].mention}")
    embed = discord.Embed(title="Pending Orders", description="\n".join(lines), color=MAIN_COLOR)
    await ctx.send(embed=embed)

@bot.command()
@allowed_server()
async def latest(ctx):
    if not latest_orders:
        await ctx.send("No latest orders.")
        return
    lines = []
    for uid, data in latest_orders.items():
        lines.append(f"User: {data.get('discord_user', 'Unknown')} | Item: {data.get('item', 'Unknown')} | Robux: {data.get('robux', 'Unknown')}")
    embed = discord.Embed(title="Latest Orders", description="\n".join(lines), color=MAIN_COLOR)
    await ctx.send(embed=embed)



# ---------------- SETTINGS ----------------
MAIN_COLOR = 0x3B6CB0  # lighter mid-blue
IMAGE_URL = "https://images-ext-1.discordapp.net/external/rbGbSQa_vw1jUlpyHbEcacyNkpQtznZev1HEVhEjU98/%3Fformat%3Dwebp%26quality%3Dlossless%26width=279&height=279/https/images-ext-1.discordapp.net/external/JeJ5jkOf50ohxX5IdtJOy5_WaADNWhGUdBQog8qTcVA/%253Fsize%253D1024/https/cdn.discordapp.com/icons/1278435741973745735/810c2f3c6cb30d501c298ecbd06add0d.png?format=webp&quality=lossless&width=279&height=279"
CATEGORY_ID = 1436844165324603482  # Ticket category

# ---------------- HELPERS ----------------
def random_transaction_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def random_ticket_number():
    return random.randint(1000, 9999)

# ---------------- TICKET CREATION ----------------
async def create_ticket(ctx, author):
    category = bot.get_channel(CATEGORY_ID)
    if not category or not isinstance(category, discord.CategoryChannel):
        await ctx.send("Ticket category not found.", ephemeral=True)
        return None
    ticket_name = f"mm-ticket-{random_ticket_number()}"
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        bot.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    return await ctx.guild.create_text_channel(ticket_name, category=category, overwrites=overwrites)

# ---------------- ASK TARGET USER ----------------
async def ask_target_user(ctx, ticket_channel):
    embed = discord.Embed(
        title="Who are you dealing with?",
        description="Mention the other user or paste their ID\nExample: @user or 123456789123456789",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)
    await ticket_channel.send(embed=embed)

    def check(m):
        return m.channel == ticket_channel and not m.author.bot

    response = await bot.wait_for("message", check=check)
    try:
        target_user = await commands.MemberConverter().convert(ctx, response.content)
    except:
        try:
            target_user = await ctx.guild.fetch_member(int(response.content))
        except:
            target_user = None

    if target_user:
        await ticket_channel.set_permissions(target_user, read_messages=True, send_messages=True)
        confirm_embed = discord.Embed(
            title="User Added",
            description=f"{target_user.mention} has been added to this ticket.",
            color=MAIN_COLOR
        )
        confirm_embed.set_thumbnail(url=IMAGE_URL)
        await ticket_channel.send(embed=confirm_embed)
    else:
        await ticket_channel.send("Failed to add user. Invalid mention or ID.")

    return target_user

# ---------------- ROLE SELECTION ----------------
async def wait_roles(ticket_channel, users):
    role_data = {}
    embed = discord.Embed(
        title="Role Selection",
        description="Both users must select their role:\nClick **Giving** or **Receiving**.",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)
    view = View(timeout=None)

    for user in users:
        giving_btn = Button(label="Giving", style=discord.ButtonStyle.green)
        receiving_btn = Button(label="Receiving", style=discord.ButtonStyle.blurple)

        async def giving_callback(interaction, u=user):
            if interaction.user != u:
                return await interaction.response.send_message("Only your assigned user can select here.", ephemeral=True)
            role_data[u.id] = "Giving"
            await interaction.response.send_message("You selected **Giving**", ephemeral=True)

        async def receiving_callback(interaction, u=user):
            if interaction.user != u:
                return await interaction.response.send_message("Only your assigned user can select here.", ephemeral=True)
            role_data[u.id] = "Receiving"
            await interaction.response.send_message("You selected **Receiving**", ephemeral=True)

        giving_btn.callback = giving_callback
        receiving_btn.callback = receiving_callback
        view.add_item(giving_btn)
        view.add_item(receiving_btn)

    await ticket_channel.send(embed=embed, view=view)

    # wait until both users select
    while any(u.id not in role_data for u in users):
        await asyncio.sleep(1)

    return role_data

# ---------------- ASK DEAL AMOUNT ----------------
async def ask_deal_amount(ticket_channel):
    embed = discord.Embed(
        title="Deal Amount",
        description="Enter the amount expected for this deal:",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)
    await ticket_channel.send(embed=embed)

    def check(m):
        return m.channel == ticket_channel and not m.author.bot

    response = await bot.wait_for("message", check=check)
    return response.content

# ---------------- ASK FEE PAYER ----------------
async def ask_fee_payer(ticket_channel):
    embed = discord.Embed(
        title="MM Fee Payer",
        description="Who will cover the MM fee for this deal?",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)
    view = View(timeout=None)
    fee_choice = {}

    sender_btn = Button(label="Sender", style=discord.ButtonStyle.gray)
    receiver_btn = Button(label="Receiver", style=discord.ButtonStyle.gray)

    async def sender_callback(interaction):
        fee_choice["payer"] = "Sender"
        await interaction.response.send_message("Sender will pay the fee.", ephemeral=True)

    async def receiver_callback(interaction):
        fee_choice["payer"] = "Receiver"
        await interaction.response.send_message("Receiver will pay the fee.", ephemeral=True)

    sender_btn.callback = sender_callback
    receiver_btn.callback = receiver_callback
    view.add_item(sender_btn)
    view.add_item(receiver_btn)

    await ticket_channel.send(embed=embed, view=view)

    while "payer" not in fee_choice:
        await asyncio.sleep(1)
    return fee_choice["payer"]

# ---------------- SEND TRANSACTION EMBED ----------------
async def send_transaction_embed(ticket_channel):
    embed = discord.Embed(
        title="Transaction Request",
        description="Please wait for staff confirmation.",
        color=MAIN_COLOR
    )
    embed.set_thumbnail(url=IMAGE_URL)
    embed.set_footer(text=f"Transaction ID: {random_transaction_id()}")
    await ticket_channel.send(embed=embed)

# ---------------- $mmsend COMMAND ----------------
@bot.command()
async def mmsend(ctx, channel_id: int):
    target_channel = bot.get_channel(channel_id)
    if not target_channel:
        return await ctx.send("Invalid channel ID.")

    fees_embed = discord.Embed(
        title="MM REQUEST INITIATED",
        description=(
            "Fees:\n"
            "150m/s+ = 15%\n"
            "Under 100m/s = 10%\n"
            "Under 50m/s = 7%\n"
            "Under 30m/s = 5%\n"
            "Under 15m/s = Free"
        ),
        color=MAIN_COLOR
    )
    fees_embed.set_thumbnail(url=IMAGE_URL)
    fees_embed.set_footer(text="Kimchi MM System | Automated")

    view = View(timeout=None)
    start_btn = Button(label="Start Deal", style=discord.ButtonStyle.blurple)

    async def start_callback(interaction: discord.Interaction):
        if interaction.user != ctx.author:
            return await interaction.response.send_message("Only the ticket creator can start.", ephemeral=True)

        ticket_channel = await create_ticket(ctx, ctx.author)
        if not ticket_channel:
            return

        await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

        target_user = await ask_target_user(ctx, ticket_channel)
        users = [ctx.author, target_user]
        role_data = await wait_roles(ticket_channel, users)
        deal_amount = await ask_deal_amount(ticket_channel)
        fee_payer = await ask_fee_payer(ticket_channel)
        await send_transaction_embed(ticket_channel)

        # final summary
        summary = discord.Embed(
            title="MM Deal Summary",
            description=f"Deal Amount: `{deal_amount}`\nFee Payer: `{fee_payer}`\nRoles Selected:",
            color=MAIN_COLOR
        )
        summary.set_thumbnail(url=IMAGE_URL)
        for user_id, role in role_data.items():
            user = ctx.guild.get_member(user_id)
            if user:
                summary.add_field(name=user.display_name, value=role, inline=True)
        await ticket_channel.send(embed=summary)

    start_btn.callback = start_callback
    view.add_item(start_btn)
    await target_channel.send(embed=fees_embed, view=view)

# ---------------- $claim COMMAND ----------------
@bot.command()
async def claim(ctx):
    ticket_channel = ctx.channel
    await ticket_channel.send(f"{ctx.author.mention} claimed this ticket. Please wait for MM process.")

# --------------------
# Run Bot
import os

# get the token from Render environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot.run(BOT_TOKEN)
