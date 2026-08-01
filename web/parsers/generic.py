from .base import UnsupportedParser


class GenericParser(UnsupportedParser):
    source_key = "generic"
    display_name = "その他（汎用CSV）"
    import_name = "汎用CSV"
    detection_headers = ()

    def parse(self, file):
        return super().parse(file)
