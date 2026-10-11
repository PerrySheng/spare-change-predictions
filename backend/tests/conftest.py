"""Tests never inherit local provider credentials or create real wallets."""
import os
import pytest

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'


@pytest.fixture(autouse=True)
def isolated_provider_configuration(monkeypatch):
    for key in ('XRPL_WALLET_KEY', 'CONTEXT_DEV_API_KEY', 'GEMINI_API_KEY',
                'GEMINI_API_SECRET', 'GEMINI_ACCOUNT', 'ANTHROPIC_API_KEY',
                'GOOGLE_AI_API_KEY', 'OPENAI_API_KEY', 'SWARM_PROVIDER',
                'APP_SESSION_SECRET', 'DEMO_ACCESS_CODE','APP_PUBLIC_DEMO'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('APP_ENV', 'development')
