import json
import os


def _load_raw_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.exists(config_path):
        return {}
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_accounts():
    cfg = _load_raw_config()
    return cfg.get('accounts', {})


def load_account_config(account_name=None):
    cfg = _load_raw_config()
    accounts = cfg.get('accounts', {})
    if not accounts:
        return {'mt4_path': '', 'mt5_path': '', 'workspaces': {}}
    if account_name is None:
        account_name = cfg.get('default_account') or next(iter(accounts))
    acc_cfg = accounts.get(account_name, {})
    return {
        'mt4_path': acc_cfg.get('mt4_path', ''),
        'mt5_path': acc_cfg.get('mt5_path', ''),
        'workspaces': acc_cfg.get('workspaces', {})
    }
