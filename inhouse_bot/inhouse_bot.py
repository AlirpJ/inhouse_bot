import logging
import os

import discord
from discord.ext import commands


# Defining intents to get full members list
from discord.ext.commands import NoPrivateMessage

from inhouse_bot.orm import session_scope
from inhouse_bot import game_queue

intents = discord.Intents.default()
intents.members = True

# Defining warnings display duration
WARNING_DURATION = 30


class InhouseBot(commands.Bot):
    def __init__(self, **options):
        super().__init__("!", intents=intents, case_insensitive=True, **options)

        # Importing locally to allow InhouseBot to be imported in the cogs
        from inhouse_bot.cogs.queue_cog import QueueCog
        from inhouse_bot.cogs.admin_cog import AdminCog
        from inhouse_bot.cogs.stats_cog import StatsCog

        self.add_cog(QueueCog(self))
        self.add_cog(AdminCog(self))
        self.add_cog(StatsCog(self))

        # While I hate mixing production and testing code, it is the most convenient solution to test the bot
        if os.environ.get("INHOUSE_BOT_TEST"):
            from tests.test_cog import TestCog

            self.add_cog(TestCog(self))

        self.short_notice_duration = 10
        self.validation_duration = 60

    def run(self, *args, **kwargs):
        super().run(os.environ["INHOUSE_BOT_TOKEN"], *args, **kwargs)

    async def on_ready(self):
        logging.info(f"{self.user.name} has connected to Discord!")

        # We start by reposting all the ongoing queues
        game_queue.cancel_all_ready_checks()
        active_queues = game_queue.get_active_queues()

        for channel_id in active_queues:
            channel = self.get_channel(channel_id)

            if not channel:
                continue

            try:
                await self.cogs["Queue"].send_queue(channel=channel)
            except AttributeError:
                # TODO LOW PRIO Should be logging
                print(f"Could not access channel {channel_id}")

    async def on_command_error(self, ctx, error):
        """
        Custom error command that catches CommandNotFound as well as MissingRequiredArgument for readable feedback
        """
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"Command `{ctx.invoked_with}` not found", delete_after=WARNING_DURATION)

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"Arguments missing. Type `!help {ctx.invoked_with}` for help", delete_after=WARNING_DURATION,
            )

        elif isinstance(error, commands.ConversionError):
            # Conversion errors feedback are handled in my converters
            pass

        elif isinstance(error, NoPrivateMessage):
            await ctx.send(f"This command cannot be used in private messages")

        # This handles errors that happen during a command
        elif isinstance(error, commands.CommandInvokeError):
            og_error = error.original

            if isinstance(og_error, game_queue.PlayerInGame):
                await ctx.send(
                    f"Your last game was not scored and you are not allowed to queue at the moment\n"
                    f"One of the winners can score the game with `!won`, "
                    f"or players can agree to cancel it with `!cancel`"
                )

            elif isinstance(og_error, game_queue.PlayerInReadyCheck):
                await ctx.send(
                    f"A game has already been found for you and you cannot queue before it is accepted or cancelled\n"
                    f"If it is a bug, contact an admin and ask them to use `!admin reset` with your name"
                )

            else:
                print(type(og_error))

                # User-facing error
                await ctx.send(
                    f"{og_error.__class__.__name__}: {og_error}\n" f"Contact server admins for bugs.",
                )

                raise og_error

        else:
            print(type(error))

            # User-facing error
            await ctx.send(f"{error.__class__.__name__}: {error}\n" f"Contact server admins for bugs.",)

            raise error
