import logging
import datetime
from sys import getsizeof
import requests
from ckanext.dq_assistant.client import analyze_data
from ckan.plugins import toolkit as tk


logger = logging.getLogger(__name__)


def generate_report(resource_id, user_id):
    logger.info('Started generating report.')
    context = {'ignore_auth': True}
    task = {
        'entity_id': resource_id,
        'entity_type': 'resource',
        'task_type': 'dq_assistant',
        'last_updated': str(datetime.datetime.utcnow()),
        'state': 'started',
        'key': 'dq_assistant',
        'value': resource_id,
    }
    tk.get_action('task_status_update')(context, task)

    try:
        xloader_status = tk.get_action('xloader_status')(
            context, {'resource_id': resource_id}
        )
        logs = []
        if xloader_status and xloader_status.get('task_info'):
            task_info = xloader_status.get('task_info', {})
            logs = [line.get('message') for line in task_info.get('logs', [])]
        xloader_report_for_ai = {
            'error': xloader_status.get('error'),
            'logs': logs,
        }
    except tk.ObjectNotFound:
        xloader_report_for_ai = None
    try:
        rec = tk.get_action('datastore_search')(
            context, {
                'resource_id': resource_id,
                'limit': 0
            }
        )
        fields = [f for f in rec['fields'] if not f['id'].startswith('_')]
    except tk.ObjectNotFound:
        fields = []
    try:
        # 5 MB =
        maximum_data_size = 5 * 1024 * 1024
        data_size = 0
        data = []
        resource = tk.get_action('resource_show')(context, {'id': resource_id})
        with requests.get(resource.get('original_url') or resource.get('url'), stream=True, timeout=30) as resp:
            for _ in range(100):
                if data_size >= maximum_data_size:
                    break
                row = resp.raw.readline().decode(encoding=resp.encoding or 'utf-8')
                if not row:
                    break
                data.append(row)
                data_size += getsizeof(row)
        analyze_data(
            resource_id=resource_id,
            data=data,
            user_id=user_id,
            xloader_report=xloader_report_for_ai,
            data_dictionary=fields
        )
        task.update({
            'last_updated': str(datetime.datetime.utcnow()),
            'state': 'finished',
        })
    except Exception as ex:
        task.update({
            'last_updated': str(datetime.datetime.utcnow()),
            'state': 'failed',
            'error': str(ex)
        })
    tk.get_action('task_status_update')(context, task)
    return True
