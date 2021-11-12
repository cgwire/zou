from slackclient import SlackClient
from matterhook import Webhook


def send_to_slack(app_token, userid, message):
    client = SlackClient(token=app_token)
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": message}}]
    client.api_call(
        "chat.postMessage", channel="@%s" % userid, blocks=blocks, as_user=True
    )

def send_to_mattermost(webhook, userid, message):
    
    arg = webhook.split('/')
    server = '%s%s//%s' % (arg[0], arg[1], arg[2])
    hook = arg[4]
    # mandatory parameters are url and your webhook API key
    mwh = Webhook(server, hook)

    # send a message to the API_KEY's channel
    mwh.send(message, channel='@%s' % userid)