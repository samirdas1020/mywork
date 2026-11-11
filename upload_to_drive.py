import os
import sys
import json
import urllib.parse
import urllib.request


def get_token():
    data = urllib.parse.urlencode({
        "client_id": os.environ["GDRIVE_CLIENT_ID"],
        "client_secret": os.environ["GDRIVE_CLIENT_SECRET"],
        "refresh_token": os.environ["GDRIVE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req) as r:
        return json.load(r)["access_token"]


def create_folder(token, name):
    body = json.dumps({"name": name, "mimeType": "application/vnd.google-apps.folder"}).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/drive/v3/files",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)["id"]


def upload_file(token, path, folder_id):
    name = os.path.basename(path)
    meta = {"name": name}
    if folder_id:
        meta["parents"] = [folder_id]

    # 1) start a resumable session
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
        data=json.dumps(meta).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
    )
    with urllib.request.urlopen(req) as r:
        session_url = r.headers["Location"]

    # 2) send the file content
    with open(path, "rb") as f:
        content = f.read()
    put = urllib.request.Request(session_url, data=content, method="PUT")
    with urllib.request.urlopen(put) as r:
        r.read()
    print(f"Uploaded {name} ({len(content)//1024} KB)", flush=True)


def main():
    src = sys.argv[1]                                  # file or folder to upload
    folder_name = sys.argv[2] if len(sys.argv) > 2 else None  # Drive folder to create

    token = get_token()
    folder_id = create_folder(token, folder_name) if folder_name else None

    if os.path.isdir(src):
        for fn in sorted(os.listdir(src)):
            p = os.path.join(src, fn)
            if os.path.isfile(p):
                upload_file(token, p, folder_id)
    else:
        upload_file(token, src, folder_id)
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
