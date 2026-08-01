"""利用可能な金融機関Parserの登録と自動判定。"""

from .generic import GenericParser
from .jpbank import JpbankParser
from .mufg import MufgParser
from .rakuten_bank import RakutenBankParser
from .rakuten_card import RakutenCardParser
from .sbi import SbiParser
from .smbc import SmbcParser
from .sony import SonyParser


PARSER_CLASSES = (
    SonyParser,
    RakutenBankParser,
    SmbcParser,
    MufgParser,
    JpbankParser,
    SbiParser,
    RakutenCardParser,
    GenericParser,
)
PARSERS = {parser.source_key: parser for parser in PARSER_CLASSES}


def detect_parser(data):
    """CSV内容から最も一致度が高いParserクラスを返します。"""
    scored = []
    for parser in PARSER_CLASSES:
        try:
            scored.append((parser.detection_score(data), parser))
        except ValueError:
            return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 2:
        return None
    # 同点の場合は誤判定を避け、ユーザー選択へ回します。
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]
