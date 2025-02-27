import logging
import datetime
import requests
from sys import getsizeof

import ckan.plugins.toolkit as tk
from ckanext.dq_assistant.client import analyze_data


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
    task_status = tk.get_action('task_status_update')(context, task)

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
    except (tk.ObjectNotFound, tk.NotAuthorized):
        xloader_report_for_ai = None

    try:
        rec = tk.get_action('datastore_search')(
            context, {
                'resource_id': resource_id,
                'limit': 0
            }
        )
        fields = [f for f in rec['fields'] if not f['id'].startswith('_')]
    except (tk.ObjectNotFound, tk.NotAuthorized):
        fields = []

    try:
        # 5 MB =
        maximum_data_size = 5 * 1024 * 1024
        data_size = 0
        data = []
        resource = tk.get_action('resource_show')(context, {'id': resource_id})
        with requests.get(resource.get('original_url') or resource.get('url'), stream=True, timeout=60) as resp:
            for _ in range(100):
                if data_size >= maximum_data_size:
                    break
                row = resp.raw.readline().decode(encoding=resp.encoding or 'utf-8')
                if not row:
                    break
                data.append(row)
                data_size += getsizeof(row)
        logger.info('Prepared data for AI processing')
        analyze_data(
            resource_id=resource_id,
            data=data,
            user_id=user_id,
            xloader_report=xloader_report_for_ai,
            data_dictionary=fields
        )
        task_status.update({
            'last_updated': str(datetime.datetime.utcnow()),
            'state': 'finished',
        })
    except Exception as ex:
        logger.exception('Exception occurred while generating report.')
        task_status.update({
            'last_updated': str(datetime.datetime.utcnow()),
            'state': 'failed',
            'error': str(ex)
        })
    tk.get_action('task_status_update')(context, task_status)
    return True
