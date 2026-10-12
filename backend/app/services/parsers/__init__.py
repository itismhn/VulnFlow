from pathlib import Path

from app.services.parsers.base import ParsedHost, ParseError, ScanMeta, ScanParser
from app.services.parsers.nessus import NessusParser

PARSERS: list[type[ScanParser]] = [NessusParser]


def get_parser(path: Path) -> ScanParser:
    for parser_cls in PARSERS:
        if parser_cls.detect(path):
            return parser_cls()
    raise ParseError("Unsupported file format. Upload a Nessus v2 (.nessus) export.")


__all__ = ["PARSERS", "ParseError", "ParsedHost", "ScanMeta", "ScanParser", "get_parser"]
