# dribble_mm_full_ready_final.py
import discord
from discord.ext import commands
import asyncio
import random
import string
import os

# ------------------ BOT ------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

# ------------------ CONFIG ------------------

PANEL_CHANNEL_ID = 1437520131222671501
CATEGORY_ID = 1437519514869694545
MIDDLE_ROLE_ID = 1437545717227978822
ARCHIVE_CHANNEL_ID = 1437519958455095307
MIDDLEMAN_PAYPAL = "dribble.mm@gmail.com"
PAYPAL_QR = "YOUR_PAYPAL_QR_URL"

MAIN_COLOR = 0xB79BEB
ICON_URL = "https://images-ext-1.discordapp.net/external/6Dtval-9vtswsuE-cWp67CwjvLRqCH5ZRbEQiEEFDj8/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1437030353674965097/45a3aa89511f4e2fdc5f88a07a1b5296.png?format=webp&quality=lossless&width=387&height=387"
PLACEHOLDER_ICON = "https://i.pinimg.com/originals/84/8c/34/848c342a56e7854dec45b9349c21dfe5.gif"

CLOSED_CATEGORY_ID = 1438145474078179328

# ------------------ STORAGE ------------------
open_tickets = {}      # user_id : channel_id
ticket_codes = {}      # channel_id : secret_code
ticket_notes = {}      # channel_id : {note, roles, deal_amount, paypal_email}

# ------------------ HELPERS ------------------
def random_code(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_fee(amount: float) -> float:
    if amount >= 50:
        return round(amount * 0.04, 2)
    elif amount >= 40:
        return 3.50
    elif amount >= 25:
        return 2.50
    elif amount >= 10:
        return 1.50
    else:
        return 0.0

async def create_ticket_channel(guild, category_id, user_id):
    secret_code = random_code(10)
    category = discord.utils.get(guild.categories, id=category_id)
    channel_name = f"mm-ticket-{user_id}"
    ticket_channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.get_member(user_id): discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
    )
    open_tickets[user_id] = ticket_channel.id
    ticket_codes[ticket_channel.id] = secret_code
    ticket_notes[ticket_channel.id] = {
        "note": secret_code,
        "roles": {},
        "deal_amount": 0,
        "paypal_email": None
    }
    return ticket_channel, secret_code

