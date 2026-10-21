"""Small service chain used only for documentation-tool regression tests."""


def load_item(store, key):
    return store.get(key)


def handle(store, key):
    value = load_item(store, key)
    return {'status': 404} if value is None else {'status': 200, 'item': value}
