"""
Автоматическое исправление кодировки для Windows
Решает проблему с отображением русских символов и emoji
"""

import sys
import os
import logging

logger = logging.getLogger(__name__)


def fix_windows_encoding():
    """
    Автоматически исправляет кодировку консоли для Windows

    Решает проблемы:
    - Русские символы отображаются как ╨г╤Б╤В╨░╨╜╨╛╨▓╨║╨░
    - Emoji не отображаются корректно

    Returns:
        bool: True если кодировка была исправлена, False иначе
    """
    if os.name != 'nt':
        # Не Windows - кодировка обычно нормальная
        return False

    try:
        # Проверяем текущую кодировку
        current_encoding = sys.stdout.encoding
        logger.debug(f"Текущая кодировка: {current_encoding}")

        if current_encoding and current_encoding.lower() in ['utf-8', 'utf8']:
            logger.debug("UTF-8 уже установлена")
            return False

        # Попытка установить UTF-8 через chcp (Windows)
        import subprocess
        try:
            # Выполняем chcp 65001 (UTF-8)
            result = subprocess.run(
                ['chcp', '65001'],
                capture_output=True,
                text=True,
                shell=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info("Кодировка консоли изменена на UTF-8 (chcp 65001)")

                # Переконфигурируем stdout/stderr
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                    sys.stderr.reconfigure(encoding='utf-8')
                    logger.info("stdout/stderr переконфигурированы на UTF-8")

                return True
            else:
                logger.warning(f"Не удалось изменить кодировку: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout при попытке изменить кодировку")
            return False
        except FileNotFoundError:
            logger.warning("Команда chcp не найдена")
            return False

    except Exception as e:
        logger.error(f"Ошибка при исправлении кодировки: {e}")
        return False


def ensure_utf8():
    """
    Гарантирует UTF-8 кодировку для вывода

    Использует несколько методов:
    1. Попытка chcp 65001 (Windows)
    2. Reconfigure stdout/stderr (Python 3.7+)
    3. Установка переменных окружения

    Если не удается - рекомендует альтернативы
    """
    if os.name != 'nt':
        # Linux/Mac - обычно UTF-8 по умолчанию
        return

    # Попытка автоисправления
    fixed = fix_windows_encoding()

    if not fixed:
        # Если не получилось автоматически
        current_encoding = sys.stdout.encoding or 'unknown'

        if current_encoding.lower() not in ['utf-8', 'utf8']:
            print("\n" + "=" * 70)
            print("[WARN] Обнаружена проблема с кодировкой консоли!")
            print(f"[INFO] Текущая кодировка: {current_encoding}")
            print("\n[FIX] Решения:")
            print("  1. Выполните в PowerShell: chcp 65001")
            print("  2. Используйте Windows Terminal вместо cmd.exe")
            print("  3. Создайте .env и добавьте: USE_EMOJI=false")
            print("  4. Используйте Docker: docker-compose up -d")
            print("=" * 70 + "\n")


def safe_print(text: str, encoding: str = 'utf-8', errors: str = 'replace'):
    """
    Безопасный вывод текста с обработкой ошибок кодировки

    Args:
        text: Текст для вывода
        encoding: Целевая кодировка (по умолчанию utf-8)
        errors: Режим обработки ошибок ('replace', 'ignore', 'strict')
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Если не получается вывести в UTF-8, пытаемся с заменой
        try:
            # Кодируем в bytes с заменой проблемных символов
            encoded = text.encode(sys.stdout.encoding or 'utf-8', errors=errors)
            # Декодируем обратно
            decoded = encoded.decode(sys.stdout.encoding or 'utf-8', errors=errors)
            print(decoded)
        except Exception as e:
            # Последняя попытка - ASCII с заменой
            ascii_text = text.encode('ascii', errors='replace').decode('ascii')
            print(ascii_text)
            logger.debug(f"Fallback to ASCII due to: {e}")


def get_safe_encoding() -> str:
    """
    Возвращает безопасную кодировку для текущей системы

    Returns:
        Название кодировки ('utf-8', 'cp1251', 'ascii')
    """
    if os.name == 'nt':
        # Windows
        encoding = sys.stdout.encoding or 'cp1251'
        if encoding.lower() not in ['utf-8', 'utf8']:
            return 'cp1251'  # Fallback для старых Windows консолей

    return 'utf-8'


# Автоматическое исправление при импорте модуля
if __name__ != "__main__":
    ensure_utf8()
