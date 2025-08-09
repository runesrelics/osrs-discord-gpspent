import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from typing import Optional

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
spending_file = "spending.json"

# Load or initialize spending data
if os.path.exists(spending_file):
    with open(spending_file, "r") as f:
        spending_data = json.load(f)
else:
    spending_data = {}

# Role thresholds in GP, ordered from highest to lowest for role assignment
role_thresholds = {
    "Relic": 10_000_000_000,
    "Eternal": 5_000_000_000,
    "Zenyte": 1_000_000_000,
    "Onyx": 800_000_000,
    "Dragonstone": 600_000_000,
    "Diamond": 400_000_000,
    "Ruby": 200_000_000,
    "Emerald": 100_000_000,
    "Sapphire": 50_000_000
}

# Reaction role mappings
reaction_roles = {
    "🎉": "Giveaways",  # party emoji
    "💀": "PvP",        # skull emoji
    "⚔️": "PvM",        # crossswords emoji
    "🤖": "Botters"     # robot emoji
}

def save_data():
    with open(spending_file, "w") as f:
        json.dump(spending_data, f)

def get_current_role(total_spent):
    for role_name, threshold in role_thresholds.items():
        if total_spent >= threshold:
            return role_name
    return None

async def update_roles(member: discord.Member, guild: discord.Guild, total_spent: int):
    new_role_name = get_current_role(total_spent)
    if not new_role_name:
        return

    new_role = discord.utils.get(guild.roles, name=new_role_name)
    if not new_role:
        return

    roles_to_remove = [
        discord.utils.get(guild.roles, name=role)
        for role in role_thresholds.keys()
        if role != new_role_name
    ]
    roles_to_remove = [r for r in roles_to_remove if r in member.roles and r is not None]

    await member.add_roles(new_role)
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove)

def parse_amount(amount_str: str) -> int:
    amount_str = amount_str.lower().strip()
    multipliers = {"k": 10**3, "m": 10**6, "b": 10**9}

    if amount_str[-1] in multipliers:
        try:
            number = float(amount_str[:-1])
            return int(number * multipliers[amount_str[-1]])
        except ValueError:
            raise ValueError("Invalid amount format.")
    else:
        # Just try parsing as int
        return int(amount_str)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# /spent [amount] [user] - admin only, supports shorthand, message public
@bot.tree.command(name="spent", description="Log spending for a member (admin only)")
@app_commands.describe(amount="Amount of GP spent (e.g. 100m, 1b)", user="Member to log spending for")
@app_commands.checks.has_permissions(manage_guild=True)
async def spent(interaction: discord.Interaction, amount: str, user: discord.Member):
    try:
        total_amount = parse_amount(amount)
    except ValueError:
        await interaction.response.send_message("Invalid amount format! Use numbers with optional 'k', 'm', or 'b' suffix.", ephemeral=True)
        return

    uid = str(user.id)
    spending_data[uid] = spending_data.get(uid, 0) + total_amount
    save_data()

    await update_roles(user, interaction.guild, spending_data[uid])
    total = spending_data[uid]

    await interaction.response.send_message(
        f"{user.mention} has now spent **{total:,} GP**."
    )

# /checkspending [user?] - anyone can use, public message
@bot.tree.command(name="checkspending", description="Check OSRS GP spending for yourself or another member")
@app_commands.describe(user="Member to check spending for (optional)")
async def checkspending(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    uid = str(target.id)
    total = spending_data.get(uid, 0)
    role = get_current_role(total)
    role_text = f" and holds the **{role}** role!" if role else " and has no assigned role."
    await interaction.response.send_message(
        f"{target.mention} has spent **{total:,} GP**{role_text}"
    )

# /leaderboard - anyone can use, public message
@bot.tree.command(name="leaderboard", description="Show the top OSRS GP spenders")
async def leaderboard(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    sorted_spenders = sorted(spending_data.items(), key=lambda x: x[1], reverse=True)[:10]

    leaderboard_lines = []
    for rank, (uid, total) in enumerate(sorted_spenders, start=1):
        member = guild.get_member(int(uid))
        if member:
            leaderboard_lines.append(f"**{rank}.** {member.mention} — **{total:,} GP**")
        else:
            leaderboard_lines.append(f"**{rank}.** <@{uid}> — **{total:,} GP**")

    if not leaderboard_lines:
        await interaction.response.send_message("No spending data available.", ephemeral=True)
        return

    leaderboard_text = "\n".join(leaderboard_lines)

    await interaction.response.send_message(f"**Top OSRS GP Spenders:**\n{leaderboard_text}")

# /React - admin only, creates reaction role message
@bot.tree.command(name="react", description="Create a reaction role message (admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def react(interaction: discord.Interaction):
    # Create the message
    message = await interaction.channel.send("React here")
    
    # Add all the reactions
    for emoji in reaction_roles.keys():
        await message.add_reaction(emoji)
    
    await interaction.response.send_message("Reaction role message created!", ephemeral=True)

# Reaction event handlers
@bot.event
async def on_raw_reaction_add(payload):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return
    
    emoji = str(payload.emoji)
    if emoji not in reaction_roles:
        return
    
    role_name = reaction_roles[emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    
    if role and role not in member.roles:
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    emoji = str(payload.emoji)
    if emoji not in reaction_roles:
        return
    
    role_name = reaction_roles[emoji]
    role = discord.utils.get(guild.roles, name=role_name)
    
    if role:
        member = guild.get_member(payload.user_id)
        if member and role in member.roles:
            await member.remove_roles(role)

import os
bot.run(os.environ["GPBOT_DISCORD"])
