"""Flask application factory."""

from __future__ import annotations

from flask import Flask

from ledger.api import routes
from ledger.store import Store


def create_app(store: Store | None = None) -> Flask:
    """Build the app. With no store, open the default sqlite file."""
    app = Flask(__name__)
    if store is None:
        store = Store.open_default()
    else:
        store.init_db()
    app.extensions["ledger_store"] = store
    app.register_blueprint(routes.bp)
    return app
