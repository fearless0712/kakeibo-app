from .base import UnsupportedParser


class MufgParser(UnsupportedParser):
    source_key = "mufg"
    display_name = "三菱UFJ銀行"
    import_name = "三菱UFJ銀行CSV"
    detection_headers = ("日付", "摘要", "支払金額", "預り金額")

    def parse(self, file):
        return super().parse(file)
