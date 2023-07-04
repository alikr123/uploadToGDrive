import importlib
import subprocess
import time
import sys
import os
import json

import modules.scripts as scripts
import gradio as gr
from modules.processing import process_images
from modules import script_callbacks

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

python = sys.executable


def run(command, desc=None, errdesc=None, custom_env=None, live=False):
    if desc is not None:
        print(desc)

    if live:
        result = subprocess.run(
            command, shell=True, env=os.environ if custom_env is None else custom_env
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}"""
            )

        return ""

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        env=os.environ if custom_env is None else custom_env,
    )

    if result.returncode != 0:
        message = f"""{errdesc or 'Error running command'}.
Command: {command}
Error code: {result.returncode}
stdout: {result.stdout.decode(encoding="utf8", errors="ignore") if len(result.stdout)>0 else '<empty>'}
stderr: {result.stderr.decode(encoding="utf8", errors="ignore") if len(result.stderr)>0 else '<empty>'}
"""
        raise RuntimeError(message)

    return result.stdout.decode(encoding="utf8", errors="ignore")


def run_pip(command, desc=None, live=False):
    return run(
        f'"{python}" -m pip {command}',
        desc=f"Installing {desc}",
        errdesc=f"Couldn't install {desc}",
        live=live,
    )


def is_installed(package):
    try:
        spec = importlib.util.find_spec(package)
    except ModuleNotFoundError:
        return False

    return spec is not None


if not is_installed("google"):
    run_pip(f"install google", "google")

if not is_installed("googleapiclient"):
    run_pip(f"install googleapiclient", "googleapiclient")


class Script(scripts.Script):
    def title(self):
        return "Upload to Google Drive"

    def ui(self, is_img2img):
        folder_id = gr.Textbox(label="Folder Id")
        credentials = gr.Textbox(label="credentials (copy complete json)")
        return [folder_id, credentials]

    def run(self, p, folder_id, credentials):
        def google_auth():
            service_account_info = json.loads(credentials)
            SCOPES = [
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive.resource",
            ]

            creds = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )

            service = build("drive", "v3", credentials=creds)
            return service

        def upload_to_folder(service, folder_id, filename):
            try:
                file_metadata = {"name": filename, "parents": [folder_id]}
                media = MediaFileUpload(filename, mimetype="image/jpeg", resumable=True)
                # pylint: disable=maybe-no-member
                file = (
                    service.files()
                    .create(body=file_metadata, media_body=media, fields="id")
                    .execute()
                )
                print(f'File ID: "{file.get("id")}".')
                return file.get("id")

            except HttpError as error:
                print(f"An error occurred: {error}")
                return None

        def upload_to_google_drive(params: script_callbacks.ImageSaveParams):
            service = google_auth()
            upload_to_folder(service, folder_id, params.filename)

        script_callbacks.on_image_saved(upload_to_google_drive)
        proc = process_images(p)
        return proc
