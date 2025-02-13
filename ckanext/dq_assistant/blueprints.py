import logging
import datetime
import ckan.plugins.toolkit as tk
from flask import Blueprint, request
from dateutil.parser import isoparse as parse_iso_date
from ckanext.dq_assistant.client import chat_limiter, get_data
from ckanext.dq_assistant.jobs import generate_report


log = logging.getLogger(__name__)
dq_assistant = Blueprint('dq_assistant', __name__, url_prefix='/dq_assistant')


@dq_assistant.route('/report/<dataset_id>/resource/<resource_id>',
                    methods=['GET', 'POST'], strict_slashes=False, merge_slashes=True)
def resource_report(dataset_id, resource_id):
    try:
        tk.check_access('dq_assistant_submit',  context={'user': tk.g.user}, data_dict={'id': resource_id})
    except tk.NotAuthorized:
        return tk.abort(403, tk._('Not authorized to see this page'))
    except tk.ObjectNotFound:
        return tk.abort(404, tk._('Resource not found'))

    user_id = tk.g.userobj.id
    limiter = chat_limiter.limit(user_id=user_id, prompt='', max_tokens=5)
    rpm_left = limiter.rpm_left()
    tpm_left = limiter.tpm_left()

    if request.method == 'POST':
        redirect_url = tk.url_for('dq_assistant.resource_report', dataset_id=dataset_id, resource_id=resource_id)
        if rpm_left <= 0 or tpm_left <= 0:
            tk.h.flash_error(tk._('You have reached the maximum number of requests. Please try again later.'))
            return tk.redirect_to(redirect_url)
        try:
            existing_task = tk.get_action('task_status_show')({'ignore_auth': True}, {
                'entity_id': resource_id,
                'entity_type': 'resource',
                'task_type': 'dq_assistant',
                'key': 'dq_assistant',
            })
            if existing_task.get('state') == 'started':
                assume_task_stale_after = datetime.timedelta(seconds=int(30))
                updated = parse_iso_date(existing_task['last_updated'])
                time_since_last_updated = datetime.datetime.utcnow() - updated
                if time_since_last_updated < assume_task_stale_after:
                    tk.h.flash_error(tk._('Report generation is already in progress. Please wait for it to finish.'))
                    return tk.redirect_to(redirect_url)
        except tk.ObjectNotFound:
            task_status = {}

        tk.enqueue_job(generate_report, args=(resource_id, user_id), title=resource_id, rq_kwargs={'timeout': 120})

        tk.h.flash_success(tk._('Report generation will start shortly. Refresh this page for updates.'))
        return tk.redirect_to(redirect_url)

    try:
        pkg_dict = tk.get_action('package_show')(None, {'id': dataset_id})
        resource = tk.get_action('resource_show')(None, {'id': resource_id})
        report = get_data(resource_id)
    except tk.NotAuthorized:
        return tk.abort(403, tk._('Not authorized to see this page'))
    except tk.ObjectNotFound:
        return tk.abort(404, tk._('Resource not found'))

    tk.g.pkg_dict = pkg_dict
    tk.g.resource = resource

    task_status = {}
    if not report:
        task = {
            'entity_id': resource_id,
            'entity_type': 'resource',
            'task_type': 'dq_assistant',
            'key': 'dq_assistant',
        }
        try:
            task = tk.get_action('task_status_show')({'ignore_auth': True}, task)
            task_status = {
                'id': task.get('id'),
                'state': task.get('state'),
                'last_updated': task.get('last_updated'),
            }
        except tk.ObjectNotFound:
            task_status = {}
    report['rpm_left'] = rpm_left
    report['tpm_left'] = tpm_left
    return tk.render(
        'dq_assistant/resource_report.html',
        extra_vars={
            'dataset_id': dataset_id,
            'resource_id': resource_id,
            'pkg_dict': tk.g.pkg_dict,
            'resource': tk.g.resource,
            'report': report,
            'job': task_status,
        }
    )
