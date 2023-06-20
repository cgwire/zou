from slack import WebClient as SlackClient
from matterhook import Webhook
from discord import (
    Client as DiscordClient,
    Intents as DiscordIntents,
    Embed as DiscordEmbed,
)
from zou.app import config
import asyncio
import traceback
import logging

logger = logging.getLogger(__name__)
loghandler = logging.StreamHandler()
loghandler.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
)
loghandler.setFormatter(formatter)
logger.addHandler(loghandler)


def send_to_slack(token, userid, message):
    if token:
        if userid:
            try:
                client = SlackClient(token=token)
                blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message},
                    }
                ]
                client.chat_postMessage(
                    channel="@%s" % userid,
                    blocks=blocks,
                    as_user=True,
                )
            except Exception:
                logger.info("Exception when sending a Slack notification:")
                logger.info(traceback.format_exc())
        else:
            logger.info("The userid of Slack user is not defined.")
    else:
        logger.info(
            "The token of Slack for sending notifications is not defined."
        )


def send_to_mattermost(webhook, userid, message):
    if webhook:
        if userid:
            try:
                arg = webhook.split("/")
                server = "%s%s//%s" % (arg[0], arg[1], arg[2])
                hook = arg[4]

                # mandatory parameters are url and your webhook API key
                mwh = Webhook(server, hook)
                mwh.username = "Kitsu - %s" % (message["project_name"])
                mwh.icon_url = "%s://%s/img/kitsu.b07d6464.png" % (
                    config.DOMAIN_PROTOCOL,
                    config.DOMAIN_NAME,
                )

                # send a message to the API_KEY's channel
                mwh.send(message["message"], channel="@%s" % userid)

            except Exception:
                logger.info(
                    "Exception when sending a Mattermost notification:"
                )
                logger.info(traceback.format_exc())
        else:
            logger.info("The userid of Mattermost user is not defined.")
    else:
        logger.info(
            "The webhook of Mattermost for sending notifications is not defined."
        )


def send_to_discord(token, userid, message):
    async def send_to_discord_async(token, userid, message):
        intents = DiscordIntents.default()
        intents.members = True
        client = DiscordClient(intents=intents)

        @client.event
        async def on_ready(userid=userid, message=message):
            user_found = False
            for user in client.get_all_members():
                if not user.bot and (
                    (user.discriminator == "0" and user.name == userid)
                    or (f"{user.name}#{user.discriminator}" == userid)
                ):
                    embed = DiscordEmbed()
                    embed.description = message
                    await user.send(embed=embed)
                    user_found = True
                    break
            if not user_found:
                logger.info("User %s not found by Discord bot" % userid)

            await client.close()

        await client.start(token)

    if token:
        if userid:
            try:
                asyncio.set_event_loop(asyncio.new_event_loop())
                loop = asyncio.get_event_loop()
                loop.run_until_complete(
                    send_to_discord_async(token, userid, message)
                )
            except Exception:
                logger.info("Exception when sending a Discord notification:")
                logger.info(traceback.format_exc())
            finally:
                if loop:
                    loop.close()
        else:
            logger.info("The userid of Discord user is not defined.")
    else:
        logger.info(
            "The token of the Discord bot for sending notifications is not defined."
        )
