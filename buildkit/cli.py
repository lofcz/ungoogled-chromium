#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# Copyright (c) 2018 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
buildkit: A small helper utility for building ungoogled-chromium.

This is the CLI interface. Available commands each have their own help; pass in
-h or --help after a command.

buildkit has optional environment variables. They are as follows:

* BUILDKIT_RESOURCES - Path to the resources/ directory. Defaults to
the one in buildkit's parent directory.
"""

import argparse
from pathlib import Path

from . import config
from . import source_retrieval
from .common import CONFIG_BUNDLES_DIR, get_resources_dir, get_logger
from .config import ConfigBundle

class _MainArgumentParserFormatter(argparse.RawTextHelpFormatter,
                                   argparse.ArgumentDefaultsHelpFormatter):
    """Custom argparse.HelpFormatter for the main argument parser"""
    pass

class _CLIError(RuntimeError):
    """Custom exception for printing argument parser errors from callbacks"""
    pass

class _NewBaseBundleAction(argparse.Action): #pylint: disable=too-few-public-methods
    """argparse.ArgumentParser action handler with more verbose logging"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.type:
            raise ValueError('Cannot define action with action %s', type(self).__name__)
        if self.nargs and self.nargs > 1:
            raise ValueError('nargs cannot be greater than 1')

    def __call__(self, parser, namespace, values, option_string=None):
        try:
            base_bundle = ConfigBundle.from_base_name(values)
        except NotADirectoryError as exc:
            get_logger().error('resources/ or resources/patches directories could not be found.')
            parser.exit(status=1)
        except FileNotFoundError:
            get_logger().error('The base config bundle "%s" does not exist.', values)
            parser.exit(status=1)
        except ValueError as exc:
            get_logger().error('Base bundle metadata has an issue: %s', exc)
            parser.exit(status=1)
        except Exception as exc: #pylint: disable=broad-except
            get_logger().exception('Unexpected exception caught.')
            parser.exit(status=1)
        setattr(namespace, self.dest, base_bundle)

def setup_bundle_group(parser):
    """Helper to add arguments for loading a config bundle to argparse.ArgumentParser"""
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        '-b', '--base-bundle-name', dest='bundle', default=argparse.SUPPRESS,
        action=_NewBaseBundleAction,
        help=('The base config bundle name to use (located in resources/config_bundles). '
              'Mutually exclusive with --user-bundle-path. '
              'Default value is nothing; a default is specified by --user-bundle-path.'))
    config_group.add_argument(
        '-u', '--user-bundle-path', dest='bundle', default='buildspace/user_bundle',
        type=lambda x: ConfigBundle(Path(x)),
        help=('The path to a user bundle to use. '
              'Mutually exclusive with --base-bundle-name. '))

def _add_bunnfo(subparsers):
    """Gets info about base bundles."""
    def _callback(args):
        if vars(args).get('list'):
            for bundle_dir in sorted(
                    (get_resources_dir() / CONFIG_BUNDLES_DIR).iterdir()):
                bundle_meta = config.BaseBundleMetaIni(
                    bundle_dir / config.BASEBUNDLEMETA_INI)
                print(bundle_dir.name, '-', bundle_meta.display_name)
        elif vars(args).get('bundle'):
            for dependency in args.bundle.get_dependencies():
                print(dependency)
        else:
            raise NotImplementedError()
    parser = subparsers.add_parser(
        'bunnfo', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=_add_bunnfo.__doc__, description=_add_bunnfo.__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-l', '--list', action='store_true',
        help='Lists all base bundles and their display names.')
    group.add_argument(
        '-d', '--dependencies', dest='bundle',
        action=_NewBaseBundleAction,
        help=('Prints the dependency order of the given base bundle, '
              'delimited by newline characters. '
              'See DESIGN.md for the definition of dependency order.'))
    parser.set_defaults(callback=_callback)

def _add_genbun(subparsers):
    """Generates a user config bundle from a base config bundle."""
    def _callback(args):
        try:
            args.base_bundle.write(args.user_bundle_path)
        except FileExistsError:
            get_logger().error('User bundle already exists: %s', args.user_bundle_path)
            raise _CLIError()
        except ValueError as exc:
            get_logger().error('Error with base bundle: %s', exc)
            raise _CLIError()
        except Exception as exc:
            get_logger().exception('Unexpected exception caught.')
            raise _CLIError()
    parser = subparsers.add_parser(
        'genbun', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=_add_genbun.__doc__, description=_add_genbun.__doc__)
    parser.add_argument(
        '-u', '--user-bundle-path', type=Path, default='buildspace/user_bundle',
        help=('The output path for the user config bundle. '
              'The path must not already exist. '))
    parser.add_argument(
        'base_bundle', action=_NewBaseBundleAction,
        help='The base config bundle name to use.')
    parser.set_defaults(callback=_callback)

