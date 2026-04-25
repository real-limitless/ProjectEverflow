# LLM Configuration Guide

This application supports multiple Large Language Models (LLMs) through a flexible configuration system. API keys and sensitive information are stored in environment variables that are not committed to version control.

## Setup

### 1. Environment Variables

1. Copy the example environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `backend/.env` and add your API keys:
   ```bash
   # OpenAI Configuration
   OPENAI_API_KEY=your_actual_openai_api_key_here
   OPENAI_BASE_URL=https://api.openai.com/v1

   # Anthropic Configuration
   ANTHROPIC_API_KEY=your_actual_anthropic_api_key_here
   ANTHROPIC_BASE_URL=https://api.anthropic.com

   # Ollama Configuration (if using custom setup)
   OLLAMA_BASE_URL=http://localhost:11434
   ```

### 2. LLM Configuration

The `backend/llm_config.json` file contains the list of available LLMs. Each LLM has the following properties:

- `id`: Unique identifier
- `name`: Display name
- `provider`: LLM provider (ollama, openai, anthropic, etc.)
- `model`: Model identifier
- `base_url`: Custom base URL (optional)
- `api_key_env`: Environment variable name for API key (optional for local models)
- `description`: Human-readable description
- `max_tokens`: Maximum tokens for responses
- `temperature`: Creativity/randomness setting
- `enabled`: Whether this LLM is available for selection

### 3. Adding New LLMs

To add a new LLM provider:

1. Add the configuration to `llm_config.json`
2. Add the required environment variables to `.env.example` and `.env`
3. Update the `LLMConfig.beeai_model_name` property in `llm_config.py` if needed

### 4. API Endpoints

- `GET /api/llm-config/available_llms/`: Get list of available LLMs with their status

### 5. Frontend Integration

The frontend can fetch available LLMs using:
```typescript
const { data } = await getAvailableLLMs();
// data.llms contains the list of available LLMs
// data.default_llm contains the default LLM ID
```

## Supported Providers

- **Ollama**: Local LLM models (no API key required)
- **OpenAI**: GPT models via OpenAI API
- **Anthropic**: Claude models via Anthropic API

## Security Notes

- Never commit the `.env` file to version control
- API keys should only be accessible to authorized users
- Use strong, unique API keys for each service
- Rotate API keys regularly

## Troubleshooting

1. **LLM not available**: Check that the required environment variables are set
2. **API errors**: Verify API keys are correct and have sufficient permissions
3. **Model not found**: Ensure the model name matches the provider's documentation
4. **Connection issues**: Check network connectivity and base URLs