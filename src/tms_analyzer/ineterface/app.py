import os
from pathlib import Path

from flask import Flask
from extensions import db
from models import User


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    Path(app.instance_path).mkdir(
        parents=True,
        exist_ok=True,
    )

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + str(
            Path(app.instance_path) / "app.db"
        ),
    )

    db.init_app(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)