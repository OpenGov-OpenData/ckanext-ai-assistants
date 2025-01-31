
from ckan.plugins import toolkit as tk
from ckan import plugins as p


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


def user_is_authorized_to_generate_report(context, data_dict):
    if not data_dict:
        return {
            'success': False,
            'msg': p.toolkit._(
                'User not authorized to use dq_assistant.')
        }
    if 'id' not in data_dict:
        data_dict['id'] = data_dict.get('resource_id')

    user = context.get('user')

    authorized = p.toolkit.check_access('resource_update', context, data_dict)
    if not authorized:
        return {
            'success': False,
            'msg': p.toolkit._(
                'User {0} not authorized to use dq_assistant {1}'
                    .format(user, data_dict['id'])
            )
        }
    else:
        return {'success': True}
