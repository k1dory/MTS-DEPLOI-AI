"""
Unit тесты для encoding_fix утилит
Тестирование исправления кодировки Windows
"""

import pytest
import sys
import os
from src.mcp_server.utils.encoding_fix import (
    get_safe_encoding,
    safe_print
)


class TestEncodingFix:
    """Тесты утилит исправления кодировки"""

    def test_get_safe_encoding(self):
        """Тест определения безопасной кодировки"""
        encoding = get_safe_encoding()
        # Должна быть либо utf-8, либо cp1251 (Windows)
        assert encoding in ['utf-8', 'cp1251'], f"Unexpected encoding: {encoding}"

    def test_get_safe_encoding_returns_string(self):
        """Тест что функция возвращает строку"""
        encoding = get_safe_encoding()
        assert isinstance(encoding, str)
        assert len(encoding) > 0

    def test_safe_print_basic(self, capsys):
        """Тест базового безопасного вывода"""
        test_text = "Test output"
        safe_print(test_text)

        captured = capsys.readouterr()
        assert test_text in captured.out

    def test_safe_print_russian(self, capsys):
        """Тест вывода русского текста"""
        test_text = "Тестовый вывод"
        try:
            safe_print(test_text)
            captured = capsys.readouterr()
            # Если получилось вывести - отлично
            assert len(captured.out) > 0
        except UnicodeEncodeError:
            # Если не получилось - safe_print должен обработать
            pytest.fail("safe_print не обработал UnicodeEncodeError")

    def test_safe_print_emoji(self, capsys):
        """Тест вывода emoji"""
        test_text = "Test ✅ 🚀 ❌"
        try:
            safe_print(test_text)
            captured = capsys.readouterr()
            assert len(captured.out) > 0
        except UnicodeEncodeError:
            pytest.fail("safe_print не обработал emoji")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
