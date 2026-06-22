import argparse
import os
import posixpath
import sys

import paramiko


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--host", required=True)
    result.add_argument("--port", type=int, required=True)
    result.add_argument("--user", required=True)
    result.add_argument("--remote-dir", required=True)
    result.add_argument("--archive", required=True)
    result.add_argument("--script", required=True)
    result.add_argument("--mux-script", required=True)
    result.add_argument("--commit", default="manual")
    return result


def connect(args):
    password = os.environ.get("MOT_SSH_PASSWORD", "")
    if not password:
        raise RuntimeError("Missing MOT_SSH_PASSWORD.")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, port=args.port, username=args.user, password=password, timeout=30, banner_timeout=30, auth_timeout=30)
    return client


def run(client, command, timeout=300):
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(out, end="")
    if err:
        print(err, end="", file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"Remote command failed ({code}): {command}")


def upload(sftp, local_path, remote_path):
    print(f"upload {os.path.basename(local_path)} -> {remote_path}")
    sftp.put(local_path, remote_path)


def main():
    args = parser().parse_args()
    remote_archive = posixpath.join(args.remote_dir, "app.tar.gz")
    remote_script = posixpath.join(args.remote_dir, "apply-release.sh")
    remote_mux = posixpath.join(args.remote_dir, "ssh_http_mux.py")

    client = connect(args)
    try:
        run(client, f"mkdir -p {args.remote_dir}", timeout=60)
        sftp = client.open_sftp()
        try:
            upload(sftp, args.archive, remote_archive)
            upload(sftp, args.script, remote_script)
            upload(sftp, args.mux_script, remote_mux)
        finally:
            sftp.close()
        run(client, f"bash {remote_script} {remote_archive} {args.commit}", timeout=600)
    finally:
        client.close()


if __name__ == "__main__":
    main()