def _add_getsrc(subparsers):
    """Downloads, checks, and unpacks the necessary files into the buildspace tree"""
    def _callback(args):
        try:
            source_retrieval.retrieve_and_extract(
                args.bundle, args.downloads, args.tree, prune_binaries=args.prune_binaries,
                show_progress=args.show_progress)
        except FileExistsError:
            get_logger().error('Buildspace tree already exists: %s', args.tree)
            raise _CLIError()
        except FileNotFoundError:
            get_logger().error('Buildspace downloads does not exist: %s', args.downloads)
            raise _CLIError()
        except NotADirectoryError:
            get_logger().error('Buildspace downloads is not a directory: %s', args.downloads)
            raise _CLIError()
        except source_retrieval.NotAFileError as exc:
            get_logger().error('Archive path is not a regular file: %s', exc)
            raise _CLIError()
        except source_retrieval.HashMismatchError as exc:
            get_logger().error('Archive checksum is invalid: %s', exc)
            raise _CLIError()
        except Exception as exc:
            get_logger().exception('Unexpected exception caught.')
            raise _CLIError()
    parser = subparsers.add_parser(
        'getsrc', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=_add_getsrc.__doc__ + '.', description=_add_getsrc.__doc__ + '; ' + (
            'these are the Chromium source code and any extra dependencies. '
            'By default, binary pruning is performed during extraction. '
            'The buildspace/downloads directory must already exist for storing downloads. '
            'If the buildspace tree already exists or there is a checksum mismatch, '
            'this command will abort. '
            'Only files that are missing will be downloaded. '
            'If the files are already downloaded, their checksums are '
            'confirmed and unpacked if necessary.'))
    setup_bundle_group(parser)
    parser.add_argument(
        '-t', '--tree', type=Path, default='buildspace/tree',
        help='The buildspace tree path')
    parser.add_argument(
        '-d', '--downloads', type=Path, default='buildspace/downloads',
        help='Path to store archives of Chromium source code and extra deps.')
    parser.add_argument(
        '--disable-binary-pruning', action='store_false', dest='prune_binaries',
        help='Disables binary pruning during extraction.')
    parser.add_argument(
        '--hide-progress-bar', action='store_false', dest='show_progress',
        help='Hide the download progress.')
    parser.set_defaults(callback=_callback)

def _add_prubin(subparsers):
    """Prunes binaries from the buildspace tree."""
    parser = subparsers.add_parser(
        'prubin', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=_add_prubin.__doc__, description=_add_prubin.__doc__ + (
            ' This is NOT necessary if the source code was already pruned '
            'during the getsrc command.'))
    setup_bundle_group(parser)

def _add_subdom(subparsers):
    """Substitutes domain names in buildspace tree with blockable strings."""
    parser = subparsers.add_parser(
        'subdom', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help=_add_subdom.__doc__, description=_add_subdom.__doc__ + (
            ' By default, it will substitute the domains on both the buildspace tree and '
            'the bundle\'s patches.'))
    setup_bundle_group(parser)
    parser.add_argument(
        '-o', '--only', choices=['tree', 'patches'],
        help=('Specifies a component to exclusively apply domain substitution to. '
              '"tree" is for the buildspace tree, and "patches" is for the bundle\'s patches.'))

def _add_genpkg(subparsers):
    """Generates a packaging script."""
    parser = subparsers.add_parser(
        'genpkg', formatter_class=argparse.ArgumentDefaultsHelpFormatter, help=_add_genpkg.__doc__,
        description=_add_genpkg.__doc__ + ' Specify no arguments to get a list of different types.')
    setup_bundle_group(parser)
    parser.add_argument(
        '-o', '--output-path', type=Path, default='buildspace/tree/ungoogled_packaging',
        help=('The directory to store packaging files. '
              'If it does not exist, just the leaf directory will be created. '
              'If it already exists, this command will abort. '))

def main(arg_list=None):
    """CLI entry point"""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=_MainArgumentParserFormatter)

    subparsers = parser.add_subparsers(title='Available commands', dest='command')
    subparsers.required = True # Workaround for http://bugs.python.org/issue9253#msg186387
    _add_bunnfo(subparsers)
    _add_genbun(subparsers)
    _add_getsrc(subparsers)
    _add_prubin(subparsers)
    _add_subdom(subparsers)
    _add_genpkg(subparsers)

    args = parser.parse_args(args=arg_list)
    try:
        args.callback(args=args)
    except _CLIError:
        parser.exit(status=1)