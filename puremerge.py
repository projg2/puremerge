#!/usr/bin/env python3

import argparse
import os
import shlex
import subprocess
import sys

from portage import create_trees, VERSION
from portage.dep import use_reduce


def main(argv):
    argp = argparse.ArgumentParser(
        description='Test-build specified package with absolutely '
                    'minimal number of non-dependency packages installed',
        epilog='WARNING: This tool will bulldoze your system.  Use '
               'in a dedicated chroot only!')
    argp.add_argument('--emerge-opts', default='--jobs',
                      help='emerge(1) options to use (default: --jobs)')
    argp.add_argument('-p', '--pretend', action='store_true',
                      help='only print what would be done')
    argp.add_argument('package',
                      help='package specification to build and install')
    args = argp.parse_args(argv)

    def run_command(cmd, env={}):
        print(' '.join(shlex.quote(x) for x
                       in [f'{k}={v}' for k, v in env.items()] + cmd))
        if not args.pretend:
            kwargs = {}
            if env:
                kwargs['env'] = dict(os.environ)
                kwargs['env'].update(env)
            subprocess.check_call(cmd, **kwargs)

    trees = create_trees()
    tree = trees[max(trees)]
    repos = tree['porttree'].dbapi
    vdb = tree['vartree']
    emerge_opts = shlex.split(args.emerge_opts)

    print('[1] Installing build-time dependencies ...\n')
    run_command(['emerge', '-v', '--ask=n', '--onlydeps',
                 '--onlydeps-with-rdeps=n']
                + emerge_opts + [args.package])

    print('\n[2] Updating world file with dependencies ...\n')
    m = repos.xmatch('bestmatch-visible', args.package)
    deps = repos.aux_get(m, ['DEPEND', 'BDEPEND'])
    depset = set()
    for dep_group in deps:
        depset.update(x
                      for x in use_reduce(dep_group,
                                          matchall=True,
                                          flat=True)
                      if x != '||')
    matches = set(vdb.dep_bestmatch(x) for x in depset)
    matches.discard('')

    if args.pretend:
        print('Note: --pretend mode works correctly only for installed deps')
        print('New world contents:')
        print('\n'.join(f'={x}' for x in matches))
    else:
        world_path = '/var/lib/portage/world'
        backup_path = world_path + '.puremerge-backup'
        try:
            if not os.path.exists(backup_path):
                os.rename(world_path, backup_path)
            else:
                os.unlink(world_path)
        except FileNotFoundError:
            pass
        with open(world_path, 'w') as f:
            f.write(''.join(f'={x}\n' for x in matches))

    print('\n[3] Cleaning up remaining packages ...\n')
    run_command(['emerge', '--depclean', '--ask=n', '--with-bdeps=n'])

    print('\n[4] Building the package itself\n')
    run_command(['emerge', '-1v', '--ask=n', '--buildpkgonly']
                 + emerge_opts + [args.package],
                env={'FEATURES': 'test'})

    print('\n[5] Installing the package\n')
    run_command(['emerge', '-1v', '--ask=n', '--usepkgonly']
                 + emerge_opts + [args.package])

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
