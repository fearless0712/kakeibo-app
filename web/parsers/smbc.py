from .base import UnsupportedParser


class SmbcParser(UnsupportedParser):
    source_key = "smbc"
    display_name = "三井住友銀行"
    import_name = "三井住友銀行CSV"
    detection_headers = ("年月日", "お支払金額", "お預り金額")

    def parse(self, file):
        return super().parse(file)
