# Copyright © 2012-2020 Piotr Ożarowski <piotr@debian.org>
#           © 2020 Scott Kitterman <scott@kitterman.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from fnmatch import fnmatch
from pathlib import Path
import csv
import logging
import os
import os.path as osp
import shutil
try:
    import tomli
except ModuleNotFoundError:
    # Plugin still works, only needed for autodetection
    pass
try:
    from flit.install import Installer
except ImportError:
    Installer = object

from dhpython.build.base import Base, shell_command

log = logging.getLogger('dhpython')


class DebianInstaller(Installer):
    def install_directly(self, destdir, installdir):
        """Install a module/package into package directory, and create its
           scripts.
        """
        if installdir[:1] == os.sep:
            installdir = installdir[1:]
        dirs = self._get_dirs(user=self.user)
        dirs['purelib'] = osp.join(destdir, installdir)
        dirs['scripts'] = destdir + dirs['scripts']
        os.makedirs(dirs['purelib'], exist_ok=True)
        os.makedirs(dirs['scripts'], exist_ok=True)

        dst = osp.join(dirs['purelib'], osp.basename(self.module.path))
        if osp.lexists(dst):
            if osp.isdir(dst) and not osp.islink(dst):
                shutil.rmtree(dst)
            else:
                os.unlink(dst)

        src = str(self.module.path)
        if self.module.is_package:
            log.info("Installing package %s -> %s", src, dst)
            shutil.copytree(src, dst)
            self._record_installed_directory(dst)
        else:
            log.info("Installing file %s -> %s", src, dst)
            shutil.copy2(src, dst)
            self.installed_files.append(dst)

        scripts = self.ini_info.entrypoints.get('console_scripts', {})
        if scripts:
            log.info("Installing scripts to %s", dirs['scripts'])
            self.install_scripts(scripts, dirs['scripts'])

        log.info("Writing dist-info %s", dirs['purelib'])
        self.write_dist_info(dirs['purelib'])
        # Remove direct_url.json - contents are not useful or reproduceable
        for path in Path(dirs['purelib']).glob("*.dist-info/direct_url.json"):
            path.unlink()
        # Remove build path from RECORD files
        for path in Path(dirs['purelib']).glob("*.dist-info/RECORD"):
            with open(path) as f:
                reader = csv.reader(f)
                records = list(reader)
            with open(path, 'w') as f:
                writer = csv.writer(f)
                for path, hash_, size in records:
                    path = path.replace(destdir, '')
                    if fnmatch(path, "*.dist-info/direct_url.json"):
                        continue
                    writer.writerow([path, hash_, size])


class BuildSystem(Base):
    DESCRIPTION = 'Flit build system'
    SUPPORTED_INTERPRETERS = {'python3', 'python{version}'}
    REQUIRED_FILES = ['pyproject.toml']
    OPTIONAL_FILES = {}
    CLEAN_FILES = Base.CLEAN_FILES | {'build'}

    def detect(self, context):
        """Return certainty level that this plugin describes the right build
        system

        This method uses cls.{REQUIRED}_FILES (pyroject.toml) as well as
        checking to see if build-backend is set to flit_core.buildapi.

        Score is 85 if both are present (to allow manually setting distutils to
        score higher if set).

        :return: 0 <= certainty <= 100
        :rtype: int
        """
        if Installer is object:
            return 0

        result = super().detect(context)
        try:
            with open('pyproject.toml', 'rb') as f:
                pyproject = tomli.load(f)
            if pyproject.get('build-system', {}).get('build-backend') == \
                    'flit_core.buildapi':
                result += 35
            else:
                # Not a flit built package
                result = 0
        except NameError:
            # No toml, no autdetection
            result = 0
        except FileNotFoundError:
            # Not a pep517 package
            result = 0
        if result > 100:
            return 100
        return result

    def clean(self, context, args):
        super().clean(context, args)
        if osp.exists(args['interpreter'].binary()):
            log.debug("removing '%s' (and everything under it)",
                      args['build_dir'])
            osp.isdir(args['build_dir']) and shutil.rmtree(args['build_dir'])
        return 0  # no need to invoke anything

    def configure(self, context, args):
        # Flit does not support binary extensions
        return 0  # Not needed for flit

    def build(self, context, args):
        my_dir = Path(args['dir'])
        install_kwargs = {'user': False, 'symlink': False, 'deps': 'none'}
        DebianInstaller.from_ini_path(my_dir / 'pyproject.toml',
                                      **install_kwargs).install_directly(
                                          args['build_dir'], '')
        # These get byte compiled too, although it's not logged.
        return 0  # Not needed for flit

    def install(self, context, args):
        my_dir = Path(args['dir'])
        install_kwargs = {'user': False, 'symlink': False, 'deps': 'none'}
        DebianInstaller.from_ini_path(my_dir / 'pyproject.toml',
                                      **install_kwargs).install_directly(
                                          args['destdir'],
                                          args['install_dir'])
        return 0  # Not needed for flit'

    @shell_command
    def test(self, context, args):
        return super().test(context, args)
