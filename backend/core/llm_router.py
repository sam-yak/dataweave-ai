"""
LLM Router — Intelligent routing between AI providers.

Routes mapping requests to the cheapest effective option:
1. Pattern cache (free) — checked by Pattern Agent before this is called
2. Claude 3.5 Sonnet (primary) — best at structured data reasoning
3. Gemini 2.0 Flash (fallback) — free tier, used when Claude fails or for simple tasks

Also handles response caching to avoid paying for the same mapping twice.

v2: Updated prompt to support split transforms (split_name, split_address)
    and new transforms (currency_normalize, zip_pad).
"""

import os
import json
import hashlib
from typing import Optional
import anthropic
import google.generativeai as genai


class LLMRouter:
    """Route mapping requests to the best LLM provider."""

    def __init__(self):
        # Initialize Claude client
        self.claude_client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY", "")
        )

        # Initialize Gemini client
        genai.configure(api_key=os.getenv("GOOGLE_AI_API_KEY", ""))
        self.gemini_model = genai.GenerativeModel("gemini-2.0-flash")

        # In-memory response cache (hash of input → response)
        # This resets when the server restarts, but that's fine for MVP
        self._cache: dict[str, dict] = {}

        # Cost tracking
        self.total_claude_calls = 0
        self.total_gemini_calls = 0
        self.total_cache_hits = 0
        self.total_cost_usd = 0.0

    def map_columns(self, unmapped_columns: list[dict], target_schema: dict,
                    already_mapped: list[dict] = None) -> list[dict]:
        """
        Ask an LLM to map source columns to target schema fields.

        Args:
            unmapped_columns: List of column profiles that Pattern Agent couldn't match
                [{"name": "Cust Email", "normalized": "custemail", "detected_type": "email",
                  "sample_values": ["john@test.com", "jane@test.com"], "null_count": 2, ...}]
            target_schema: The target schema definition with fields
            already_mapped: Columns already mapped by Pattern Agent (to avoid duplicates)

        Returns:
            List of mapping proposals:
            [{"source": "Cust Email", "target_field": "email", "confidence": 92,
              "transform_type": null, "reasoning": "Column contains email addresses matching email field"}]
        """
        if not unmapped_columns:
            return []

        # Check cache first
        cache_key = self._make_cache_key(unmapped_columns, target_schema)
        if cache_key in self._cache:
            self.total_cache_hits += 1
            return self._cache[cache_key]

        # Build the prompt
        prompt = self._build_mapping_prompt(unmapped_columns, target_schema, already_mapped)

        # Try Claude first, fall back to Gemini
        result = self._call_claude(prompt)
        if result is None:
            result = self._call_gemini(prompt)
        if result is None:
            # Both failed — return unmapped with zero confidence
            result = [
                {
                    "source": col["name"],
                    "target_field": None,
                    "confidence": 0,
                    "transform_type": None,
                    "reasoning": "LLM unavailable — manual mapping required",
                }
                for col in unmapped_columns
            ]

        # Cache the result
        self._cache[cache_key] = result

        return result

    def _build_mapping_prompt(self, columns: list[dict], target_schema: dict,
                              already_mapped: list[dict] = None) -> str:
        """Build the mapping prompt for the LLM."""

        # Format target schema fields
        target_fields = []
        for field in target_schema.get("fields", []):
            field_desc = f"- {field['name']} ({field['type']}"
            if field.get("required"):
                field_desc += ", required"
            if field.get("format"):
                field_desc += f", format: {field['format']}"
            field_desc += ")"
            target_fields.append(field_desc)

        # Format already mapped columns (so LLM doesn't suggest duplicates)
        mapped_info = ""
        if already_mapped:
            mapped_list = [f"  '{m['source']}' → '{m['target_field']}'" for m in already_mapped]
            mapped_info = f"""
The following columns have already been mapped (do NOT suggest these target fields again unless they truly need multiple source columns):
{chr(10).join(mapped_list)}
"""

        # Format unmapped columns with their profiles
        column_profiles = []
        for col in columns:
            samples = col.get("sample_values", [])
            samples_str = ", ".join(f'"{s}"' for s in samples[:5]) if samples else "no samples"

            profile = f"""  Column: "{col['name']}"
    Detected type: {col.get('detected_type', 'unknown')}
    Sample values: [{samples_str}]
    Null count: {col.get('null_count', 0)} / {col.get('total_count', 0)}
    Unique values: {col.get('unique_count', 0)}"""
            column_profiles.append(profile)

        prompt = f"""You are a data mapping expert. Your job is to map source data columns to a target schema.

TARGET SCHEMA FIELDS:
{chr(10).join(target_fields)}
{mapped_info}
SOURCE COLUMNS TO MAP:
{chr(10).join(column_profiles)}

For each source column, determine the best matching target field.

RULES:
1. If a column clearly matches a target field, map it with high confidence (80-99).
2. If a column partially matches or requires transformation, map it with medium confidence (50-79).
3. If a column has no reasonable match in the target schema, set target_field to null with confidence 0.
4. Consider the sample values and data types, not just the column name.
5. If a transformation is needed (e.g., date format conversion, type casting), specify the transform_type.
6. Do NOT map multiple source columns to the same target field unless absolutely necessary.

CRITICAL — SPLIT TRANSFORMS:
7. If a source column contains FULL NAMES (e.g., "John Doe", "Jane Smith") and the target schema has separate first_name and last_name fields, you MUST use "split_name" as the transform_type. Set target_field to "first_name" (the primary target). The transform agent will automatically produce both first_name and last_name from the split.
8. If a source column contains FULL ADDRESSES (e.g., "123 Main St, Springfield, IL 62704") and the target schema has separate address, city, state, zip_code fields, use "split_address" as the transform_type. Set target_field to "address" (the primary target).
9. When you propose a split transform, do NOT also create separate mappings for the secondary output fields (e.g., don't create a separate mapping for last_name if you already proposed split_name on the Name column — the split handles it).

TRANSFORM TYPES (use when needed):
- "cast_integer" — convert string to integer
- "cast_float" — convert string to float
- "parse_date" — parse various date formats to ISO 8601
- "cast_boolean" — convert yes/no, true/false, 1/0 to boolean
- "lowercase" — convert to lowercase
- "uppercase" — convert to uppercase
- "titlecase" — convert to title case
- "phone_normalize" — normalize phone number format
- "email_normalize" — lowercase and trim email
- "currency_normalize" — strip currency symbols/commas, convert to number (e.g., "$1,234.56" → 1234.56)
- "zip_pad" — pad zip codes to 5 digits (e.g., "2134" → "02134")
- "split_name" — split full name into first_name + last_name (1-to-2 mapping)
- "split_address" — split full address into address, city, state, zip_code (1-to-4 mapping)
- null — no transformation needed

Respond with ONLY a JSON array, no other text. Each element must have:
- "source": the exact source column name
- "target_field": the target field name (or null if no match). For split transforms, use the PRIMARY target field (e.g., "first_name" for split_name, "address" for split_address).
- "confidence": integer 0-99
- "transform_type": string or null
- "reasoning": one sentence explaining the mapping decision

Example response:
[
  {{"source": "Cust Email", "target_field": "email", "confidence": 92, "transform_type": "email_normalize", "reasoning": "Column contains email addresses matching the email field"}},
  {{"source": "Full Name", "target_field": "first_name", "confidence": 88, "transform_type": "split_name", "reasoning": "Column contains full names that need splitting into first_name and last_name"}},
  {{"source": "Price", "target_field": "amount", "confidence": 85, "transform_type": "currency_normalize", "reasoning": "Column contains currency values like $1,234.56 that need normalization"}},
  {{"source": "Zipcode", "target_field": "zip_code", "confidence": 90, "transform_type": "zip_pad", "reasoning": "Column contains zip codes that may need zero-padding to 5 digits"}},
  {{"source": "Random ID", "target_field": null, "confidence": 0, "transform_type": null, "reasoning": "No matching field in target schema"}}
]"""

        return prompt

    def _call_claude(self, prompt: str) -> Optional[list[dict]]:
        """Call Claude 3.5 Sonnet for mapping."""
        try:
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            # Extract text from response
            text = response.content[0].text.strip()

            # Parse JSON from response (handle markdown code blocks)
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            # Track costs (approximate: ~$0.003 per 1K input tokens, ~$0.015 per 1K output tokens for Sonnet)
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = (input_tokens * 0.003 / 1000) + (output_tokens * 0.015 / 1000)

            self.total_claude_calls += 1
            self.total_cost_usd += cost

            return result

        except json.JSONDecodeError as e:
            print(f"Claude returned invalid JSON: {e}")
            return None
        except anthropic.APIError as e:
            print(f"Claude API error: {e}")
            return None
        except Exception as e:
            print(f"Claude unexpected error: {e}")
            return None

    def _call_gemini(self, prompt: str) -> Optional[list[dict]]:
        """Call Gemini 2.0 Flash as fallback."""
        try:
            response = self.gemini_model.generate_content(prompt)

            # Extract text
            text = response.text.strip()

            # Parse JSON
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            self.total_gemini_calls += 1
            # Gemini Flash is essentially free for our volume

            return result

        except json.JSONDecodeError as e:
            print(f"Gemini returned invalid JSON: {e}")
            return None
        except Exception as e:
            print(f"Gemini error: {e}")
            return None

    def _make_cache_key(self, columns: list[dict], target_schema: dict) -> str:
        """Create a hash key for caching LLM responses."""
        # Build a deterministic string from columns + schema
        cache_input = {
            "columns": [
                {
                    "name": c["name"],
                    "detected_type": c.get("detected_type"),
                    "sample_values": sorted(c.get("sample_values", [])[:3]),
                }
                for c in columns
            ],
            "schema_fields": [f["name"] for f in target_schema.get("fields", [])],
        }
        cache_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()

    def get_stats(self) -> dict:
        """Get usage statistics for cost tracking."""
        total_calls = self.total_claude_calls + self.total_gemini_calls + self.total_cache_hits
        return {
            "total_requests": total_calls,
            "claude_calls": self.total_claude_calls,
            "gemini_calls": self.total_gemini_calls,
            "cache_hits": self.total_cache_hits,
            "cache_hit_rate": round(self.total_cache_hits / total_calls, 2) if total_calls > 0 else 0,
            "estimated_cost_usd": round(self.total_cost_usd, 4),
        }
