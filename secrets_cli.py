#!/usr/bin/python3
"""Manage encrypted credentials (#22). Run through compose:

    docker compose run --rm secrets set bw_master_password   # prompts
    ... | docker compose run --rm -T secrets set bw_clientsecret   # piped
    docker compose run --rm secrets list
    docker compose run --rm secrets check
    docker compose run --rm secrets remove bw_clientsecret

Values are never printed."""
import argparse
import getpass
import sys

import credentials
import hostpath
import stdin_value


def read_value(name):
    if sys.stdin.isatty():
        first = getpass.getpass('Value for {0}: '.format(name))
        if getpass.getpass('Again: ') != first:
            raise ValueError('The two entries differ; nothing stored')
        if not first:
            raise ValueError('Nothing entered; nothing stored')
        return first
    return stdin_value.read(sys.stdin)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='secrets',
                                     description='Manage encrypted credentials.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('set', help='store a credential (from stdin, or a prompt)')
    p.add_argument('name')
    sub.add_parser('list', help='list stored credentials')
    p = sub.add_parser('check', help='check credentials can be decrypted')
    p.add_argument('names', nargs='*')
    p = sub.add_parser('remove', help='delete a credential')
    p.add_argument('name')
    args = parser.parse_args(argv)

    try:
        if args.command == 'set':
            credentials.check_name(args.name)
            credentials.put(args.name, read_value(args.name))
            print('Stored {0} in {1}'.format(args.name, hostpath.join(
                credentials.secrets_dir(), args.name + '.enc')))
        elif args.command == 'list':
            for name in credentials.names():
                print(name)
        elif args.command == 'check':
            failed = False
            for name in args.names or credentials.names():
                try:
                    ok = credentials.get(name) is not None
                    print('{0}: {1}'.format(name, 'ok' if ok else 'not set'))
                    failed |= not ok
                except RuntimeError as exc:
                    print('{0}: {1}'.format(name, exc))
                    failed = True
            return 1 if failed else 0
        elif args.command == 'remove':
            if credentials.remove(args.name):
                print('Removed {0}'.format(args.name))
            else:
                print('{0} was not set'.format(args.name))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
