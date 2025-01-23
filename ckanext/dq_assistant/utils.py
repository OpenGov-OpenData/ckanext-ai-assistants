
from ckan.plugins import toolkit as tk


def is_dq_assistant_enabled():
    try:
        if not tk.c.pkg_dict.get('private', True) and is_xloader_status_error(tk.c.resource.get('id')):
            return True
    except AttributeError:
        pass
    return False


def is_xloader_status_error(resource_id):
    try:
        xloader_status = tk.get_action("xloader_status")(
            None, {"resource_id": resource_id}
        )
        task_info = xloader_status.get('task_info')
        if not task_info:
            return False
        return task_info.get("status") == "error"
    except (tk.ObjectNotFound, tk.NotAuthorized):
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
