from slackclient import SlackClient
from matterhook import Webhook
from zou.app import config


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
