#!/usr/bin/python3

import argparse
import os
import sys

import delivery
import password_stdin
import pipeline
import vars

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate the homelab packet, then preview it (the '
                    'default) or export it.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preview', action='store_true',
                      help='serve the page on this machine until Ctrl-C '
                           '(the default)')
    mode.add_argument('--export', metavar='DIR',
                      help='copy the page and the files in output/ into DIR '
                           '(e.g. a USB stick); the only durable copy')
    parser.add_argument('--force', action='store_true',
                        help='export even if plugins were skipped')
    parser.add_argument('--require-mount', action='store_true',
                        help='refuse to export unless DIR is a mount point '
                             '(used by the compose build service)')
    parser.add_argument('--skip', action='append', default=[],
                        metavar='PLUGINS',
                        help='plugins to skip for this run, by number, '
                             'directory or class name (comma-separated or '
                             'repeated); added to SKIP_PLUGINS')
    parser.add_argument('--password-stdin', action='store_true',
                        help='read the Bitwarden master password from '
                             'standard input (one line), e.g. piped from '
                             'scripts/bw-password.ps1')
    args = parser.parse_args()

    bw_password = None
    if args.password_stdin:
        try:
            bw_password = password_stdin.read(sys.stdin)
        except ValueError as exc:
            parser.error(str(exc))

    status = pipeline.main(skip=args.skip, bw_password=bw_password)
    if status != 0 or vars.page is None:
        sys.exit(status or 1)

    extras_dir = os.path.join(vars.data_dir, 'output')
    if args.export:
        ok = delivery.export(vars.page, extras_dir, args.export,
                             skipped=vars.skipped, force=args.force,
                             require_mount=args.require_mount)
        sys.exit(0 if ok else 2)

    delivery.preview(vars.page, extras_dir,
                     host=os.environ.get('PREVIEW_HOST', '127.0.0.1'),
                     port=int(os.environ.get('PREVIEW_PORT', '8000')))
