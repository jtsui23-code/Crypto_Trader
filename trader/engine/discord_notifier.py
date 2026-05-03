import httpx
import os
import threading
import discord
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID    = int(os.getenv("DISCORD_GUILD_ID", "0"))

ENGINE_URL = "http://paper_trader:8001"

# -----------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------

_BLANK = {"name": "\u200b", "value": "\u200b", "inline": True}

def _now_ts() -> datetime:
    return datetime.now(timezone.utc)

def _fmt_ts(dt: datetime | None = None) -> str:
    """01 May 2026 • 14:35:22 UTC"""
    if dt is None:
        dt = _now_ts()
    return dt.strftime("%d %B %Y • %H:%M:%S UTC")

def _footer(label: str = "Paper Trading Engine") -> dict:
    return {"text": f"🤖 {label}  |  {_fmt_ts()}"}

def _pad_to_3(fields: list[dict]) -> list[dict]:
    """Pad inline fields to a multiple of 3 so Discord renders a clean 3-column grid."""
    remainder = len(fields) % 3
    if remainder:
        fields += [_BLANK] * (3 - remainder)
    return fields

def _make_embed(title: str, color: int, fields: list[dict],
                description: str | None = None) -> discord.Embed:
    """Single factory for all slash-command embeds — consistent structure every time."""
    embed = discord.Embed(title=title, color=color, description=description)
    for f in _pad_to_3(list(fields)):
        embed.add_field(name=f["name"], value=f["value"], inline=f.get("inline", True))
    embed.set_footer(**_footer())
    embed.timestamp = _now_ts()
    return embed


# -----------------------------------------------------------------------
# Webhook alerts — called directly by paper_trader.py
# -----------------------------------------------------------------------

def _build_payload(title: str, fields: list[dict], color: int,
                   footer: str = "Paper Trading Engine") -> dict:
    padded = _pad_to_3(list(fields))
    return {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": padded,
            "footer": {"text": f"🤖 {footer}  |  {_fmt_ts()}"},
            "timestamp": _now_ts().isoformat(),
        }]
    }

def send_discord_alert_sync(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] No webhook URL set, skipping alert.")
        return
    try:
        with httpx.Client() as client:
            resp = client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
            if resp.status_code not in (200, 204):
                print(f"[DISCORD] Webhook returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")

async def send_discord_alert(title: str, fields: list[dict], color: int):
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD] No webhook URL set, skipping alert.")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=_build_payload(title, fields, color), timeout=5)
            if resp.status_code not in (200, 204):
                print(f"[DISCORD] Webhook returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[DISCORD] Failed to send alert: {e}")


# -----------------------------------------------------------------------
# Slash command bot
# -----------------------------------------------------------------------

class TradingBot(discord.Client):
    def __init__(self, account):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.account = account
        self.tree = app_commands.CommandTree(self)
        self.guild_obj = discord.Object(id=DISCORD_GUILD_ID)

    async def setup_hook(self):
        """
        setup_hook is the correct place to register and sync guild commands.
        Commands added here are registered BEFORE sync() is called, which is
        why the previous approach (decorating outside setup_hook, then syncing
        inside it) resulted in empty syncs — the tree was populated after the
        fact but the sync had already fired with nothing in it.
        """
        _register_commands(self)
        await self.tree.sync(guild=self.guild_obj)
        print("[DISCORD BOT] Slash commands synced to guild.")

    async def on_ready(self):
        print(f"[DISCORD BOT] Logged in as {self.user} — {len(self.tree.get_commands(guild=self.guild_obj))} guild commands registered.")


