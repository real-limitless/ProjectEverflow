"""
LLM Configuration Management
Handles loading LLM configurations from JSON and environment variables
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for a single LLM"""
    id: str
    name: str
    provider: str
    model: str
    base_url: Optional[str]
    api_key_env: Optional[str]
    description: str
    max_tokens: int
    temperature: float
    enabled: bool

    @property
    def api_key(self) -> Optional[str]:
        """Get the API key from environment variables"""
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None

    @property
    def resolved_base_url(self) -> Optional[str]:
        """Get the resolved base URL from environment variables if needed"""
        if self.base_url and self.base_url.startswith('http'):
            return self.base_url
        elif self.base_url:
            # Treat as environment variable name
            return os.getenv(self.base_url)
        return None

    @property
    def beeai_model_name(self) -> str:
        """Get the model name formatted for BeeAI"""
        provider_lower = self.provider.lower()
        if provider_lower == "ollama":
            return f"ollama:{self.model}"
        elif provider_lower == "openai":
            return f"openai:{self.model}"
        elif provider_lower == "anthropic":
            return f"anthropic:{self.model}"
        elif provider_lower in ["litemaas", "litemaas"]:
            # LiteMaaS might use OpenAI-compatible API
            return f"openai:{self.model}"
        else:
            # For unknown providers, try OpenAI format as fallback
            return f"openai:{self.model}"


class LLMManager:
    """Manages LLM configurations and provides access to enabled LLMs"""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Default to backend/llm_config.json relative to this file
            config_path = Path(__file__).parent.parent / "llm_config.json"

        self.config_path = config_path
        self._configs: Dict[str, LLMConfig] = {}
        self._default_llm: Optional[str] = None
        self._load_config()

    def _load_config(self):
        """Load LLM configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)

            # Load LLM configurations
            for llm_data in data.get('llms', []):
                config = LLMConfig(
                    id=llm_data['id'],
                    name=llm_data['name'],
                    provider=llm_data['provider'],
                    model=llm_data['model'],
                    base_url=llm_data.get('base_url'),
                    api_key_env=llm_data.get('api_key_env'),
                    description=llm_data['description'],
                    max_tokens=llm_data['max_tokens'],
                    temperature=llm_data['temperature'],
                    enabled=llm_data['enabled']
                )
                self._configs[config.id] = config

            # Set default LLM
            self._default_llm = data.get('default_llm')

        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"Error loading LLM config: {e}")
            # Create a basic fallback configuration
            self._create_fallback_config()

    def _create_fallback_config(self):
        """Create a basic fallback configuration if config file is missing"""
        fallback_config = LLMConfig(
            id="ollama-granite",
            name="Ollama Granite (Fallback)",
            provider="ollama",
            model="granite3.3:8b",
            base_url=None,
            api_key_env=None,
            description="Fallback Ollama configuration",
            max_tokens=4096,
            temperature=0.7,
            enabled=True
        )
        self._configs[fallback_config.id] = fallback_config
        self._default_llm = fallback_config.id

    def get_llm_config(self, llm_id: Optional[str] = None) -> LLMConfig:
        """Get LLM configuration by ID, or default if none specified"""
        if llm_id is None:
            llm_id = self._default_llm

        if llm_id and llm_id in self._configs:
            return self._configs[llm_id]

        # Return first enabled LLM as fallback
        for config in self._configs.values():
            if config.enabled:
                return config

        # Ultimate fallback
        return list(self._configs.values())[0] if self._configs else self._create_fallback_config()

    def get_enabled_llms(self) -> List[LLMConfig]:
        """Get all enabled LLM configurations"""
        return [config for config in self._configs.values() if config.enabled]

    def get_all_llms(self) -> List[LLMConfig]:
        """Get all LLM configurations"""
        return list(self._configs.values())

    def is_llm_available(self, llm_id: str) -> bool:
        """Check if an LLM is available (enabled and has required credentials)"""
        if llm_id not in self._configs:
            return False

        config = self._configs[llm_id]
        if not config.enabled:
            return False

        # For providers that need API keys, check if key is available
        if config.api_key_env and not config.api_key:
            return False

        return True


# Global LLM manager instance
llm_manager = LLMManager()


def get_llm_manager() -> LLMManager:
    """Get the global LLM manager instance"""
    return llm_manager