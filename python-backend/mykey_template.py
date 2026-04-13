# LLM API Configuration Template
# Rename this file to mykey.py and fill in your keys

# OpenAI-compatible API (e.g. DeepSeek, Moonshot, etc.)
oai_config = {
    'apikey': 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'apibase': "https://api.example.com/v1",
    'model': "gpt-4-turbo"
}

# Another OpenAI-compatible config
model_config = {
    'apikey': 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'apibase': "https://api.example.com/v1",
    'model': "kimi-k2.5"
}

# Claude API Config
claude_config = {
    'apikey': 'sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    'apibase': 'https://api.anthropic.com',
    'model': 'claude-3-opus-20240229'
}

# Sider Config (Optional)
# sider_cookie = 'token=Bearer%20...'

# Proxy Configuration (Optional)
# proxy = "http://127.0.0.1:7890"
