import logging
from zou.app import config

if config.LOGS_MODE == "ovh":
    try:
        from pygelf import GelfTcpHandler, gelf
    except ModuleNotFoundError:
        print("pygelf module not found.")


def configure_logs_ovh(app):
    if config.LOGS_MODE == "ovh":

        class GelfOVHHandler(GelfTcpHandler):
            """
            Class to adapt OVH Log management platform
            """

            def __init__(self, ovh_token, **kwargs):
                """
                OVH TCP Handler
                :param ovh_token: OVH API Token
                """
                self.ovh_token = ovh_token
                GelfTcpHandler.__init__(self, **kwargs)

            def convert_record_to_gelf(self, record):
                l = gelf.make(
                    record,
                    self.domain,
                    self.debug,
                    self.version,
                    self.additional_fields,
                    self.include_extra_fields,
                )
                l.update({"_X-OVH-TOKEN": self.ovh_token})
                return gelf.pack(l, self.compress, self.json_default)

        graylogHandler = GelfOVHHandler(
            host=app.config["LOGS_HOST"],
            port=app.config["LOGS_PORT"],
            ovh_token=app.config["LOGS_TOKEN"],
        )
        graylogHandler.setLevel(logging.ERROR)
        app.logger.addHandler(graylogHandler)
