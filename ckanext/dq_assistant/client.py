import yaml
import redis
import logging

import ckan.model as model
from ckan.plugins import toolkit as tk
from ckan.common import asint

from openai import OpenAI
from ckanext.dq_assistant import db
from ckanext.dq_assistant.limiter import ChatCompletionLimiterPerUser

log = logging.getLogger(__name__)


with open(tk.config.get('ckan.openapi.prompt_file', ''), 'r') as f:
    prompt_file_data = f.read()
prompt = yaml.load(prompt_file_data, Loader=yaml.SafeLoader)
redis_url = tk.config.get('ckan.dq_assistant.redis_url')
cache = redis.from_url(redis_url)

messages = prompt.get('messages', [])

model_name = tk.config.get('ckan.openapi.model', 'gpt-4o')
rpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.rpm_limit_per_user', 1))
tpm_limit_per_user = asint(tk.config.get('ckan.dq_assistant.tpm_limit_per_user', 1000))
max_tokens = asint(tk.config.get('ckan.openapi.max_tokens', 512))
client = OpenAI(
    api_key=tk.config.get('ckan.openapi.api_key'),
    timeout=asint(tk.config.get('ckan.openapi.timeout', 60)),
)
chat_limiter = ChatCompletionLimiterPerUser(
        model_name=model_name,
        rpm=rpm_limit_per_user,
        tpm=tpm_limit_per_user,
        redis_instance=cache,
    )

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
    data = resp.choices[0].message.content.replace('```', '').replace('html\n', '')
    return data



def analyze_data(resource_id, data, user_id, data_dictionary=None, xloader_report=None):
    lock = chat_limiter.limit(user_id=user_id, prompt=prompt_file_data, max_tokens=max_tokens)
    report = get_data(resource_id)
    if not report:
        with lock:
            report = dict()
            report['data'] = send_to_ai(data, data_dictionary, xloader_report)
            report['cached'] = True
            store_data(resource_id, report['data'])
    report['rpm_left'] = lock.rpm_left()
    report['tpm_left'] = lock.tpm_left()
    return report


def store_data(resource_id, data):
    report = db.DataQualityReports()
    report.resource_id = resource_id
    report.data = data.encode()
    model.Session.add(report)
    model.Session.commit()


def get_data(resource_id):
    report = {}
    stored_report = db.DataQualityReports.by_resource_id(resource_id)
    if stored_report:
        report['data'] = stored_report.data.decode()
        report['cached'] = True
    return report


def remove_data(resource_id):
    try:
        db.DataQualityReports.by_resource_id(resource_id).delete()
        model.Session.commit()
    except (tk.ObjectNotFound, AttributeError):
        pass
