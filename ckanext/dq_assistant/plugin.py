import json
import logging
from json import JSONDecodeError
from sys import getsizeof
import requests
import ckan.plugins as p
from common import request
from ckan.plugins import toolkit as tk

from logic import NotFound
from views.resource import Blueprint
from ckanext.dq_assistant.client import analyze_data

log = logging.getLogger(__name__)

openai = Blueprint("dq_assistant", __name__, url_prefix='/dq_assistant')


class DQAIPlugin(p.SingletonPlugin):

    p.implements(p.IConfigurer)
    p.implements(p.IBlueprint)
    # p.implements(p.IAuthFunctions)
    # p.implements(p.IActions)

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

        # Add the extension public directory so we can serve our own content
        # p.toolkit.add_public_directory(config, 'theme/public')

    def get_blueprint(self):
        return [openai]



@openai.route("/report/<dataset_id>/resource/<resource_id>",
              methods=['GET', 'POST'], strict_slashes=False, merge_slashes=True)

def resource_report(dataset_id, resource_id):
    pkg_dict = p.toolkit.get_action("package_show")(None, {"id": dataset_id})
    resource = p.toolkit.get_action("resource_show")(None, {"id": resource_id})
    p.toolkit.c.pkg_dict = pkg_dict
    p.toolkit.c.resource = resource
    xloader_status = p.toolkit.get_action("xloader_status")(
        None, {"resource_id": resource_id}
    )
    if request.method == 'GET':
        return p.toolkit.render(
            "dq_assistant/resource_report.html",
            extra_vars={
                "dataset_id": dataset_id,
                "resource_id": resource_id,
                "resource": p.toolkit.c.resource,
                "pkg_dict": p.toolkit.c.pkg_dict,
                "status": xloader_status,
            }
        )
    if xloader_status:
        logs=[]
        if xloader_status.get('task_info'):
            logs = [line.get("message") for line in xloader_status.get('task_info', {}).get('logs', [])]
        xloader_report_for_ai = {
            "status": xloader_status.get('status'),
            "error": xloader_status.get('error'),
            "logs": logs,
        }
    else:
        xloader_report_for_ai=None
    try:
        rec = p.toolkit.get_action(u'datastore_search')(
            None, {
                u'resource_id': resource_id,
                u'limit': 0
            }
        )
        fields =[ f for f in rec[u'fields'] if not f[u'id'].startswith(u'_')]
    except (NotFound, p.toolkit.ObjectNotFound):
        fields = []

    # 5 MB =
    maximum_data_size = 5 * 1024 * 1024
    data_size = 0
    data = []
    with requests.get(resource.get('original_url') or resource.get('url'), stream=True) as resp:
        for _ in range(100):
            if data_size >= maximum_data_size:
                break
            row = resp.raw.readline().decode(encoding=resp.encoding or 'utf-8')
            if not row:
                break
            data.append(row)
            data_size += getsizeof(row)
    msg = analyze_data(data=data, xloader_report=xloader_report_for_ai, data_dictionary=fields)
    try:
        report = json.loads(msg.content.replace('```', '').replace('json\n', ''))
    except JSONDecodeError as exc:
        log.exception(exc)
        report = {'summary': 'Could not get analysis report from AI. Please try again.'}
    return p.toolkit.render(
            "dq_assistant/resource_report.html",
            extra_vars={
                "status": xloader_status,
                "resource": p.toolkit.c.resource,
                "pkg_dict": p.toolkit.c.pkg_dict,
                "report": report,
            },
        )
