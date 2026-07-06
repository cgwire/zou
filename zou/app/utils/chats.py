from zou.app import config
import asyncio
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
                from slack import WebClient as SlackClient

                client = SlackClient(token=token)
                blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message},
                    }
                ]
                client.chat_postMessage(
                    channel=f"@{userid}",
                    blocks=blocks,
                    as_user=True,
                )
            except Exception:
                logger.error(
                    "Exception when sending a Slack notification:",
                    exc_info=True,
                )
        else:
            logger.warning("The userid of Slack user is not defined.")
    else:
        logger.warning(
            "The token of Slack for sending notifications is not defined."
        )


def send_to_mattermost(webhook, userid, message):
    if webhook:
        if userid:
            try:
                import requests

                # A Mattermost incoming webhook is a plain POST of a
                # JSON payload on the webhook URL.
                payload = {
                    "text": message["message"],
                    "channel": f"@{userid}",
                    "username": f"Kitsu - {message['project_name']}",
                    "icon_url": (
                        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
                        "/img/kitsu.b07d6464.png"
                    ),
                }
                response = requests.post(webhook, json=payload, timeout=30)
                response.raise_for_status()
            except Exception:
                logger.error(
                    "Exception when sending a Mattermost notification:",
                    exc_info=True,
                )
        else:
            logger.warning("The userid of Mattermost user is not defined.")
    else:
        logger.warning(
            "The webhook of Mattermost for sending notifications is not defined."
        )


def send_to_discord(token, userid, message):
    from discord import (
        Client as DiscordClient,
        Intents as DiscordIntents,
        Embed as DiscordEmbed,
    )

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
                logger.info(f"User {userid} not found by Discord bot")

            await client.close()

        await client.start(token)

    if token:
        if userid:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    send_to_discord_async(token, userid, message)
                )
            except Exception:
                logger.error(
                    "Exception when sending a Discord notification:",
                    exc_info=True,
                )
            finally:
                if loop:
                    loop.close()
        else:
            logger.warning("The userid of Discord user is not defined.")
    else:
        logger.warning(
            "The token of the Discord bot for sending notifications is not defined."
        )