# ------------------ $startmm ------------------
@bot.command()
async def startmm(ctx):
    panel_channel = bot.get_channel(PANEL_CHANNEL_ID)
    panel_embed = discord.Embed(
        title="PayPal",
        description=(
            "⬝ Dribble's Automatic Middleman\n\n"
            "**__Fees__**\n"
            "• Deals €50+: 4%\n"
            "• Deals under €40: €3.50\n"
            "• Deals under €25: €2.50\n"
            "• Deals under €10: €1.50\n"
            "• Deals under €5: FREE"
        ),
        color=MAIN_COLOR
    )
    panel_embed.set_thumbnail(url=ICON_URL)

    class RequestMM(discord.ui.View):
        @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.primary)
        async def request(self, interaction: discord.Interaction, button):
            if interaction.user.id in open_tickets:
                await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
                return

            ticket_channel, secret_code = await create_ticket_channel(
                interaction.guild, CATEGORY_ID, interaction.user.id
            )

            # --- Ticket Code Embed ---
            code_embed = discord.Embed(
                title="Ticket Created",
                description=f"Ticket code: ```{secret_code}```\nSave this for your safety.",
                color=MAIN_COLOR
            )
            code_embed.set_thumbnail(url=ICON_URL)
            await ticket_channel.send(embed=code_embed)

            # --- Welcome Embed ---
            welcome_embed = discord.Embed(
                title="Dribble Middleman System",
                description="Ticket created successfully!\nWelcome!",
                color=MAIN_COLOR
            )
            welcome_embed.set_thumbnail(url=PLACEHOLDER_ICON)
            await ticket_channel.send(embed=welcome_embed)

            # --- Ask Trading Partner Function ---
            async def ask_partner():
                ask_embed = discord.Embed(
                    title="Who are you dealing with?",
                    description="Mention them, ID, or username#1234",
                    color=MAIN_COLOR
                )
                await ticket_channel.send(embed=ask_embed)

                def user_check(m):
                    return m.channel == ticket_channel and m.author == interaction.user

                user_msg = await bot.wait_for("message", check=user_check)

                other_member = None
                if user_msg.mentions:
                    other_member = user_msg.mentions[0]
                else:
                    try:
                        other_member = await interaction.guild.fetch_member(int(user_msg.content))
                    except:
                        if "#" in user_msg.content:
                            name, discrim = user_msg.content.split("#", 1)
                            other_member = discord.utils.get(
                                interaction.guild.members, name=name, discriminator=discrim
                            )
                        if not other_member:
                            other_member = discord.utils.get(interaction.guild.members, name=user_msg.content)

                if not other_member:
                    await ticket_channel.send("Couldn't find the user. Mention them or provide ID/username#1234.")
                    return await ask_partner()

                # --- Confirm Partner Embed ---
                confirm_embed = discord.Embed(
                    title="Confirm Partner",
                    description=f"Deal with {other_member.mention}. Confirm or Decline.",
                    color=MAIN_COLOR
                )

                class ConfirmPartnerView(discord.ui.View):
                    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
                    async def confirm(self2, interaction2, button2):
                        await ticket_channel.set_permissions(
                            other_member, read_messages=True, send_messages=True
                        )
                        added_embed = discord.Embed(
                            title="User Added",
                            description=f"{other_member.mention} added to the ticket.",
                            color=MAIN_COLOR
                        )
                        added_embed.set_thumbnail(url=ICON_URL)
                        await ticket_channel.send(embed=added_embed)
                        self2.stop()
                        await ask_roles_and_amount(other_member)

                    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
                    async def decline(self2, interaction2, button2):
                        await interaction2.response.send_message("Partner selection declined. Please enter again.", ephemeral=True)
                        self2.stop()
                        await ask_partner()

                await ticket_channel.send(embed=confirm_embed, view=ConfirmPartnerView())

            # --- Ask Roles and Deal Amount ---
            async def ask_roles_and_amount(other_member):
                # --- Role Selection ---
                class RoleSelection(discord.ui.View):
                    def __init__(self):
                        super().__init__()
                        self.selected_roles = {}

                    @discord.ui.button(label="Sending Money", style=discord.ButtonStyle.secondary)
                    async def sending(self3, interaction3, button3):
                        if interaction3.user.id in self3.selected_roles:
                            await interaction3.response.send_message("Already selected role.", ephemeral=True)
                            return
                        self3.selected_roles[interaction3.user.id] = "Sending"
                        button3.disabled = True
                        await self3.update_embed(interaction3)

                    @discord.ui.button(label="Giving Item", style=discord.ButtonStyle.secondary)
                    async def giving(self3, interaction3, button3):
                        if interaction3.user.id in self3.selected_roles:
                            await interaction3.response.send_message("Already selected role.", ephemeral=True)
                            return
                        self3.selected_roles[interaction3.user.id] = "Giving"
                        button3.disabled = True
                        await self3.update_embed(interaction3)

                    async def update_embed(self3, interaction3):
                        embed = discord.Embed(
                            title="Role Selection",
                            description="\n".join([
                                f"**{interaction3.guild.get_member(uid).name}** selected **{role}**"
                                for uid, role in self3.selected_roles.items()
                            ]),
                            color=MAIN_COLOR
                        )
                        await interaction3.response.edit_message(embed=embed, view=self3)

                        if len(self3.selected_roles) == 2:
                            self3.stop()
                            sending_id = [uid for uid, r in self3.selected_roles.items() if r=="Sending"][0]
                            giving_id = [uid for uid, r in self3.selected_roles.items() if r=="Giving"][0]

                            # store roles
                            ticket_notes[ticket_channel.id]["roles"] = self3.selected_roles

                            # --- Ask Deal Amount ---
                            amount_embed = discord.Embed(
                                title="Enter Deal Amount",
                                description=f"<@{interaction.user.id}> please type the deal amount in euros (numbers only).",
                                color=MAIN_COLOR
                            )
                            await ticket_channel.send(embed=amount_embed)

                            def amount_check(m):
                                return m.channel == ticket_channel and m.author.id == interaction.user.id

                            amount_msg = await bot.wait_for("message", check=amount_check)
                            try:
                                deal_amount = float(amount_msg.content.strip())
                            except:
                                await ticket_channel.send("Invalid amount, defaulting to €50.")
                                deal_amount = 50

                            ticket_notes[ticket_channel.id]["deal_amount"] = deal_amount

                            # --- Fee Confirmation ---
                            fee = get_fee(deal_amount)
                            fee_embed = discord.Embed(
                                title="Deal Fee",
                                description=f"Middleman fee €{fee:.2f} covered by <@{sending_id}>.",
                                color=MAIN_COLOR
                            )

                            class FeeConfirmView(discord.ui.View):
                                @discord.ui.button(label="Okay", style=discord.ButtonStyle.green)
                                async def okay(self4, interaction4, button4):
                                    self4.stop()
                                    await send_invoice(ticket_channel, self3.selected_roles, deal_amount, fee, sending_id)

                            await ticket_channel.send(embed=fee_embed, view=FeeConfirmView())

                role_embed = discord.Embed(
                    title="Role Selection",
                    description="Select your role. Each participant can click one button.",
                    color=MAIN_COLOR
                )
                role_embed.set_thumbnail(url=ICON_URL)
                await ticket_channel.send(embed=role_embed, view=RoleSelection())

            await ask_partner()
            await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

    await panel_channel.send(embed=panel_embed, view=RequestMM())
    await ctx.send("MM Panel sent.")


