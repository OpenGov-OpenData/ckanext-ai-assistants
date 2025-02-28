import logging
import ckan.plugins as p
from ckan.plugins import toolkit as tk
from ckanext.dq_assistant.auth import dq_assistant_submit
from ckanext.dq_assistant.blueprints import dq_assistant
from ckanext.dq_assistant.utils import is_dq_assistant_enabled
from ckanext.dq_assistant.client import remove_data
from ckanext.dq_assistant import db
from ckanext.xloader.interfaces import IXloader

log = logging.getLogger(__name__)


class DQAIPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IConfigurable)
    p.implements(p.IBlueprint)
    p.implements(p.IAuthFunctions)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IResourceController, inherit=True)
    p.implements(IXloader)

    # IXloader
    def can_upload(self, resource_id):
        log.info('Cache purged for {}'.format(resource_id))
        remove_data(resource_id)
        return True

    def after_upload(self, context, resource_dict, dataset_dict):
        log.info('Cache purged for {}'.format(resource_dict.get('id')))
        remove_data(resource_dict.get('id'))

    # IConfigurable
    def configure(self, config):
        db.init_db()

    # IConfigurer
    def update_config(self, config):
        plugins = config.get('ckan.plugins')
        if 'xloader' not in plugins or 'datastore' not in plugins:
            log.error('xloader and datastore plugins must be enabled for dq_assistant plugin.')

        api_key = config.get('ckan.openapi.api_key')
        if not api_key:
            raise tk.ValidationError('ckan.openapi.api_key is not set')

        prompt_file = config.get('ckan.openapi.prompt_file')
        if not prompt_file:
            raise tk.ValidationError('ckan.openapi.prompt_file is not set')

        # Add the extension templates directory so it overrides the CKAN core
        p.toolkit.add_template_directory(config, './templates')
        p.toolkit.add_resource('./assets', 'dq-assistant')

    # IBlueprint
    def get_blueprint(self):
        return [dq_assistant]

    # IResourceController
    def before_create(self, context, resource):
        remove_data(resource.get('id'))

    def before_update(self, context, current, resource):
        remove_data(resource.get('id'))

    def before_delete(self, context, resource, resources):
        remove_data(resource.get('id'))

    # ITemplateHelpers
    def get_helpers(self):
        return {
            'is_dq_assistant_enabled': is_dq_assistant_enabled,
        }

    # IAuthFunctions
    def get_auth_functions(self):
        return {
            'dq_assistant_submit': dq_assistant_submit,
        }
