from .base import UnsupportedParser


class SbiParser(UnsupportedParser):
    source_key = "sbi"
    display_name = "住信SBIネット銀行"
    import_name = "住信SBI CSV"
    detection_headers = ("取引日", "入出金金額", "残高")

    def parse(self, file):
        return super().parse(file)