# ------------------ SEND INVOICE ------------------
async def send_invoice(ticket_channel, selected_roles, amount, fee, fee_payer):
    sending_id = [uid for uid, role in selected_roles.items() if role=="Sending"][0]
    giving_id = [uid for uid, role in selected_roles.items() if role=="Giving"][0]
    total = amount + fee
    note = random_code(10)
    ticket_notes[ticket_channel.id]["note"] = note

    invoice_embed = discord.Embed(
        title="📩 Payment Invoice",
        description=(
            f"<@{sending_id}> send the funds to Middleman.\n"
            f"Include note. Once done type: $sent"
        ),
        color=MAIN_COLOR
    )
    invoice_embed.set_thumbnail(url="https://i.pinimg.com/originals/c0/34/17/c03417ebf4f447610528b07a704e0540.gif")
    invoice_embed.add_field(name="Address", value=MIDDLEMAN_PAYPAL, inline=False)
    invoice_embed.add_field(name="Amount", value=f"€{total:.2f}", inline=False)
    invoice_embed.add_field(name="Note", value=f"{note}", inline=False)

    class CopyDetails(discord.ui.View):
        @discord.ui.button(label="Copy Address", style=discord.ButtonStyle.primary)
        async def copy_address(self, interaction, button):
            await interaction.response.send_message(MIDDLEMAN_PAYPAL, ephemeral=True)

        @discord.ui.button(label="Copy Amount", style=discord.ButtonStyle.primary)
        async def copy_amount(self, interaction, button):
            await interaction.response.send_message(f"{total:.2f}", ephemeral=True)

        @discord.ui.button(label="Copy Note", style=discord.ButtonStyle.primary)
        async def copy_note(self, interaction, button):
            await interaction.response.send_message(f"{note}", ephemeral=True)

    await ticket_channel.send(embed=invoice_embed, view=CopyDetails())

