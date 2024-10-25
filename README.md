Ckan AI assistance
===========

Requirements
------------
Requires [datastore](https://github.com/ckan/ckan/tree/master/ckanext/datastore)  and [xloader](https://github.com/ckan/ckanext-xloader) extensions.


Config settings
---------------
```ini
# general settings
ckan.plugins = ... dq_assistant datastore xloader ...
ckan.dq_assistant.enable_for_orgadmins = True
ckan.dq_assistant.only_for_failed_xloader_jobs = True

ckan.dq_assistant.rpm_limit_per_user = int (default 3)
ckan.dq_assistant.tpm_limit_per_user = int (default 3000)


# OpenAI settings https://python.langchain.com/api_reference/openai/chat_models/langchain_openai.chat_models.base.ChatOpenAI.html#langchain_openai.chat_models.base.ChatOpenAI
ckan.openapi.api_key = <your openai api key> (required)
ckan.openapi.prompt_file = str (required)

ckan.openapi.timeout = int (default 60)
ckan.openapi.max_tokens = int (default 512)
ckan.openapi.model = str (default gpt-4o)
ckan.openapi.temperature = float (default 0.1)
ckan.openapi.top_p = int (default 1)
ckan.openapi.frequency_penalty = int (default 0)
ckan.openapi.presence_penalty = int (default 0)
                     

ckan.openapi.redis_url = redis://redis:6379/1
```
