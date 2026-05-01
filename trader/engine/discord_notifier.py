import httpx
import os
import threading
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID    = int(os.getenv("DISCORD_GUILD_ID", "0"))

# -----------------------------------------------------------------------
# Webhook alerts (unchanged from before — used by paper_trader.py)
# -----------------------------------------------------------------------

def _build_payload(title: str, fields: list[dict], color: int, footer: str = "Paper Trading Engine") -> dict:
    return {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": footer},
        }]
    }

def send_discord_alert_sync(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        with httpx.Client() as client:
            client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")

async def send_discord_alert(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")


# -----------------------------------------------------------------------
# Slash command bot
# -----------------------------------------------------------------------

class TradingBot(discord.Client):
    def __init__(self, account):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.account = account  # Reference to your PaperAccount instance
        self.tree = app_commands.CommandTree(self)
        self.guild = discord.Object(id=DISCORD_GUILD_ID)

    async def setup_hook(self):
        """Register slash commands to your guild on startup."""
        self.tree.copy_global_to(guild=self.guild)
        await self.tree.sync(guild=self.guild)
        print("[DISCORD BOT] Slash commands synced.")

    async def on_ready(self):
        print(f"[DISCORD BOT] Logged in as {self.user}")


def create_bot(account) -> TradingBot:
    bot = TradingBot(account)

    # -----------------------------------------------------------------------
    # /portfolio
    # -----------------------------------------------------------------------
    @bot.tree.command(name="portfolio", description="Show balance and open positions")
    async def portfolio(interaction: discord.Interaction):
        acc = bot.account
        balance  = acc.getBalance()
        pnl      = acc.getPnL()
        positions = acc.getPositions()
        pnl_color = 0x2ECC71 if pnl >= 0 else 0xE74C3C

        fields = [
            {"name": "💰 Cash Balance",    "value": f"${balance:,.2f}",          "inline": True},
            {"name": "📈 Total PnL",        "value": f"${pnl:+,.2f}",             "inline": True},
            {"name": "📂 Open Positions",   "value": str(len(positions)),         "inline": True},
        ]

        for mint, pos in list(positions.items())[:10]:  # cap at 10 to avoid embed limits
            fields.append({
                "name": pos["token_symbol"],
                "value": (
                    f"Entry: ${pos['entry_price']:.6f}\n"
                    f"Size:  {pos['amount']:.4f} tokens\n"
                    f"Cost:  ${pos['cost_basis']:.2f}"
                ),
                "inline": True
            })

        embed = discord.Embed(title="📊 Portfolio Summary", color=pnl_color)
        for f in fields:
            embed.add_field(name=f["name"], value=f["value"], inline=f["inline"])
        embed.set_footer(text="Paper Trading Engine")

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------------------------------
    # /pnl
    # -----------------------------------------------------------------------
    @bot.tree.command(name="pnl", description="Show PnL summary")
    async def pnl(interaction: discord.Interaction):
        acc = bot.account
        total_pnl = acc.getPnL()

        # Calculate today's PnL from trade history
        from datetime import datetime, timezone, date
        today = date.today()
        today_pnl = sum(
            t.realised_pnl
            for t in acc.tradeHistory
            if hasattr(t, "realised_pnl")
            and t.realised_pnl is not None
            and t.timestamp.date() == today
        )

        color = 0x2ECC71 if total_pnl >= 0 else 0xE74C3C
        embed = discord.Embed(title="💹 PnL Report", color=color)
        embed.add_field(name="📅 Today's PnL",  value=f"${today_pnl:+,.2f}", inline=True)
        embed.add_field(name="📈 All-Time PnL", value=f"${total_pnl:+,.2f}", inline=True)
        embed.add_field(
            name="💼 Initial Balance",
            value=f"${acc.initialBalance:,.2f}",
            inline=True
        )
        embed.set_footer(text="Paper Trading Engine")

        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------------------------------
    # /positions
    # -----------------------------------------------------------------------
    @bot.tree.command(name="positions", description="List all current holdings")
    async def positions(interaction: discord.Interaction):
        acc = bot.account
        pos_dict = acc.getPositions()

        if not pos_dict:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📂 Open Positions",
                    description="No open positions right now.",
                    color=0x95A5A6
                )
            )
            return

        embed = discord.Embed(title=f"📂 Open Positions ({len(pos_dict)})", color=0x3498DB)

        for mint, pos in list(pos_dict.items())[:25]:  # Discord limit: 25 fields
            symbol       = pos["token_symbol"]
            amount       = pos["amount"]
            entry        = pos["entry_price"]
            peak         = pos["peak_price"]
            cost         = pos["cost_basis"]
            wallet       = pos["wallet_address"]
            tp_sold      = pos.get("tp_sold", False)

            embed.add_field(
                name=f"{symbol}",
                value=(
                    f"Amount: `{amount:.4f}`\n"
                    f"Entry:  `${entry:.6f}`\n"
                    f"Peak:   `${peak:.6f}`\n"
                    f"Cost:   `${cost:.2f}`\n"
                    f"TP Fired: {'✅' if tp_sold else '❌'}\n"
                    f"Whale: `{wallet[:8]}...`"
                ),
                inline=True
            )

        embed.set_footer(text="Paper Trading Engine")
        await interaction.response.send_message(embed=embed)

    # -----------------------------------------------------------------------
    # /whales
    # -----------------------------------------------------------------------
    @bot.tree.command(name="whales", description="Show top performing tracked wallets")
    async def whales(interaction: discord.Interaction):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:8000/api/traders", timeout=5)
            traders = resp.json()
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not fetch whale data: {e}")
            return

        if not traders:
            await interaction.response.send_message(
                embed=discord.Embed(title="🐋 Whale Wallets", description="No wallets tracked yet.", color=0x95A5A6)
            )
            return

        embed = discord.Embed(title="🐋 Top Performing Wallets", color=0x9B59B6)

        for i, t in enumerate(traders[:10], 1):  # top 10
            wallet  = t["id"]
            total   = t["total_pnl"]
            wins    = t["winning_trades"]
            losses  = t["losing_trades"]
            avg     = t["avg_pnl_per_trade"]
            best    = t["best_trade_pnl"]

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            pnl_emoji = "🟢" if total >= 0 else "🔴"

            embed.add_field(
                name=f"#{i} `{wallet[:8]}...`",
                value=(
                    f"{pnl_emoji} PnL: `${total:+,.2f}`\n"
                    f"W/L: `{wins}/{losses}` ({win_rate:.0f}%)\n"
                    f"Avg: `${avg:+,.2f}` | Best: `${best:,.2f}`"
                ),
                inline=True
            )

        embed.set_footer(text="Paper Trading Engine")
        await interaction.response.send_message(embed=embed)

    return bot


def start_discord_bot(account):
    """Run the bot in its own thread so it doesn't block the trading engine."""
    if not DISCORD_BOT_TOKEN:
        print("[DISCORD BOT] No token set, skipping bot startup.")
        return

    import asyncio

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot = create_bot(account)
        loop.run_until_complete(bot.start(DISCORD_BOT_TOKEN))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("[DISCORD BOT] Bot thread started.")