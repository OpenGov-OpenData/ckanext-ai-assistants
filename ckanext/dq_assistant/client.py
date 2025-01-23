import json
import yaml
import redis
import logging
import time
import types
import tiktoken

from typing import Optional, Type, Any, Union
from redis.lock import Lock

import ckan.model as model
from ckan.plugins import toolkit as tk
from ckan.common import asint

from tiktoken.core import Encoding
from openai import OpenAI
from ckanext.dq_assistant import db


log = logging.getLogger(__name__)


with open(tk.config.get('ckan.openapi.prompt_file', ''), 'r') as f:
    prompt_file_data = f.read()
prompt = yaml.load(prompt_file_data, Loader=yaml.SafeLoader)
redis_url = tk.config.get('ckan.dq_assistant.redis_url')
cache = redis.from_url(redis_url)
cache_ttl = asint(tk.config.get('ckan.dq_assistant.redis_cache_ttl_days', 0)) * 24 * 60 * 60


messages = prompt.get('messages', [])

model_name = tk.config.get('ckan.openapi.model', "gpt-4o")
rpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.rpm_limit_per_user', 1))
tpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.tpm_limit_per_user', 10000))
max_tokens = asint(tk.config.get('ckan.openapi.max_tokens', 512))
client = OpenAI(
    api_key=tk.config.get('ckan.openapi.api_key'),
    timeout=asint(tk.config.get('ckan.openapi.timeout', 60)),
)


class AdvancedLimiter:
    def __init__(
        self,
        user_id: str,
        model_name: str,
        max_calls: int,
        max_tokens: int,
        period: int,
        tokens: int,
        redis: "redis.Redis[bytes]",
                 ):
        self.key = "{}_{}".format(user_id, model_name)
        self.current_calls = 0
        self.current_tokens = 0
        self.model_name = model_name
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.period = period
        self.tokens = tokens
        self.redis = redis

    def __enter__(self):
        lock = Lock(self.redis, f"{self.key}_lock", timeout=self.period)
        with lock:
            while True:
                self.current_calls = self.redis.incr(
                    f"{self.key}_api_calls", amount=1
                )
                if self.current_calls == 1:
                    self.redis.expire(f"{self.key}_api_calls", self.period)
                if self.current_calls <= self.max_calls:
                    break
                else:
                    lock.release()  # Release the lock before sleeping
                    time.sleep(self.period)  # wait for the limit to reset
                    lock.acquire()

            while True:
                self.current_tokens = self.redis.incrby(
                    f"{self.key}_api_tokens", self.tokens
                )
                if self.current_tokens == self.tokens:
                    self.redis.expire(f"{self.key}_api_tokens", self.period)
                if self.current_tokens <= self.max_tokens:
                    break
                else:
                    lock.release()  # Release the lock before sleeping
                    time.sleep(self.period)  # wait for the limit to reset
                    lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[types.TracebackType],
    ) -> Optional[bool]:
        pass

    def rpm_left(self):
        return self.max_calls - self.current_calls

    def tpm_left(self):
        return self.max_tokens - self.current_tokens


class ChatCompletionLimiterPerUser:
    def __init__(self, user_id: str, model_name: str, rpm: int, tpm: int, redis_instance: "redis.Redis[bytes]"):
        """
        Initializer for the BaseAPILimiterRedis class.

        Args:
            model_name (str): The name of the model being limited.
            rpm (int): The maximum number of requests per minute allowed. You can find your rate limits in your
                       OpenAI account at https://platform.openai.com/account/rate-limits
            tpm (int): The maximum number of tokens per minute allowed. You can find your rate limits in your
                       OpenAI account at https://platform.openai.com/account/rate-limits
            redis_instance (redis.Redis[bytes]): The redis instance.

        Creates an instance of the BaseAPILimiterRedis with the specified parameters, and connects to a Redis server
        at the specified host and port.
        """
        self.user_id = user_id
        self.model_name = model_name
        self.max_calls = rpm
        self.max_tokens = tpm
        self.period = 60
        self.redis = redis_instance
        try:
            if not self.redis.ping():
                raise ConnectionError("Redis server is not working. Ping failed.")
        except redis.ConnectionError as e:
            raise ConnectionError("Redis server is not running.", e)
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoder = None

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

    def limit(self, prompt: str, max_tokens: int):
        if not self.encoder:
            raise ValueError("The encoder is not set.")
        tokens = self.num_tokens_consumed_by_completion_request(
            prompt, self.encoder, max_tokens
        )
        return self._limit(tokens)

    @staticmethod
    def num_tokens_consumed_by_completion_request(
        prompt: Union[str, list[str], Any],
        encoder: Encoding,
        max_tokens: int = 15,
        n: int = 1,
    ):
        num_tokens = n * max_tokens
        if isinstance(prompt, str):  # Single prompt
            num_tokens += len(encoder.encode(prompt))
        elif isinstance(prompt, list):  # Multiple prompts
            num_tokens *= len(prompt)
            num_tokens += sum([len([encoder.encode(p) for p in prompt])])
        else:
            raise TypeError(
                "Either a string or list of strings expected for 'prompt' field in completion request."
            )

        return num_tokens


def send_to_ai(data, data_dictionary=None, xloader_report=None):
    msgs = messages
    msgs.append(
        {
            'role': 'user',
            'content':  f'data={data}\ndata_dict={data_dictionary}\nxloader_report={xloader_report}\nencoding=UTF-8',
         }
    )

    resp = client.chat.completions.create(
        model=model_name,
        max_tokens=max_tokens,
        temperature=float(tk.config.get('ckan.openapi.temperature', 0.1)),
        top_p=asint(tk.config.get('ckan.openapi.top_p', 1)),
        frequency_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
        presence_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
        messages=messages,
        stream=False,
    )
    data = resp.choices[0].message.content.replace('```', '').replace('json\n', '')
    return data


def analyze_data(resource_id, data, data_dictionary=None, xloader_report=None):
    chat_limiter = ChatCompletionLimiterPerUser(
        user_id=tk.c.userobj.id,
        model_name=model_name,
        rpm=rpm_limit_per_user,
        tpm=tpm_limit_per_user,
        redis_instance=cache,
    )

    report = get_data(resource_id)
    if not report:
        with chat_limiter.limit(prompt=prompt_file_data, max_tokens=max_tokens) as limit:
            ai_res = send_to_ai(data, data_dictionary, xloader_report)
            report = {}
            report['rpm_left'] = limit.rpm_left()
            report['tpm_left'] = limit.tpm_left()
            try:
                report = json.loads(ai_res)
                report['cached'] = True
                store_data(resource_id, ai_res)
            except json.JSONDecodeError as exc:
                log.exception(exc)
                report['cached'] = False
    return report


def store_data(resource_id, data):
    report = db.DataQualityReports()
    report.resource_id = resource_id
    report.data = data.encode()
    model.Session.add(report)
    model.Session.commit()


def get_data(resource_id):
    try:
        report = {}
        stored_report = db.DataQualityReports.by_resource_id(resource_id)
        if stored_report:
            report = json.loads(stored_report.data)
            report['cached'] = True
    except json.JSONDecodeError as exc:
        log.exception(exc)
        report = {}
    return report


def remove_data(resource_id):
    try:
        db.DataQualityReports.by_resource_id(resource_id).delete()
        model.Session.commit()
    except (tk.ObjectNotFound, AttributeError):
        pass
