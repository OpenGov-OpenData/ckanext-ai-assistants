import json
import yaml

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from functools import lru_cache

from ckan.plugins import toolkit as tk
from common import asint

prompt = yaml.load(open(tk.config.get('ckan.openapi.prompt_file'), 'r'), Loader=yaml.SafeLoader)

messages = [(message.get('role', 'system'),message.get('content', '')) for message  in prompt.get('messages', [])]
messages.extend([
    MessagesPlaceholder('data', optional=False),
    MessagesPlaceholder('data_dict', optional=True),
    MessagesPlaceholder('xloader_report', optional=True)]
)

messages = ChatPromptTemplate(messages)


client = ChatOpenAI(
    api_key=tk.config.get('ckan.openapi.api_key'),
    timeout=asint(tk.config.get('ckan.openapi.timeout', 60)),
    model=tk.config.get('ckan.openapi.model', "gpt-4o"),
    max_tokens=asint(tk.config.get('ckan.openapi.max_tokens', 512)),
    temperature=float(tk.config.get('ckan.openapi.temperature', 0.1)),
    top_p=asint(tk.config.get('ckan.openapi.top_p', 1)),
    frequency_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
    presence_penalty=asint(tk.config.get('ckan.openapi.presence_penalty', 0)),
    disable_streaming=True,
)

def analyze_data(data, data_dictionary=None, xloader_report=None):
    chain = messages | client
    return chain.invoke({
            'data': [HumanMessage(content=json.dumps(data))],
            'data_dict': [HumanMessage(content=json.dumps(data_dictionary))],
            'xloader_report': [HumanMessage(content=json.dumps(xloader_report))],
    })

