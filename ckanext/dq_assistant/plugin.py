import logging
import ckan.plugins as p
from ckan.plugins import toolkit as tk
from ckanext.dq_assistant.blueprints import dq_assistant
from ckanext.dq_assistant.utils import is_dq_assistant_enabled, user_is_authorized_to_generate_report
from ckanext.dq_assistant.client import remove_data


log = logging.getLogger(__name__)


class DQAIPlugin(p.SingletonPlugin):

    p.implements(p.IConfigurer)
    p.implements(p.IBlueprint)
    p.implements(p.IAuthFunctions)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IResourceController, inherit=True)

    ## IConfigurer
    def update_config(self, config):
        log.info('You are using the following plugins: {0}'
                 .format(config.get('ckan.plugins')))

        api_key = config.get('ckan.openapi.api_key')
        if not api_key:
            raise tk.ValidationError("ckan.openapi.api_key is not set")

        prompt_file = config.get('ckan.openapi.prompt_file')
        if not prompt_file:
            raise tk.ValidationError("ckan.openapi.prompt_file is not set")

        # Add the extension templates directory so it overrides the CKAN core
        p.toolkit.add_template_directory(config, './templates')
        p.toolkit.add_resource('./assets', 'dq-assistant')

    def get_blueprint(self):
        return [dq_assistant]

    def after_update(self, context, resource_dict):
        log.info('Cache purged for {}'.format(resource_dict.get('id')))
        remove_data(resource_dict.get('id'))

    def get_helpers(self):
        return {
            "is_dq_assistant_enabled": is_dq_assistant_enabled,
        }

    def get_auth_functions(self):
        return {
            'is_user_authorized_to_generate_report': user_is_authorized_to_generate_report,
        }
