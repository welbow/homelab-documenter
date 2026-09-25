#!/usr/bin/python3

import argparse
import sys

import pipeline

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate the homelab packet.')
    parser.add_argument('--skip', action='append', default=[],
                        metavar='PLUGINS',
                        help='plugins to skip for this run, by number, '
                             'directory or class name (comma-separated or '
                             'repeated); added to SKIP_PLUGINS')
    args = parser.parse_args()
    sys.exit(pipeline.main(skip=args.skip))
