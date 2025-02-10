import ckan.plugins.toolkit as tk


def dq_assistant_submit(context, data_dict):
    if 'id' not in data_dict:
        data_dict['id'] = data_dict.get('resource_id')

    user = context.get('user')

    authorized = tk.check_access('resource_update', context, data_dict)
    if not authorized:
        return {
            'success': False,
            'msg': tk._(
                'User {0} not authorized to use Data Quality Assistant for {1}'
                .format(user, data_dict['id'])
            )
        }
    else:
        return {'success': True}
