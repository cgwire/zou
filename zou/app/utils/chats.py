import slack


def send_to_slack(app_token, userid, message):
    try:
        client = slack.WebClient(app_token)
        blocks = [{
            "type": "section", "text": {"type": "mrkdwn", "text": message}
        }]
        client.chat_postMessage(
            channel="@%s" % userid,
            blocks=blocks
        )
    except Exception:
        from flask import current_app
        current_app.logger.error(
            "An error occured while posting on Slack",
            exc_info=1
        )
    return True
