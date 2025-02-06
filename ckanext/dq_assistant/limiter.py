import time
import types
import tiktoken
import redis

from typing import Optional, Type, Any, Union
from redis.lock import Lock
from tiktoken.core import Encoding


class AdvancedLimiter:
    def __init__(
        self,
        user_id: str,
        model_name: str,
        max_calls: int,
        max_tokens: int,
        period: int,
        tokens: int,
        redis: 'redis.Redis[bytes]',
                 ):
        self.key = '{}_{}'.format(user_id, model_name)
        self.current_calls = 0
        self.current_tokens = 0
        self.model_name = model_name
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.period = period
        self.tokens = tokens
        self.redis = redis

    def __enter__(self):
        lock = Lock(self.redis, f'{self.key}_lock', timeout=self.period)
        with lock:
            while True:
                self.current_calls = self.redis.incr(
                    f'{self.key}_api_calls', amount=1
                )
                if self.current_calls == 1:
                    self.redis.expire(f'{self.key}_api_calls', self.period)
                if self.current_calls <= self.max_calls:
                    break
                else:
                    lock.release()  # Release the lock before sleeping
                    time.sleep(self.period)  # wait for the limit to reset
                    lock.acquire()

            while True:
                self.current_tokens = self.redis.incrby(
                    f'{self.key}_api_tokens', self.tokens
                )
                if self.current_tokens == self.tokens:
                    self.redis.expire(f'{self.key}_api_tokens', self.period)
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
    def __init__(self, model_name: str, rpm: int, tpm: int, redis_instance: 'redis.Redis[bytes]'):
        '''
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
        '''
        self.model_name = model_name
        self.max_calls = rpm
        self.max_tokens = tpm
        self.period = 60
        self.redis = redis_instance
        try:
            if not self.redis.ping():
                raise ConnectionError('Redis server is not working. Ping failed.')
        except redis.ConnectionError as e:
            raise ConnectionError('Redis server is not running.', e)
        try:
            self.encoder = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoder = None

    def _limit(self, tokens, user_id):
        return AdvancedLimiter(
            user_id,
            self.model_name,
            self.max_calls,
            self.max_tokens,
            self.period,
            tokens,
            self.redis,
        )

    def limit(self, user_id: str, prompt: str, max_tokens: int):
        if not self.encoder:
            raise ValueError('The encoder is not set.')
        tokens = self.num_tokens_consumed_by_completion_request(
            prompt, self.encoder, max_tokens
        )
        return self._limit(tokens, user_id)

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
                'Either a string or list of strings expected for \'prompt\' field in completion request.'
            )

        return num_tokens
