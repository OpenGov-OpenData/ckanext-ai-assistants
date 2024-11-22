import logging
from sys import getsizeof
import requests
import ckan.plugins as p
from common import request

from ckan.logic import NotFound, check_access
from views.resource import Blueprint
from ckanext.dq_assistant.client import analyze_data, get_data


log = logging.getLogger(__name__)



dq_assistant = Blueprint("dq_assistant", __name__, url_prefix='/dq_assistant')


@dq_assistant.route("/report/<dataset_id>/resource/<resource_id>",
              methods=['GET', 'POST'], strict_slashes=False, merge_slashes=True)

def resource_report(dataset_id, resource_id):
    try:
        check_access('is_user_authorized_to_generate_report', context={'user': p.toolkit.c.user})
    except p.toolkit.NotAuthorized:
        return p.toolkit.abort(403)
    pkg_dict = p.toolkit.get_action("package_show")(None, {"id": dataset_id})
    resource = p.toolkit.get_action("resource_show")(None, {"id": resource_id})
    p.toolkit.c.pkg_dict = pkg_dict
    p.toolkit.c.resource = resource
    try:
        xloader_status = p.toolkit.get_action("xloader_status")(
            None, {"resource_id": resource_id}
        )
        logs = []
        status = 'no status'
        if xloader_status and xloader_status.get('task_info'):
            task_info = xloader_status.get('task_info', {})
            logs = [line.get("message") for line in task_info.get('logs', [])]
            status = task_info.get('status')
        xloader_report_for_ai = {
            "status": status,
            "error": xloader_status.get('error'),
            "logs": logs,
        }
    except NotFound:
        xloader_status = {}
        xloader_report_for_ai = None

    if request.method == 'GET':
        return p.toolkit.render(
            "dq_assistant/resource_report.html",
            extra_vars={
                "dataset_id": dataset_id,
                "resource_id": resource_id,
                "resource": p.toolkit.c.resource,
                "pkg_dict": p.toolkit.c.pkg_dict,
                "status": xloader_status,
                "report": get_data(resource_id),
            }
        )

    try:
        rec = p.toolkit.get_action('datastore_search')(
            None, {
                'resource_id': resource_id,
                'limit': 0
            }
        )
        fields =[ f for f in rec['fields'] if not f['id'].startswith('_')]
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
    report = analyze_data(resource_id=resource_id, data=data, xloader_report=xloader_report_for_ai, data_dictionary=fields)
    return p.toolkit.render(
        "dq_assistant/resource_report.html",
        extra_vars={
            "status": xloader_status,
            "resource": p.toolkit.c.resource,
            "pkg_dict": p.toolkit.c.pkg_dict,
            "report": report,
        },
    )
