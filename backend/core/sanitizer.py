"""
Input Sanitizer — v2 Security Layer

Sanitizes all user-provided data before it enters LLM prompts.
Defends against prompt injection attacks where malicious content
is embedded in CSV column names, cell values, or filenames.

Four defense layers:
1. Length limits — truncate excessively long strings
2. Pattern stripping — remove known injection patterns
3. Character filtering — remove control characters and special tokens
4. Structure validation — ensure output is plain data, not instructions

Usage:
    from core.sanitizer import Sanitizer

    clean_name = Sanitizer.clean_column_name(raw_name)
    clean_values = Sanitizer.clean_sample_values(raw_values)
    clean_text = Sanitizer.clean_text(raw_text)
"""

import re
from typing import Optional


class Sanitizer:
    """Sanitize user-provided data before it enters LLM prompts."""

    # ── Length Limits ────────────────────────────────────────

    MAX_COLUMN_NAME_LENGTH = 100
    MAX_SAMPLE_VALUE_LENGTH = 200
    MAX_TEXT_LENGTH = 500
    MAX_FILENAME_LENGTH = 200

    # ── Injection Patterns ───────────────────────────────────
    # These regex patterns match common prompt injection attempts.
    # Case-insensitive matching.

    INJECTION_PATTERNS = [
        # Direct instruction injection
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"ignore\s+(all\s+)?above\s+instructions?",
        r"disregard\s+(all\s+)?previous",
        r"forget\s+(all\s+)?previous",
        r"override\s+(all\s+)?instructions?",
        r"new\s+instructions?\s*:",
        r"system\s*prompt\s*:",
        r"you\s+are\s+now\s+a",
        r"act\s+as\s+(a\s+)?",
        r"pretend\s+you\s+are",
        r"roleplay\s+as",

        # Prompt framing attempts
        r"<\s*system\s*>",
        r"<\s*/?\s*prompt\s*>",
        r"<\s*/?\s*instruction\s*>",
        r"\[SYSTEM\]",
        r"\[INST\]",
        r"\[/INST\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"###\s*(System|Human|Assistant|User)\s*:",

        # Output manipulation
        r"respond\s+with\s+only",
        r"your\s+response\s+must",
        r"output\s+the\s+following",
        r"return\s+the\s+following\s+json",
        r"map\s+everything\s+to",
        r"map\s+all\s+(columns?\s+)?to",
        r"set\s+all\s+confidence\s+to",
        r"set\s+confidence\s+to\s+\d+",

        # Jailbreak-style attempts
        r"DAN\s*mode",
        r"developer\s*mode",
        r"jailbreak",
        r"do\s+anything\s+now",
    ]

    # Compile patterns for performance
    _compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    # ── Control Characters ───────────────────────────────────
    # Characters that should never appear in data going to LLM prompts

    CONTROL_CHAR_PATTERN = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
    )

    # ── Public API ───────────────────────────────────────────

    @classmethod
    def clean_column_name(cls, name: str) -> str:
        """
        Sanitize a column name before using it in an LLM prompt.

        Preserves the semantic meaning of the name while removing
        any potential injection content.
        """
        if not name or not isinstance(name, str):
            return "unnamed_column"

        # Strip whitespace
        cleaned = name.strip()

        # Truncate
        cleaned = cleaned[:cls.MAX_COLUMN_NAME_LENGTH]

        # Remove control characters
        cleaned = cls.CONTROL_CHAR_PATTERN.sub("", cleaned)

        # Strip injection patterns
        cleaned = cls._strip_injection_patterns(cleaned)

        # Remove excessive special characters (keep alphanumeric, spaces, underscores, hyphens, dots)
        cleaned = re.sub(r"[^\w\s\-.\(\)/&,#@]", "", cleaned)

        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # If nothing meaningful remains, use a placeholder
        if not cleaned or len(cleaned) < 1:
            return "unnamed_column"

        return cleaned

    @classmethod
    def clean_sample_values(cls, values: list) -> list:
        """
        Sanitize a list of sample values before using them in an LLM prompt.
        """
        if not values or not isinstance(values, list):
            return []

        cleaned = []
        for val in values[:10]:  # Max 10 samples
            if val is None:
                cleaned.append(None)
                continue

            val_str = str(val).strip()

            # Truncate
            val_str = val_str[:cls.MAX_SAMPLE_VALUE_LENGTH]

            # Remove control characters
            val_str = cls.CONTROL_CHAR_PATTERN.sub("", val_str)

            # Strip injection patterns
            val_str = cls._strip_injection_patterns(val_str)

            # If the cleaned value is suspiciously different from the original,
            # replace with a placeholder to avoid leaking partial injections
            original_len = len(str(val).strip()[:cls.MAX_SAMPLE_VALUE_LENGTH])
            if original_len > 20 and len(val_str) < original_len * 0.5:
                val_str = "[value filtered]"

            cleaned.append(val_str if val_str else None)

        return cleaned

    @classmethod
    def clean_text(cls, text: str, max_length: int = None) -> str:
        """
        General-purpose text sanitizer for any string going into an LLM prompt.
        """
        if not text or not isinstance(text, str):
            return ""

        max_len = max_length or cls.MAX_TEXT_LENGTH
        cleaned = text.strip()[:max_len]

        # Remove control characters
        cleaned = cls.CONTROL_CHAR_PATTERN.sub("", cleaned)

        # Strip injection patterns
        cleaned = cls._strip_injection_patterns(cleaned)

        return cleaned.strip()

    @classmethod
    def clean_filename(cls, filename: str) -> str:
        """Sanitize a filename."""
        if not filename or not isinstance(filename, str):
            return "unnamed_file"

        cleaned = filename.strip()[:cls.MAX_FILENAME_LENGTH]
        cleaned = cls.CONTROL_CHAR_PATTERN.sub("", cleaned)
        cleaned = cls._strip_injection_patterns(cleaned)

        # Filenames: keep only safe characters
        cleaned = re.sub(r"[^\w\s\-.\(\)]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned if cleaned else "unnamed_file"

    @classmethod
    def is_suspicious(cls, text: str) -> bool:
        """
        Check if a string contains potential injection patterns.
        Returns True if suspicious, False if clean.

        Useful for logging/auditing without modifying the text.
        """
        if not text or not isinstance(text, str):
            return False

        for pattern in cls._compiled_patterns:
            if pattern.search(text):
                return True

        return False

    # ── Output Validation ────────────────────────────────────

    @classmethod
    def validate_llm_mapping_output(cls, result: list) -> list:
        """
        Validate and sanitize the structured output from the LLM.

        Ensures the LLM's mapping response hasn't been manipulated:
        - Confidence must be 0-99
        - Target field names must be reasonable
        - Transform types must be from the allowed list
        - No injection content in reasoning strings
        """
        ALLOWED_TRANSFORMS = {
            None, "cast_integer", "cast_float", "parse_date", "cast_boolean",
            "lowercase", "uppercase", "titlecase", "phone_normalize",
            "email_normalize", "currency_normalize", "zip_pad",
            "split_name", "split_address",
        }

        if not isinstance(result, list):
            return []

        validated = []
        for item in result:
            if not isinstance(item, dict):
                continue

            # Validate confidence range
            confidence = item.get("confidence", 0)
            if not isinstance(confidence, (int, float)):
                confidence = 0
            confidence = max(0, min(99, int(confidence)))

            # Validate transform type
            transform_type = item.get("transform_type")
            if transform_type not in ALLOWED_TRANSFORMS:
                transform_type = None

            # Validate target field (must be a reasonable identifier)
            target_field = item.get("target_field")
            if target_field is not None:
                target_field = str(target_field).strip()
                # Target field should be a simple identifier
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", target_field):
                    target_field = None
                elif len(target_field) > 50:
                    target_field = None

            # Sanitize reasoning
            reasoning = cls.clean_text(
                item.get("reasoning", ""),
                max_length=300
            )

            validated.append({
                "source": str(item.get("source", ""))[:100],
                "target_field": target_field,
                "confidence": confidence,
                "transform_type": transform_type,
                "reasoning": reasoning,
            })

        return validated

    # ── Private Helpers ──────────────────────────────────────

    @classmethod
    def _strip_injection_patterns(cls, text: str) -> str:
        """Remove all detected injection patterns from text."""
        cleaned = text
        for pattern in cls._compiled_patterns:
            cleaned = pattern.sub("", cleaned)
        return cleaned
