"""Граница доверенных модельных сервисов задаётся оператором, не префиксом IP."""
import ipaddress
from urllib.parse import urlsplit
from .config import settings
from .openai_asr import ProviderError


def trusted_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {'localhost', 'host.docker.internal', *settings().trusted_ai_hosts}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or any(address in ipaddress.ip_network(network)
            for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
            if address.version == ipaddress.ip_network(network).version)
    except ValueError:
        return False


def llm_is_external():
    s = settings()
    return s.llm_provider == 'openai' or s.llm_is_cloud or (
        s.llm_provider in ('ollama', 'openai_compatible') and not trusted_url(s.llm_url))


def require_trusted_asr():
    s = settings()
    if s.asr_provider == 'faster_whisper':
        return
    if s.asr_provider == 'self_hosted' and trusted_url(s.asr_url):
        return
    raise ProviderError('Исходное аудио разрешено только доверенному локальному ASR. Настройте faster_whisper или self_hosted в приватном контуре.')