def _register_commands(bot: TradingBot):
    """
    All slash commands are defined here and added to bot.tree before
    setup_hook calls sync(). This guarantees they exist in the tree
    at sync time and are registered on Discord's side immediately.
    """
    guild = bot.guild_obj

    # -------------------------------------------------------------------
    # /portfolio — balance, PnL, and top open positions
    # -------------------------------------------------------------------
    @bot.tree.command(name="portfolio", description="Show balance and open positions", guild=guild)
    async def portfolio(interaction: discord.Interaction):
        await interaction.response.defer()
        acc       = bot.account
        balance   = acc.getBalance()
        pnl       = acc.getPnL()
        positions = acc.getPositions()
        color     = 0x2ECC71 if pnl >= 0 else 0xE74C3C

        fields = [
            {"name": "💰 Cash Balance",  "value": f"`${balance:,.2f}`",  "inline": True},
            {"name": "📈 Total PnL",     "value": f"`${pnl:+,.2f}`",     "inline": True},
            {"name": "📂 Positions",     "value": f"`{len(positions)}`", "inline": True},
        ]

        if positions:
            fields.append({"name": "─" * 32, "value": "\u200b", "inline": False})
            for mint, pos in list(positions.items())[:9]:
                fields.append({
                    "name": pos["token_symbol"],
                    "value": (
                        f"Entry: `${pos['entry_price']:.6f}`\n"
                        f"Size:  `{pos['amount']:.4f}`\n"
                        f"Cost:  `${pos['cost_basis']:.2f}`"
                    ),
                    "inline": True,
                })

        await interaction.followup.send(embed=_make_embed("📊 Portfolio Summary", color, fields))

    # -------------------------------------------------------------------
    # /pnl — today vs all-time PnL
    # -------------------------------------------------------------------
    @bot.tree.command(name="pnl", description="Show today's and all-time PnL", guild=guild)
    async def pnl(interaction: discord.Interaction):
        await interaction.response.defer()
        from datetime import date
        acc       = bot.account
        total_pnl = acc.getPnL()
        today     = date.today()

        today_pnl = sum(
            t.realised_pnl
            for t in acc.tradeHistory
            if hasattr(t, "realised_pnl")
            and t.realised_pnl is not None
            and t.timestamp.date() == today
        )

        color = 0x2ECC71 if total_pnl >= 0 else 0xE74C3C
        fields = [
            {"name": "📅 Today's PnL",    "value": f"`${today_pnl:+,.2f}`",         "inline": True},
            {"name": "📈 All-Time PnL",   "value": f"`${total_pnl:+,.2f}`",         "inline": True},
            {"name": "💼 Initial Balance", "value": f"`${acc.initialBalance:,.2f}`", "inline": True},
        ]

        await interaction.followup.send(embed=_make_embed("💹 PnL Report", color, fields))

    # -------------------------------------------------------------------
    # /positions — all open holdings
    # -------------------------------------------------------------------
    @bot.tree.command(name="positions", description="List all current holdings", guild=guild)
    async def positions(interaction: discord.Interaction):
        await interaction.response.defer()
        acc      = bot.account
        pos_dict = acc.getPositions()

        if not pos_dict:
            await interaction.followup.send(
                embed=_make_embed("📂 Open Positions", 0x95A5A6, [], description="No open positions right now.")
            )
            return

        fields = []
        for mint, pos in list(pos_dict.items())[:24]:
            tp_sold = pos.get("tp_sold", False)
            wallet  = pos["wallet_address"]
            fields.append({
                "name": pos["token_symbol"],
                "value": (
                    f"Amount: `{pos['amount']:.4f}`\n"
                    f"Entry:  `${pos['entry_price']:.6f}`\n"
                    f"Peak:   `${pos['peak_price']:.6f}`\n"
                    f"Cost:   `${pos['cost_basis']:.2f}`\n"
                    f"TP: {'✅' if tp_sold else '❌'}  Whale: `{wallet[:8]}…`"
                ),
                "inline": True,
            })

        await interaction.followup.send(
            embed=_make_embed(f"📂 Open Positions ({len(pos_dict)})", 0x3498DB, fields)
        )

    # -------------------------------------------------------------------
    # /whales — top performing tracked wallets
    # -------------------------------------------------------------------
    @bot.tree.command(name="whales", description="Show top performing tracked wallets", guild=guild)
    async def whales(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://api:8000/api/traders", timeout=5)
            traders = resp.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Could not fetch whale data: {e}")
            return

        if not traders:
            await interaction.followup.send(
                embed=_make_embed("🐋 Whale Wallets", 0x95A5A6, [], description="No wallets tracked yet.")
            )
            return

        fields = []
        for i, t in enumerate(traders[:9], 1):
            wins         = t["winning_trades"]
            losses       = t["losing_trades"]
            total_trades = wins + losses
            win_rate     = (wins / total_trades * 100) if total_trades > 0 else 0
            total        = t["total_pnl"]

            fields.append({
                "name": f"{'🟢' if total >= 0 else '🔴'} #{i} `{t['id'][:8]}…`",
                "value": (
                    f"PnL:  `${total:+,.2f}`\n"
                    f"W/L:  `{wins}/{losses}` ({win_rate:.0f}%)\n"
                    f"Avg:  `${t['avg_pnl_per_trade']:+,.2f}`\n"
                    f"Best: `${t['best_trade_pnl']:,.2f}`"
                ),
                "inline": True,
            })

        await interaction.followup.send(
            embed=_make_embed("🐋 Top Performing Wallets", 0x9B59B6, fields)
        )

    # -------------------------------------------------------------------
    # /config — view or update engine configuration
    # -------------------------------------------------------------------
    @bot.tree.command(name="config", description="View or update engine configuration", guild=guild)
    @app_commands.describe(
        risk_per_trade    = "Fraction of balance per trade (e.g. 0.05 = 5%)",
        take_profit_pct   = "Price gain to trigger partial TP exit (e.g. 0.2 = 20%)",
        take_profit_split = "Fraction of position to sell at TP (e.g. 0.7 = 70%)",
        trailing_stop_pct = "Max drop from peak before trailing stop fires (e.g. 0.35 = 35%)",
        stop_loss_pct     = "Hard stop-loss below entry (e.g. 0.15 = 15%)",
        max_hold_seconds  = "Max seconds to hold before force-selling (e.g. 70)",
        dex_fee_pct       = "DEX fee per swap (e.g. 0.0025 = 0.25% for Raydium/Jupiter)",
    )
    async def config(
        interaction: discord.Interaction,
        risk_per_trade:    float | None = None,
        take_profit_pct:   float | None = None,
        take_profit_split: float | None = None,
        trailing_stop_pct: float | None = None,
        stop_loss_pct:     float | None = None,
        max_hold_seconds:  int   | None = None,
        dex_fee_pct:       float | None = None,
    ):
        await interaction.response.defer()

        # If no args supplied, just show the current config
        any_provided = any(v is not None for v in [
            risk_per_trade, take_profit_pct, take_profit_split,
            trailing_stop_pct, stop_loss_pct, max_hold_seconds, dex_fee_pct,
        ])

        if not any_provided:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get("http://api:8000/api/settings/config", timeout=5)
                cfg = resp.json()
            except Exception as e:
                await interaction.followup.send(f"❌ Could not fetch config: {e}")
                return

            fields = [
                {"name": "⚖️ Risk / Trade",      "value": f"`{cfg.get('risk_per_trade', '?')}`",    "inline": True},
                {"name": "🎯 Take Profit %",      "value": f"`{cfg.get('take_profit_pct', '?')}`",   "inline": True},
                {"name": "✂️ TP Split",            "value": f"`{cfg.get('take_profit_split', '?')}`", "inline": True},
                {"name": "📉 Trailing Stop %",    "value": f"`{cfg.get('trailing_stop_pct', '?')}`", "inline": True},
                {"name": "🛑 Stop Loss %",        "value": f"`{cfg.get('stop_loss_pct', '?')}`",     "inline": True},
                {"name": "⏱️ Max Hold (secs)",    "value": f"`{cfg.get('max_hold_seconds', '?')}`",  "inline": True},
                {"name": "💸 DEX Fee %",          "value": f"`{cfg.get('dex_fee_pct', '?')}`",       "inline": True},
            ]
            await interaction.followup.send(
                embed=_make_embed("⚙️ Engine Configuration", 0x3498DB, fields)
            )
            return

        # Build payload with only the provided values so we don't accidentally
        # zero-out fields the user didn't mention. Fetch current config first,
        # then overlay the new values.
        try:
            async with httpx.AsyncClient() as client:
                current = (await client.get("http://api:8000/api/settings/config", timeout=5)).json()
        except Exception as e:
            await interaction.followup.send(f"❌ Could not fetch current config to merge: {e}")
            return

        payload = {
            "risk_per_trade":    risk_per_trade    if risk_per_trade    is not None else current["risk_per_trade"],
            "take_profit_pct":   take_profit_pct   if take_profit_pct   is not None else current["take_profit_pct"],
            "take_profit_split": take_profit_split if take_profit_split is not None else current["take_profit_split"],
            "trailing_stop_pct": trailing_stop_pct if trailing_stop_pct is not None else current["trailing_stop_pct"],
            "stop_loss_pct":     stop_loss_pct     if stop_loss_pct     is not None else current["stop_loss_pct"],
            "max_hold_seconds":  max_hold_seconds  if max_hold_seconds  is not None else current["max_hold_seconds"],
            "dex_fee_pct":       dex_fee_pct       if dex_fee_pct       is not None else current.get("dex_fee_pct", 0.0025),
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("http://api:8000/api/settings/config", json=payload, timeout=5)
            if resp.status_code != 200:
                await interaction.followup.send(f"❌ Engine returned {resp.status_code}: {resp.text}")
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Could not reach engine: {e}")
            return

        fields = [
            {"name": "⚖️ Risk / Trade",    "value": f"`{payload['risk_per_trade']}`",    "inline": True},
            {"name": "🎯 Take Profit %",    "value": f"`{payload['take_profit_pct']}`",   "inline": True},
            {"name": "✂️ TP Split",          "value": f"`{payload['take_profit_split']}`", "inline": True},
            {"name": "📉 Trailing Stop %",  "value": f"`{payload['trailing_stop_pct']}`", "inline": True},
            {"name": "🛑 Stop Loss %",      "value": f"`{payload['stop_loss_pct']}`",     "inline": True},
            {"name": "⏱️ Max Hold (secs)",  "value": f"`{payload['max_hold_seconds']}`",  "inline": True},
            {"name": "💸 DEX Fee %",        "value": f"`{payload['dex_fee_pct']}`",       "inline": True},
        ]
        await interaction.followup.send(
            embed=_make_embed("✅ Configuration Updated", 0x2ECC71, fields)
        )

    # -------------------------------------------------------------------
    # /reset — wipe positions and restart with a fresh balance
    # -------------------------------------------------------------------
    @bot.tree.command(name="reset", description="Reset the paper trading engine", guild=guild)
    @app_commands.describe(balance="Starting balance after reset (default: 10000)")
    async def reset(interaction: discord.Interaction, balance: float = 10000.0):
        await interaction.response.defer()

        if balance <= 0:
            await interaction.followup.send("❌ Balance must be greater than 0.")
            return

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://api:8000/api/engine/reset",
                    json={"new_balance": balance},
                    timeout=10,
                )
            if resp.status_code != 200:
                await interaction.followup.send(f"❌ Engine returned {resp.status_code}: {resp.text}")
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Could not reach engine: {e}")
            return

        fields = [
            {"name": "💰 New Balance",  "value": f"`${balance:,.2f}`",    "inline": True},
            {"name": "📂 Positions",    "value": "`Cleared`",              "inline": True},
            {"name": "📜 Trade History","value": "`Cleared`",              "inline": True},
        ]
        await interaction.followup.send(
            embed=_make_embed("🔄 Engine Reset", 0xE67E22, fields)
        )


def start_discord_bot(account):
    """Run the bot in its own daemon thread so it doesn't block the trading engine."""
    if not DISCORD_BOT_TOKEN:
        print("[DISCORD BOT] No token set, skipping bot startup.")
        return

    import asyncio

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Pass account into TradingBot — _register_commands is called inside
        # setup_hook so commands exist in the tree before sync fires.
        bot = TradingBot(account)
        loop.run_until_complete(bot.start(DISCORD_BOT_TOKEN))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("[DISCORD BOT] Bot thread started.")