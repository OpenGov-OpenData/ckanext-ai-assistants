import ckan.plugins.toolkit as tk


def is_dq_assistant_enabled():
    try:
        if not tk.g.pkg_dict.get('private', True) and is_xloader_status_error(tk.g.resource.get('id')):
            return True
    except AttributeError:
        pass
    return False


def is_xloader_status_error(resource_id):
    try:
        xloader_status = tk.get_action('xloader_status')(
            None, {'resource_id': resource_id}
        )
        task_info = xloader_status.get('task_info')
        if not task_info:
            return False
        return task_info.get('status') == 'error'
    except (tk.ObjectNotFound, tk.NotAuthorized):
        return False
