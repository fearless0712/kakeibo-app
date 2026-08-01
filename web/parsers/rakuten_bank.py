from .base import UnsupportedParser


class RakutenBankParser(UnsupportedParser):
    source_key = "rakuten_bank"
    display_name = "楽天銀行"
    import_name = "楽天銀行CSV"
    detection_headers = ("入出金(円)", "取引後残高(円)", "入出金内容")

    def parse(self, file):
        return super().parse(file)
