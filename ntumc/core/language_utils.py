"""
Language utilities for the NTUMC WordNet tagging system.

This module provides functions for language code conversion, language-specific text processing.
"""
from typing import Optional, Dict, List, Set


# Language code mappings
ISO_TO_BCP: Dict[str, str] = {
    "ces": "cs",  # Czech
    "eng": "en",  # English
    "jap": "ja",  # Japanese
    "zsm": "zh",  # Mandarin Chinese
    "vie": "vi",  # Vietnamese
}

BCP_TO_ISO: Dict[str, str] = {v: k for k, v in ISO_TO_BCP.items()}

# Original language codes used in the system
SUPPORTED_LANGUAGES: Set[str] = {"ces", "eng", "jap", "zsm", "vie"}


def is_supported_language(lang_code: str) -> bool:
    """
    Check if a language code is supported by the system.

    Args:
        lang_code: A language code (ISO or BCP format)

    Returns:
        bool: True if the language is supported, False otherwise
    """
    if lang_code in SUPPORTED_LANGUAGES:
        return True
    if lang_code in BCP_TO_ISO and BCP_TO_ISO[lang_code] in SUPPORTED_LANGUAGES:
        return True
    return False


def convert_to_iso(lang_code: str) -> str:
    """
    Convert a language code to ISO 639-3 format.

    Args:
        lang_code: A language code (ISO or BCP format)

    Returns:
        str: The language code in ISO 639-3 format
    
    Raises:
        ValueError: If the language code is not supported
    """
    if lang_code in SUPPORTED_LANGUAGES:
        return lang_code
    if lang_code in BCP_TO_ISO and BCP_TO_ISO[lang_code] in SUPPORTED_LANGUAGES:
        return BCP_TO_ISO[lang_code]
    raise ValueError(f"Unsupported language code: {lang_code}")


def convert_to_bcp(lang_code: str) -> str:
    """
    Convert a language code to BCP 47 format.

    Args:
        lang_code: A language code (ISO or BCP format)

    Returns:
        str: The language code in BCP 47 format
    
    Raises:
        ValueError: If the language code is not supported
    """
    if lang_code in ISO_TO_BCP:
        return ISO_TO_BCP[lang_code]
    if lang_code in BCP_TO_ISO.values():
        return {v: k for k, v in ISO_TO_BCP.items()}[lang_code]
    raise ValueError(f"Unsupported language code: {lang_code}")
