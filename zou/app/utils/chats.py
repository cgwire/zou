from slackclient import SlackClient
from matterhook import Webhook
from discord import (
    Client as DiscordClient,
    Intents as DiscordIntents,
    Embed as DiscordEmbed,
)
from zou.app import config
import asyncio


def send_to_slack(app_token, userid, message):
    client = SlackClient(token=app_token)
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": message}}]
    client.api_call(
        "chat.postMessage", channel="@%s" % userid, blocks=blocks, as_user=True
    )


def send_to_mattermost(webhook, userid, message):
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


def send_to_discord(current_app, token, userid, message):
    async def send_to_discord_async(current_app, token, userid, message):
        intents = DiscordIntents.default()
        intents.members = True
        client = DiscordClient(intents=intents)

        @client.event
        async def on_ready(
            current_app=current_app, userid=userid, message=message
        ):
            user_found = False
            for user in client.get_all_members():
                if (
                    "%s#%s" % (user.name, user.discriminator) == userid
                    and not user.bot
                ):
                    embed = DiscordEmbed()
                    embed.description = message
                    await user.send(embed=embed)
                    user_found = True
                    break
            if not user_found:
                current_app.logger.info(
                    "User %s not found by discord bot" % userid
                )

            await client.close()

        await client.start(token)

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        send_to_discord_async(current_app, token, userid, message)
    )
    loop.close()
