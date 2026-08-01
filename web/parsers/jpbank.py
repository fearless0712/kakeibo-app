from .base import UnsupportedParser


class JpbankParser(UnsupportedParser):
    source_key = "jpbank"
    display_name = "ゆうちょ銀行"
    import_name = "ゆうちょ銀行CSV"
    detection_headers = ("取扱日", "受入金額", "払出金額")

    def parse(self, file):
        return super().parse(file)