# ------------------ RECEIVED ------------------
@bot.command()
async def received(ctx, ticket_code: str):
    # find channel id from ticket_codes (ticket_codes stores channel_id -> code)
    ticket_channel_id = None
    for cid, code in ticket_codes.items():
        if code == ticket_code:
            ticket_channel_id = cid
            break
    if ticket_channel_id is None:
        await ctx.send("Invalid ticket code.")
        return

    ticket_channel = bot.get_channel(ticket_channel_id)
    if not ticket_channel:
        await ctx.send("Ticket channel not found.")
        return

    tn = ticket_notes.get(ticket_channel.id)
    if not isinstance(tn, dict):
        await ctx.send("Ticket data invalid.")
        return

    roles = tn.get("roles", {})
    sending_ids = [uid for uid, r in roles.items() if r == "Sending"]
    giving_ids = [uid for uid, r in roles.items() if r == "Giving"]
    if not sending_ids or not giving_ids:
        await ctx.send("Roles not set correctly for this ticket.")
        return

    sending_id = sending_ids[0]
    giving_id = giving_ids[0]

    money_received_embed = discord.Embed(
        title="Item Delivery Confirmation 📦",
        description=(
            f"Money sender: `<@{sending_id}>`\n"
            f"Item giver: `<@{giving_id}>`\n\n"
            "Once the item has been received, click **Confirm Received**.\n"
            "If there’s an issue, the item giver can click **Report Problem**."
        ),
        color=MAIN_COLOR
    )

    class ReceivedView(discord.ui.View):
        @discord.ui.button(label="Confirm Received", style=discord.ButtonStyle.green)
        async def confirm_received(self, interaction: discord.Interaction, button: discord.ui.Button):
            # only sender can confirm
            if interaction.user.id != sending_id:
                await interaction.response.send_message("Only the money sender can confirm.", ephemeral=True)
                return

            # lock channel for both parties (remove read/send)
            await ticket_channel.set_permissions(interaction.guild.get_member(sending_id), read_messages=False, send_messages=False)
            await ticket_channel.set_permissions(interaction.guild.get_member(giving_id), read_messages=False, send_messages=False)

            # ask for paypal email privately
            await interaction.response.send_message("Type your PayPal email in chat to receive payment. (You have 2 minutes)", ephemeral=True)

            def check(m):
                return m.channel == ticket_channel and m.author.id == sending_id

            try:
                msg = await bot.wait_for("message", check=check, timeout=120)
            except asyncio.TimeoutError:
                await ticket_channel.send("Timeout: No PayPal email entered. Staff, please assist.")
                return

            paypal_email = msg.content.strip()
            tn["paypal_email"] = paypal_email

            # send single clean "Your money is due" embed once
            txn_embed = discord.Embed(
                title="Your Money is Due 💸",
                description=(
                    "Nicely done! The item has been delivered.\n\n"
                    "Transaction Summary:\n"
                    f"• Sender (Money): <@{sending_id}>\n"
                    f"• Receiver (Item): <@{giving_id}>\n"
                    f"• Amount: `€{tn.get('deal_amount', 0)}`\n"
                    f"• PayPal Email: `{tn['paypal_email']}`\n"
                    f"• Middleman Note: `{tn.get('note','')}`"
                ),
                color=MAIN_COLOR
            )
            await ticket_channel.send(embed=txn_embed)

        @discord.ui.button(label="Report Problem", style=discord.ButtonStyle.red)
        async def report_problem(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != giving_id:
                await interaction.response.send_message("Only the item giver can report a problem.", ephemeral=True)
                return
            await interaction.response.send_message("Problem reported. Staff will intervene shortly.", ephemeral=True)

    await ticket_channel.send(embed=money_received_embed, view=ReceivedView())
    await ctx.send(f"Money received panel sent in {ticket_channel.mention}.")

# ------------------ COMPLETED ------------------
@bot.command()
async def completed(ctx, paypal_txn_id: str, ticket_code: str):
    # find channel id by secret code
    ticket_channel_id = None
    for cid, code in ticket_codes.items():
        if code == ticket_code:
            ticket_channel_id = cid
            break
    if ticket_channel_id is None:
        await ctx.send("Invalid ticket code.")
        return

    ticket_channel = bot.get_channel(ticket_channel_id)
    if not ticket_channel:
        await ctx.send("Ticket channel not found.")
        return

    tn = ticket_notes.get(ticket_channel.id)
    if not isinstance(tn, dict):
        await ctx.send("Ticket data invalid.")
        return

    roles = tn.get("roles", {})
    sending_ids = [uid for uid, r in roles.items() if r == "Sending"]
    giving_ids = [uid for uid, r in roles.items() if r == "Giving"]
    sending_id = sending_ids[0] if sending_ids else None
    giving_id = giving_ids[0] if giving_ids else None

    completed_embed = discord.Embed(
        title="Transaction Completed ✅",
        description=(
            "The transaction has been completed, enjoy!\n\n"
            f"PayPal Transaction ID: `{paypal_txn_id}`\n"
            f"Sent to: `{tn.get('paypal_email','unknown')}`\n"
            f"Amount: `€{tn.get('deal_amount',0)}`\n\n"
            f"Sender (Money): `{sending_id}`\n"
            f"Receiver (Item): `{giving_id}`"
        ),
        color=MAIN_COLOR
    )

    # send to archive/completed channel (no mentions)
    completed_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if completed_channel:
        await completed_channel.send(embed=completed_embed)
        await ctx.send("Completed transaction logged to archive channel.")
    else:
        await ticket_channel.send(embed=completed_embed)
        await ctx.send("Completed transaction posted in ticket (archive channel not found).")

@bot.command()
async def tos(ctx):
    tos_embed = discord.Embed(
        title="Terms of Service",
        description=(
            "By using this service, you agree to the [Discord Terms of Service](https://discord.com/terms).\n\n"
            "You are responsible for understanding our platform rules before using the service.\n"
            "Failure to follow the Terms may result in loss of access or funds. User errors are not compensated.”\n\n"
            "**Dribble Terms:**\n"
            "1. Use the bot responsibly.\n"
            "2. Transaction Accuracy: It is your duty to send the invoice correctly. This includes the correct address, amount, note. "
            "If you fail to do so this may result in a permanent loss of funds.\n"
            "3. Fee bypassing: Splitting transactions to avoid a fee will result in an immediate ban.\n"
            "4. We guarantee the safety of all funds while they are in our direct possession. If a bot-related error causes a loss, "
            "users will be compensated at a 1:1 rate. Losses caused by user mistakes are not eligible for reimbursement.\n"
            "5. We are not responsible for any chargebacks or refunds that can happen in-game.\n"
            "6. When sending money you must send using **FRIENDS & FAMILY**. Not doing so may result in loss of funds. No refunds to prevent chargebacks."
        ),
        color=MAIN_COLOR
    )
    # optional thumbnail / footer
    tos_embed.set_thumbnail(url=ICON_URL)
    tos_embed.set_footer(text="Dribble Middleman • Read carefully")

    await ctx.send(embed=tos_embed)


# ------------------ RS (random simulation) ------------------
@bot.command()
async def rs(ctx, amount: int = None):
    await ctx.message.delete()  # delete the $rs message


    # if no amount given, generate random
    fake_amount_eur = round(amount if amount else random.uniform(5, 500), 2)
    fake_amount_usd = round(fake_amount_eur * 1.1, 2)  # rough eur → usd

    # generate fake ids + txn
    fake_sending_id = random.randint(10000000000000000, 99999999999999999)
    fake_giving_id = random.randint(10000000000000000, 99999999999999999)
    fake_txn = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

    completed_channel = bot.get_channel(1437519958455095307)

    completed_channel = bot.get_channel(1437519958455095307)

    embed = discord.Embed(
        title="Paypal Deal Complete",
        description=(
            f"**Amount**\n"
            f"`{fake_amount_eur}` EURO ({fake_amount_usd} USD)\n\n"
            f"**Sender**                       **Receiver**\n"
            f"<@{fake_sending_id}>       <@{fake_giving_id}>\n\n"
            f"**Paypal Transaction ID**\n"
            f"{fake_txn}"
        ),
        color=MAIN_COLOR
    )

    embed.set_thumbnail(url="https://images-ext-1.discordapp.net/external/6Dtval-9vtswsuE-cWp67CwjvLRqCH5ZRbEQiEEFDj8/%3Fsize%3D1024/https/cdn.discordapp.com/icons/1437030353674965097/45a3aa89511f4e2fdc5f88a07a1b5296.png?format=webp&quality=lossless&width=387&height=387")

    if completed_channel:
        await completed_channel.send(embed=embed)

# ------------------ $close ------------------
# when closing a ticket
@bot.command()
async def close(ctx, ticket_code: str):
    ticket_channel_id = None
    for cid, code in ticket_codes.items():
        if code == ticket_code:
            ticket_channel_id = cid
            break
    if ticket_channel_id is None:
        await ctx.send("Invalid ticket code.")
        return

    ticket_channel = bot.get_channel(ticket_channel_id)
    closed_category = ctx.guild.get_channel(CLOSED_CATEGORY_ID)
    await ticket_channel.edit(
        name=f"closed-{ticket_code}",
        category=closed_category
    )

    tn = ticket_notes.get(ticket_channel.id, {})
    for uid in tn.get("roles", {}):
        member = ctx.guild.get_member(uid)
        if member:
            await ticket_channel.set_permissions(member, overwrite=None)

    # remove user from open_tickets
    for user_id, ch_id in list(open_tickets.items()):
        if ch_id == ticket_channel.id:
            open_tickets.pop(user_id)

    await ticket_channel.send("Ticket closed and moved to closed category. Only staff can access now.")



# ------------------ $sent ------------------
@bot.command()
async def sent(ctx):
    middle_role = ctx.guild.get_role(MIDDLE_ROLE_ID)
    if middle_role:
        msg = await ctx.send(f"{middle_role.mention}")
        await msg.delete()
    ticket_channel = ctx.channel
    embed = discord.Embed(
        title="Claimed Sent",
        description="Do **NOT** give any items yet, please wait until a staff can confirm that the money has been received. We do this to prevent scams, sorry for the wait.",
        color=MAIN_COLOR
    )
    await ticket_channel.send(embed=embed)


# ------------------ $open ------------------
@bot.command()
async def open(ctx, ticket_code: str):
    ticket_channel_id = None
    for cid, code in ticket_codes.items():
        if code == ticket_code:
            ticket_channel_id = cid
            break
    if ticket_channel_id is None:
        await ctx.send("Invalid ticket code.")
        return

    ticket_channel = bot.get_channel(ticket_channel_id)
    if not ticket_channel:
        await ctx.send("Ticket channel not found.")
        return

    category = discord.utils.get(ctx.guild.categories, id=CATEGORY_ID)
    await ticket_channel.edit(category=category)

    tn = ticket_notes.get(ticket_channel.id, {})
    for uid in tn.get("roles", {}):
        member = ctx.guild.get_member(uid)
        if member:
            await ticket_channel.set_permissions(member, read_messages=True, send_messages=True)

    middle_role = ctx.guild.get_role(MIDDLE_ROLE_ID)
    await ticket_channel.send(f"{middle_role.mention} <@{ctx.author.id}> reopened ticket")


# ------------------ $delete ------------------
    # when deleting a ticket
    @bot.command()
    async def delete(ctx, code: str):
        ticket_channel_id = None
        for cid, c in ticket_codes.items():
            if c == code:
                ticket_channel_id = cid
                break
        if ticket_channel_id is None:
            await ctx.send("Invalid ticket code.")
            return
        ticket_channel = bot.get_channel(ticket_channel_id)
        if ticket_channel:
            await ticket_channel.delete()
            open_tickets.pop(ticket_channel_id, None)  # <- fix
            ticket_codes.pop(ticket_channel_id, None)
            ticket_notes.pop(ticket_channel_id, None)
            await ctx.send(f"Ticket {code} deleted.")



# ------------------ $startsupport ------------------
@bot.command()
async def startsupport(ctx):
    panel_channel = bot.get_channel(SUPPORT_PANEL_CHANNEL)
    embed = discord.Embed(
        title="Support",
        description="Please only use these tickets if you have been scammed or you need support.",
        color=MAIN_COLOR
    )

    class SupportView(discord.ui.View):
        @discord.ui.button(label="Support", style=discord.ButtonStyle.primary)
        async def support_button(self, interaction: discord.Interaction, button):
            if interaction.user.id in open_tickets:
                await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
                return
            category = discord.utils.get(interaction.guild.categories, id=SUPPORT_CATEGORY_ID)
            ticket_channel = await interaction.guild.create_text_channel(
                name=f"support-{interaction.user.id}",
                category=category,
                overwrites={
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
            )
            open_tickets[interaction.user.id] = ticket_channel.id
            await ticket_channel.send(f"{interaction.user.mention} your support ticket is created!")
            await interaction.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

    await panel_channel.send(embed=embed, view=SupportView())




# ------------------ BOT EVENTS ------------------
@bot.event
async def on_ready():
    print("Bot ready", bot.user)

# ------------------ RUN ------------------
import os
bot.run(os.getenv("TOKEN"))

