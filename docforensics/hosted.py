"""Run the password-protected hosted demo behind Render's HTTPS proxy."""

import os
from pathlib import Path

import uvicorn

from .upload_app import create_app


def main():
    app = create_app(
        Path("/var/lib/scopeguard"),
        hosted_access=(os.environ["RENDER_EXTERNAL_HOSTNAME"], os.environ["DEMO_PASSWORD"]),
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")),
                proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
