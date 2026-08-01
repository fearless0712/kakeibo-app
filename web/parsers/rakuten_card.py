from .base import UnsupportedParser


class RakutenCardParser(UnsupportedParser):
    source_key = "rakuten_card"
    display_name = "楽天カード"
    import_name = "楽天カードCSV"
    detection_headers = ("利用日", "利用店名・商品名", "利用金額")

    def parse(self, file):
        return super().parse(file)
