import json
import yaml
import redis
import logging
from json import JSONDecodeError

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from openai_ratelimiter import TextCompletionLimiter
from openai_ratelimiter.base import Limiter

from ckan.plugins import toolkit as tk
from common import asint


log = logging.getLogger(__name__)


with open(tk.config.get('ckan.openapi.prompt_file', ''), 'r') as f:
    prompt_file_data = f.read()
prompt = yaml.load(prompt_file_data, Loader=yaml.SafeLoader)
redis_url = tk.config.get('ckan.dq_assistant.redis_url')
cache = redis.from_url(redis_url)
cache_ttl = asint(tk.config.get('ckan.dq_assistant.redis_cache_ttl_days', 0)) * 24 * 60 * 60


messages = [(message.get('role', 'system'), message.get('content', '')) for message in prompt.get('messages', [])]
messages.extend([
    MessagesPlaceholder('data', optional=False),
    MessagesPlaceholder('data_dict', optional=True),
    MessagesPlaceholder('xloader_report', optional=True)
])

messages_tpl = ChatPromptTemplate(messages)
model_name = tk.config.get('ckan.openapi.model', "gpt-4o")
rpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.rpm_limit_per_user', 3))
tpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.tpm_limit_per_user', 3000))
max_tokens = asint(tk.config.get('ckan.openapi.max_tokens', 512))
client = ChatOpenAI(
    api_key=tk.config.get('ckan.openapi.api_key'),
    timeout=asint(tk.config.get('ckan.openapi.timeout', 60)),
    model=model_name,
    max_tokens=max_tokens,
    temperature=float(tk.config.get('ckan.openapi.temperature', 0.1)),
    top_p=asint(tk.config.get('ckan.openapi.top_p', 1)),
    frequency_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
    presence_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
    disable_streaming=True,
)


class AdvancedLimiter(Limiter):
    def __init__(self, user_id, model_name, max_calls, max_tokens, period, tokens, redis):
        key = "{}_{}".format(user_id, model_name)
        self.current_calls = 0
        self.current_tokens = 0
        super().__init__(model_name=key, max_calls=max_calls, max_tokens=max_tokens, period=period, tokens=tokens, redis=redis)

    def __enter__(self):
        super().__enter__()
        return self

    def rpm_left(self):
        return self.max_calls - self.current_calls

    def tpm_left(self):
        return self.max_tokens - self.current_tokens


class ChatCompletionLimiterPerUser(TextCompletionLimiter):
    def __init__(self, user_id, model_name, RPM, TPM, redis_instance):
        super().__init__(model_name=model_name,  RPM=RPM, TPM=TPM, redis_instance=redis_instance)
        self.user_id = user_id

    def _limit(self, tokens):
        return AdvancedLimiter(
            self.user_id,
            self.model_name,
            self.max_calls,
            self.max_tokens,
            self.period,
            tokens,
            self.redis,
        )


def send_to_ai(data, data_dictionary=None, xloader_report=None):
    chain = messages_tpl | client
    resp = chain.invoke({
        'data': [HumanMessage(content=json.dumps(data))],
        'data_dict': [HumanMessage(content=json.dumps(data_dictionary))],
        'xloader_report': [HumanMessage(content=json.dumps(xloader_report))],
    })
    ai_resp_data = resp.content.replace('```', '').replace('json\n', '')
    return ai_resp_data


def analyze_data(resource_id, data, data_dictionary=None, xloader_report=None):
    chat_limiter = ChatCompletionLimiterPerUser(
        user_id=tk.c.userobj.id,
        model_name=model_name,
        RPM=rpm_limit_per_user,
        TPM=tpm_limit_per_user,
        redis_instance=cache,
    )

    report = get_data(resource_id)
    if not report:
        with chat_limiter.limit(prompt=prompt_file_data, max_tokens=max_tokens) as limit:
            ai_res = send_to_ai(data, data_dictionary, xloader_report)
            store_data(resource_id, ai_res)
            report = json.loads(ai_res)
            report['rpm_left'] = limit.rpm_left()
            report['tpm_left'] = limit.tpm_left()
            report['cached'] = True
    return report


def store_data(resource_id, data):
    cache.set(resource_id, data)


def get_data(resource_id):
    try:
        report = {}
        data = cache.get(resource_id)
        if data:
            report = json.loads(data)
            report['cached'] = True
    except JSONDecodeError as exc:
        log.exception(exc)
        report = {}
    return report


def remove_data(resource_id):
    cache.delete(resource_id)
