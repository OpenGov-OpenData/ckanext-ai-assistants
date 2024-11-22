
from ckan.plugins import toolkit as tk


def is_dq_assistant_enabled():
    if not tk.c.pkg_dict.get('private', True) and not is_xloader_status_complete(tk.c.resource.get('id')):
        return True
    return False


def is_xloader_status_complete(resource_id):
    try:
        xloader_status = tk.get_action("xloader_status")(
            None, {"resource_id": resource_id}
        )
        task_info = xloader_status.get('task_info')
        if not task_info:
            return False
        return task_info.get("status") == "complete"
    except tk.ObjectNotFound:
        return False


def user_is_sysadmin(context):
    model = context['model']
    user = context['user']
    user_obj = context['auth_user_obj'] or model.User.get(user)
    if not user_obj:
        return False
    return user_obj.sysadmin

def user_is_authorized_to_generate_report(context, data_dict=None):
    return {'success': user_is_sysadmin(context)}
