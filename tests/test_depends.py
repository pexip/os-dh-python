import os
import logging
import platform
import unittest
from copy import deepcopy
from pickle import dumps
from tempfile import TemporaryDirectory

from dhpython.depends import Dependencies
from dhpython.version import Version

from tests.common import FakeOptions


def pep386(d):
    """Mark all pydist entries as being PEP386"""
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = {'dependency': v}
            d[k].setdefault('standard', 'PEP386')
    return d


def py27(d):
    """Mark all pydist entries as being for Python 2.7"""
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = {'dependency': v}
            d[k].setdefault('versions', {Version('2.7')})
    return d


def prime_pydist(impl, pydist):
    """Fake the pydist data for impl. Returns a cleanup function"""
    from dhpython.pydist import load

    for name, entries in pydist.items():
        if not isinstance(entries, list):
            pydist[name] = entries = [entries]
        for i, entry in enumerate(entries):
            if isinstance(entry, str):
                entries[i] = entry = {'dependency': entry}
            entry.setdefault('name', name)
            entry.setdefault('standard', '')
            entry.setdefault('rules', [])
            entry.setdefault('versions', set())

    key = dumps(((impl,), {}))
    load.cache[key] = pydist
    return lambda: load.cache.pop(key)


class DependenciesTestCase(unittest.TestCase):
    pkg = 'foo'
    impl = 'cpython3'
    pydist = {}
    stats = {
        'compile': False,
        'dist-info': set(),
        'egg-info': set(),
        'ext_no_version': set(),
        'ext_vers': set(),
        'nsp.txt': set(),
        'private_dirs': {},
        'public_vers': set(),
        'requires.txt': set(),
        'shebangs': set(),
    }
    requires = {}
    dist_info_metadata = {}
    options = FakeOptions()
    parse = True

    def setUp(self):
        self.d = Dependencies(self.pkg, self.impl)

        stats = deepcopy(self.stats)
        write_files = {}
        if self.requires:
            for fn, lines in self.requires.items():
                write_files[fn] = lines
                stats['requires.txt'].add(fn)

        if self.dist_info_metadata:
            for fn, lines in self.dist_info_metadata.items():
                write_files[fn] = lines
                stats['dist-info'].add(fn)

        if write_files:
            self.tempdir = TemporaryDirectory()
            self.addCleanup(self.tempdir.cleanup)
            old_wd = os.getcwd()
            os.chdir(self.tempdir.name)
            self.addCleanup(os.chdir, old_wd)

        for fn, lines in write_files.items():
            os.makedirs(os.path.dirname(fn))
            with open(fn, 'w') as f:
                f.write('\n'.join(lines))

        cleanup = prime_pydist(self.impl, self.pydist)
        self.addCleanup(cleanup)

        if self.parse:
            self.d.parse(stats, self.options)
        else:
            self.prepared_stats = stats

    def assertNotInDepends(self, pkg):
        """Assert that pkg doesn't appear *anywhere* in self.d.depends"""
        for dep in self.d.depends:
            for alt in dep.split('|'):
                alt = alt.strip().split('(', 1)[0].strip()
                if pkg == alt:
                    raise AssertionError(f'{pkg} appears in {alt}')


class TestRequiresCPython3(DependenciesTestCase):
    options = FakeOptions(guess_deps=True)
    pydist = {
        'bar': 'python3-bar',
        'baz': {'dependency': 'python3-baz', 'standard': 'PEP386'},
        'quux': {'dependency': 'python3-quux', 'standard': 'PEP386'},
    }
    requires = {
        'debian/foo/usr/lib/python3/dist-packages/foo.egg-info/requires.txt': (
            'bar',
            'baz >= 1.0',
            'quux',
        ),
    }

    def test_depends_on_bar(self):
        self.assertIn('python3-bar', self.d.depends)

    def test_depends_on_baz(self):
        self.assertIn('python3-baz (>= 1.0)', self.d.depends)


class TestRequiresPyPy(DependenciesTestCase):
    impl = 'pypy'
    options = FakeOptions(guess_deps=True)
    pydist = {
        'bar': 'pypy-bar',
        'baz': {'dependency': 'pypy-baz', 'standard': 'PEP386'},
        'quux': {'dependency': 'pypy-quux', 'standard': 'PEP386'},
    }
    requires = {
        'debian/foo/usr/lib/pypy/dist-packages/foo.egg-info/requires.txt': (
            'bar',
            'baz >= 1.0',
            'quux',
        )
    }

    def test_depends_on_bar(self):
        self.assertIn('pypy-bar', self.d.depends)

    def test_depends_on_baz(self):
        self.assertIn('pypy-baz (>= 1.0)', self.d.depends)


class TestRequiresCompatible(DependenciesTestCase):
    options = FakeOptions(guess_deps=True)
    pydist = {
        'bar': 'python3-bar',
        'baz': {'dependency': 'python3-baz', 'standard': 'PEP386'},
        'qux': {'dependency': 'python3-qux', 'standard': 'PEP386'},
        'quux': {'dependency': 'python3-quux', 'standard': 'PEP386'},
    }
    requires = {
        'debian/foo/usr/lib/python3/dist-packages/foo.egg-info/requires.txt': (
            'bar',
            'baz ~= 1.1',
            'qux == 1.*',
            'quux',
        ),
    }

    def test_depends_on_bar(self):
        self.assertIn('python3-bar', self.d.depends)

    def test_depends_on_baz(self):
        self.assertIn('python3-baz (>= 1.1), python3-baz (<< 2)', self.d.depends)

    def test_depends_on_qux(self):
        self.assertIn('python3-qux (>= 1.0), python3-qux (<< 2)', self.d.depends)


class TestRequiresDistPython3(DependenciesTestCase):
    options = FakeOptions(guess_deps=True)
    pydist = {
        'bar': 'python3-bar',
        'baz': {'dependency': 'python3-baz', 'standard': 'PEP386'},
        'qux': {'dependency': 'python3-qux', 'standard': 'PEP386'},
        'quux': {'dependency': 'python3-quux', 'standard': 'PEP386'},
    }
    dist_info_metadata = {
        'debian/foo/usr/lib/python3/dist-packages/foo.dist-info/METADATA': (
            'Requires-Dist: bar',
            'Requires-Dist: baz >= 1.0',
            'Requires-Dist: qux == 1.*',
            'Requires-Dist: quux ~= 1.1',
        ),
    }

    def test_depends_on_bar(self):
        self.assertIn('python3-bar', self.d.depends)

    def test_depends_on_baz(self):
        self.assertIn('python3-baz (>= 1.0)', self.d.depends)

    def test_depends_on_qux(self):
        self.assertIn('python3-qux (>= 1.0), python3-qux (<< 2)',
                      self.d.depends)

    def test_depends_on_quux(self):
        self.assertIn('python3-quux (>= 1.1), python3-quux (<< 2)',
                      self.d.depends)


class TestEnvironmentMarkersDistInfo(DependenciesTestCase):
    options = FakeOptions(guess_deps=True, depends_section=['feature'])
    pydist = pep386({
        'no_markers': 'python3-no-markers',
        'os_posix': 'python3-os-posix',
        'os_java': 'python3-os-java',
        'sys_platform_linux': 'python3-sys-platform-linux',
        'sys_platform_darwin': 'python3-sys-platform-darwin',
        'platform_machine_x86_64': 'python3-platform-machine-x86-64',
        'platform_machine_mips64': 'python3-platform-machine-mips64',
        'platform_python_implementation_cpython':
            'python3-platform-python-implementation-cpython',
        'platform_python_implementation_jython':
            'python3-platform-python-implementation-jython',
        'platform_release_lt2': 'python3-platform-release-lt2',
        'platform_release_ge2': 'python3-platform-release-ge2',
        'platform_system_linux': 'python3-platform-system-linux',
        'platform_system_windows': 'python3-platform-system-windows',
        'platform_version_lt1': 'python3-platform-version-lt1',
        'platform_version_ge1': 'python3-platform-version-ge1',
        'python_version_ge3': 'python3-python-version-ge3',
        'python_version_gt3': 'python3-python-version-gt3',
        'python_version_lt3': 'python3-python-version-lt3',
        'python_version_lt30': 'python3-python-version-lt30',
        'python_version_lt35': 'python3-python-version-lt35',
        'python_version_le35': 'python3-python-version-le35',
        'python_version_ge27': 'python3-python-version-ge27',
        'python_version_ge35': 'python3-python-version-ge35',
        'python_version_gt35': 'python3-python-version-gt35',
        'python_version_eq35': 'python3-python-version-eq35',
        'python_version_ne35': 'python3-python-version-ne35',
        'python_version_aeq35': 'python3-python-version-aeq35',
        'python_version_ceq35': 'python3-python-version-ceq35',
        'python_version_weq35': 'python3-python-version-weq35',
        'python_version_full_lt300': 'python3-python-version-full-lt300',
        'python_version_full_lt351': 'python3-python-version-full-lt351',
        'python_version_full_le351': 'python3-python-version-full-le351',
        'python_version_full_ge351': 'python3-python-version-full-ge351',
        'python_version_full_ge351a1': 'python3-python-version-full-ge351a1',
        'python_version_full_ge351b1post1':
            'python3-python-version-full-ge351b1post1',
        'python_version_full_gt351': 'python3-python-version-full-gt351',
        'python_version_full_eq351': 'python3-python-version-full-eq351',
        'python_version_full_ne351': 'python3-python-version-full-ne351',
        'python_version_full_aeq351': 'python3-python-version-full-aeq351',
        'python_version_full_ceq351': 'python3-python-version-full-ceq351',
        'python_version_full_weq35': 'python3-python-version-full-weq35',
        'implementation_name_cpython': 'python3-implementation-name-cpython',
        'implementation_name_pypy': 'python3-implementation-name-pypy',
        'implementation_version_lt35': 'python3-implementation-version-lt35',
        'implementation_version_ge35': 'python3-implementation-version-ge35',
        'invalid_marker': 'python3-invalid-marker',
        'extra_feature': 'python3-extra-feature',
        'extra_test': 'python3-extra-test',
        'complex_marker': 'python3-complex-marker',
        'complex_marker_2': 'python3-complex-marker-2',
        'no_markers_2': 'python3-no-markers-2',
    })
    dist_info_metadata = {
        'debian/foo/usr/lib/python3/dist-packages/foo.dist-info/METADATA': (
            "Requires-Dist: no_markers",
            "Requires-Dist: os_posix; (os_name == 'posix')",
            'Requires-Dist: os_java; os_name == "java"',
            "Requires-Dist: sys_platform_linux ; sys_platform == 'linux'",
            "Requires-Dist: sys_platform_darwin;sys_platform == 'darwin'",
            "Requires-Dist: platform_machine_x86_64; "
                "platform_machine == 'x86_64'",
            "Requires-Dist: platform_machine_mips64; "
                "platform_machine == 'mips64'",
            "Requires-Dist: platform_python_implementation_cpython; "
                "platform_python_implementation == 'CPython'",
            "Requires-Dist: platform_python_implementation_jython; "
                "platform_python_implementation == 'Jython'",
            "Requires-Dist: platform_release_lt2; platform_release < '2.0'",
            "Requires-Dist: platform_release_ge2; platform_release >= '2.0'",
            "Requires-Dist: platform_system_linux; platform_system == 'Linux'",
            "Requires-Dist: platform_system_windows; "
                "platform_system == 'Windows'",
            "Requires-Dist: platform_version_lt1; platform_version < '1'",
            "Requires-Dist: platform_version_ge1; platform_version >= '1'",
            "Requires-Dist: python_version_ge3; python_version >= '3'",
            "Requires-Dist: python_version_gt3; python_version > '3'",
            "Requires-Dist: python_version_lt3; python_version < '3'",
            "Requires-Dist: python_version_lt30; python_version < '3.0'",
            "Requires-Dist: python_version_lt35; python_version < '3.5'",
            "Requires-Dist: python_version_le35; python_version <= '3.5'",
            "Requires-Dist: python_version_gt35; python_version > '3.5'",
            "Requires-Dist: python_version_ge27; python_version >= '2.7'",
            "Requires-Dist: python_version_ge35; python_version >= '3.5'",
            "Requires-Dist: python_version_eq35; python_version == '3.5'",
            "Requires-Dist: python_version_ne35; python_version != '3.5'",
            "Requires-Dist: python_version_aeq35; python_version === '3.5'",
            "Requires-Dist: python_version_ceq35; python_version ~= '3.5'",
            "Requires-Dist: python_version_weq35; python_version == '3.5.*'",
            "Requires-Dist: python_version_full_lt300; "
                "python_full_version < '3.0.0'",
            "Requires-Dist: python_version_full_lt351; "
                "python_full_version < '3.5.1'",
            "Requires-Dist: python_version_full_le351; "
                "python_full_version <= '3.5.1'",
            "Requires-Dist: python_version_full_gt351; "
                "python_full_version > '3.5.1'",
            "Requires-Dist: python_version_full_ge351; "
                "python_full_version >= '3.5.1'",
            "Requires-Dist: python_version_full_ge351a1; "
                "python_full_version >= '3.5.1a1'",
            "Requires-Dist: python_version_full_ge351b1post1; "
                "python_full_version >= '3.5.1b1.post1'",
            "Requires-Dist: python_version_full_eq351; "
                "python_full_version == '3.5.1'",
            "Requires-Dist: python_version_full_ne351; "
                "python_full_version != '3.5.1'",
            "Requires-Dist: python_version_full_aeq351; "
                "python_full_version === '3.5.1'",
            "Requires-Dist: python_version_full_ceq351; "
                "python_full_version ~= '3.5.1'",
            "Requires-Dist: python_version_full_weq35; "
                "python_full_version == '3.5.*'",
            "Requires-Dist: implementation_name_cpython; "
                "implementation_name == 'cpython'",
            "Requires-Dist: implementation_name_pypy; "
                "implementation_name == 'pypy'",
            "Requires-Dist: implementation_version_lt35; "
                "implementation_version < '3.5'",
            "Requires-Dist: implementation_version_ge35; "
                "implementation_version >= '3.5'",
            "Requires-Dist: invalid_marker; invalid_marker > '1'",
            "Requires-Dist: extra_feature; extra == 'feature'",
            "Requires-Dist: extra_test; extra == 'test'",
            "Requires-Dist: complex_marker; os_name != 'windows' "
                "and implementation_name == 'cpython'",
            "Requires-Dist: complex_marker_2; (python_version > \"3.4\") "
                "and extra == 'test'",
            "Requires-Dist: no_markers_2",
        ),
    }

    def test_depends_on_unmarked_packages(self):
        self.assertIn('python3-no-markers', self.d.depends)

    def test_depends_on_posix_packages(self):
        self.assertIn('python3-os-posix', self.d.depends)

    def test_skips_non_posix_packages(self):
        self.assertNotInDepends('python3-os-java')

    def test_depends_on_linux_packages(self):
        self.assertIn('python3-sys-platform-linux', self.d.depends)

    def test_skips_darwin_packages(self):
        self.assertNotInDepends('python3-sys-platform-darwin')

    def test_depends_on_x86_64_packages_on_x86_64(self):
        if platform.machine() == 'x86_64':
            self.assertIn('python3-platform-machine-x86-64', self.d.depends)
        else:
            self.assertNotInDepends('python3-platform-machine-x86-64')

    def test_depends_on_mips64_packages_on_mips64(self):
        if platform.machine() == 'mips64':
            self.assertIn('python3-platform-machine-mips64', self.d.depends)
        else:
            self.assertNotInDepends('python3-platform-machine-mips64')

    def test_depends_on_plat_cpython_packages(self):
        self.assertIn('python3-platform-python-implementation-cpython',
                      self.d.depends)

    def test_skips_plat_jython_packages(self):
        self.assertNotInDepends('python3-platform-python-implementation-jython')

    def test_skips_release_lt_2_packages(self):
        self.assertNotInDepends('python3-platform-release-lt2')

    def test_skips_release_gt_2_packages(self):
        self.assertNotInDepends('python3-platform-release-ge2')

    def test_depends_on_platform_linux_packages(self):
        self.assertIn('python3-platform-system-linux', self.d.depends)

    def test_skips_platform_windows_packages(self):
        self.assertNotInDepends('python3-platform-system-windows')

    def test_skips_platfrom_version_lt_1_packages(self):
        self.assertNotInDepends('python3-platform-version-lt1')

    def test_skips_platform_version_ge_1_packages(self):
        self.assertNotInDepends('python3-platform-version-ge1')

    def test_skips_py_version_lt_3_packages(self):
        self.assertNotInDepends('python3-python-version-lt3')

    def test_elides_py_version_ge_3(self):
        self.assertIn('python3-python-version-ge3', self.d.depends)

    def test_elides_py_version_gt_3(self):
        self.assertIn('python3-python-version-gt3', self.d.depends)

    def test_skips_py_version_lt_30_packages(self):
        self.assertNotInDepends('python3-python-version-lt30')

    def test_depends_on_py_version_lt_35_packages(self):
        self.assertIn('python3-python-version-lt35 | python3 (>> 3.5)',
                      self.d.depends)

    def test_depends_on_py_version_le_35_packages(self):
        self.assertIn('python3-python-version-le35 | python3 (>> 3.6)',
                      self.d.depends)

    def test_depends_on_py_version_ge_27_packages(self):
        self.assertIn('python3-python-version-ge27',
                      self.d.depends)

    def test_depends_on_py_version_ge_35_packages(self):
        self.assertIn('python3-python-version-ge35 | python3 (<< 3.5)',
                      self.d.depends)

    def test_depends_on_py_version_gt_35_packages(self):
        self.assertIn('python3-python-version-gt35 | python3 (<< 3.6)',
                      self.d.depends)

    def test_depends_on_py_version_eq_35_packages(self):
        self.assertIn('python3-python-version-eq35 | python3 (<< 3.5) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_depends_on_py_version_ne_35_packages(self):
        # Can't be represented in Debian depends
        self.assertIn('python3-python-version-ne35', self.d.depends)

    def test_depends_on_py_version_aeq_35_packages(self):
        self.assertIn('python3-python-version-aeq35 | python3 (<< 3.5) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_depends_on_py_version_ceq_35_packages(self):
        self.assertIn('python3-python-version-ceq35 | python3 (<< 3.5) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_depends_on_py_version_weq_35_packages(self):
        self.assertIn('python3-python-version-weq35 | python3 (<< 3.5) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_skips_py_version_full_lt_300_packages(self):
        self.assertNotInDepends('python3-python-version-full-lt300')

    def test_depends_on_py_version_full_lt_351_packages(self):
        self.assertIn('python3-python-version-full-lt351 | python3 (>> 3.5.1)',
                      self.d.depends)

    def test_depends_on_py_version_full_le_351_packages(self):
        self.assertIn('python3-python-version-full-le351 | python3 (>> 3.5.2)',
                      self.d.depends)

    def test_depends_on_py_version_full_ge_351_packages(self):
        self.assertIn('python3-python-version-full-ge351 | python3 (<< 3.5.1)',
                      self.d.depends)

    def test_depends_on_py_version_full_ge_351a1_packages(self):
        # With full PEP-440 parsing this should be (<< 3.5.1~a1)
        self.assertIn(
            'python3-python-version-full-ge351a1 | python3 (<< 3.5.0)',
            self.d.depends)

    def test_depends_on_py_version_full_ge_351b1post1_packages(self):
        # With full PEP-440 parsing this should be (<< 3.5.1~b1.post1)
        self.assertIn('python3-python-version-full-ge351a1 '
                      '| python3 (<< 3.5.0)',
                      self.d.depends)

    def test_depends_on_py_version_full_gt_351_packages(self):
        self.assertIn('python3-python-version-full-gt351 | python3 (<< 3.5.2)',
                      self.d.depends)

    def test_depends_on_py_version_full_eq_351_packages(self):
        self.assertIn('python3-python-version-full-eq351 | python3 (<< 3.5.1) '
                      '| python3 (>> 3.5.2)', self.d.depends)

    def test_depends_on_py_version_full_ne_351_packages(self):
        # Can't be represented in Debian depends
        self.assertIn('python3-python-version-full-ne351', self.d.depends)

    def test_skips_py_version_full_aeq_351_packages(self):
        # Can't be represented in Debian depends
        self.assertNotInDepends('python3-python-version-full-aeq351')

    def test_depends_on_py_version_full_ceq_351_packages(self):
        self.assertIn('python3-python-version-full-ceq351 | python3 (<< 3.5.1) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_depends_on_py_version_full_weq_35_packages(self):
        self.assertIn('python3-python-version-full-weq35 | python3 (<< 3.5) '
                      '| python3 (>> 3.6)', self.d.depends)

    def test_depends_on_sys_cpython_packages(self):
        self.assertIn('python3-implementation-name-cpython', self.d.depends)

    def test_depends_on_sys_pypy_packages(self):
        self.assertIn('python3-implementation-name-pypy', self.d.depends)

    def test_depends_on_sys_implementation_lt35_packages(self):
        self.assertIn('python3-implementation-version-lt35 | python3 (>> 3.5)',
                      self.d.depends)

    def test_depends_on_sys_implementation_ge35_packages(self):
        self.assertIn('python3-implementation-version-ge35 | python3 (<< 3.5)',
                      self.d.depends)

    def test_ignores_invalid_marker(self):
        self.assertNotInDepends('python3-invalid-marker')

    def test_depends_on_extra_feature_packages(self):
        self.assertIn('python3-extra-feature', self.d.depends)

    def test_skips_extra_test_packages(self):
        self.assertNotInDepends('python3-extra-test')

    def test_ignores_complex_environment_markers(self):
        self.assertNotInDepends('python3-complex-marker')
        self.assertNotInDepends('python3-complex-marker-2')

    def test_depends_on_un_marked_dependency_after_extra(self):
        self.assertIn('python3-no-markers-2', self.d.depends)


class TestEnvironmentMarkersEggInfo(TestEnvironmentMarkersDistInfo):
    dist_info_metadata = None
    requires = {
        'debian/foo/usr/lib/python3/dist-packages/foo.egg-info/requires.txt': (
            "no_markers",
            "[:(os_name == 'posix')]",
            "os_posix",
            '[:os_name == "java"]',
            "os_java",
            "[:sys_platform == 'linux']",
            "sys_platform_linux",
            "[:sys_platform == 'darwin']",
            "sys_platform_darwin",
            "[:platform_machine == 'x86_64']",
            "platform_machine_x86_64",
            "[:platform_machine == 'mips64']",
            "platform_machine_mips64",
            "[:platform_python_implementation == 'CPython']",
            "platform_python_implementation_cpython",
            "[:platform_python_implementation == 'Jython']",
            "platform_python_implementation_jython",
            "[:platform_release < '2.0']",
            "platform_release_lt2",
            "[:platform_release >= '2.0']",
            "platform_release_ge2",
            "[:platform_system == 'Linux']",
            "platform_system_linux",
            "[:platform_system == 'Windows']",
            "platform_system_windows",
            "[:platform_version < '1']",
            "platform_version_lt1",
            "[:platform_version >= '1']",
            "platform_version_ge1",
            "[:python_version >= '3']",
            "python_version_ge3",
            "[:python_version > '3']",
            "python_version_gt3",
            "[:python_version < '3']",
            "python_version_lt3",
            "[:python_version < '3.0']",
            "python_version_lt30",
            "[:python_version < '3.5']",
            "python_version_lt35",
            "[:python_version <= '3.5']",
            "python_version_le35",
            "[:python_version > '3.5']",
            "python_version_gt35",
            "[:python_version >= '2.7']",
            "python_version_ge27",
            "[:python_version >= '3.5']",
            "python_version_ge35",
            "[:python_version == '3.5']",
            "python_version_eq35",
            "[:python_version != '3.5']",
            "python_version_ne35",
            "[:python_version === '3.5']",
            "python_version_aeq35",
            "[:python_version ~= '3.5']",
            "python_version_ceq35",
            "[:python_version == '3.5.*']",
            "python_version_weq35",
            "[:python_full_version < '3.0.0']",
            "python_version_full_lt300",
            "[:python_full_version < '3.5.1']",
            "python_version_full_lt351",
            "[:python_full_version <= '3.5.1']",
            "python_version_full_le351",
            "[:python_full_version > '3.5.1']",
            "python_version_full_gt351",
            "[:python_full_version >= '3.5.1']",
            "python_version_full_ge351",
            "[:python_full_version >= '3.5.1a1']",
            "python_version_full_ge351a1",
            "[:python_full_version >= '3.5.1b1.post1']",
            "python_version_full_ge351b1post1",
            "[:python_full_version == '3.5.1']",
            "python_version_full_eq351",
            "[:python_full_version != '3.5.1']",
            "python_version_full_ne351",
            "[:python_full_version === '3.5.1']",
            "python_version_full_aeq351",
            "[:python_full_version ~= '3.5.1']",
            "python_version_full_ceq351",
            "[:python_full_version == '3.5.*']",
            "python_version_full_weq35",
            "[:implementation_name == 'cpython']",
            "implementation_name_cpython",
            "[:implementation_name == 'pypy']",
            "implementation_name_pypy",
            "[:implementation_version < '3.5']",
            "implementation_version_lt35",
            "[:implementation_version >= '3.5']",
            "implementation_version_ge35",
            "[:invalid_marker > '1']",
            "invalid_marker",
            "[feature]",
            "extra_feature",
            "[test]",
            "extra_test",
            "[:os_name != 'windows' and implementation_name == 'cpython']",
            "complex_marker",
            "[test:(os_name != 'windows')]",
            "complex_marker_2",
        ),
    }

    def test_depends_on_un_marked_dependency_after_extra(self):
        raise unittest.SkipTest('Not possible in requires.txt')


class TestEnvironmentMarkers27EggInfo(DependenciesTestCase):
    options = FakeOptions(guess_deps=True)
    impl = 'cpython2'
    requires = {
        'debian/foo/usr/lib/python2.7/dist-packages/foo.egg-info/requires.txt': (
            "no_markers",
            "[:os_name == 'posix']",
            "os_posix",
            "[:python_version >= '2.6']",
            "python_version_ge26",
        )
    }
    pydist = py27({
        'no_markers': 'python-no-markers',
        'os_posix': 'python-os-posix',
        'python_version_ge26': 'python-python-version-ge26',
    })

    def test_depends_on_unmarked_packages(self):
        self.assertIn('python-no-markers', self.d.depends)

    def test_ignores_posix_packages(self):
        self.assertNotInDepends('python-os-posix')

    def test_ignores_pyversion_packages(self):
        self.assertNotInDepends('python-python-version-ge26')


class TestIgnoresUnusedModulesDistInfo(DependenciesTestCase):
    options = FakeOptions(guess_deps=True, depends_section=['feature'])
    dist_info_metadata = {
        'debian/foo/usr/lib/python3/dist-packages/foo.dist-info/METADATA': (
            "Requires-Dist: unusued-complex-module ; "
                "(sys_platform == \"darwin\") and extra == 'nativelib'",
            "Requires-Dist: unused-win-module ; (sys_platform == \"win32\")",
            "Requires-Dist: unused-extra-module ; extra == 'unused'",
        ),
    }
    parse = False

    def test_ignores_unused_dependencies(self):
        if not hasattr(self, 'assertLogs'):
            raise unittest.SkipTest("Requires Python >= 3.4")
        with self.assertLogs(logger='dhpython', level=logging.INFO) as logs:
            self.d.parse(self.prepared_stats, self.options)
        for line in logs.output:
            self.assertTrue(
                line.startswith(
                    'INFO:dhpython:Ignoring complex environment marker'),
                'Expecting only complex environment marker messages, but '
                'got: {}'.format(line))


class TestIgnoresUnusedModulesEggInfo(DependenciesTestCase):
    options = FakeOptions(guess_deps=True, depends_section=['feature'])
    requires = {
        'debian/foo/usr/lib/python3/dist-packages/foo.egg-info/requires.txt': (
            "[nativelib:(sys_platform == 'darwin')]",
            "unusued-complex-module",
            "[:sys_platform == 'win32']",
            "unused-win-module",
            "[unused]",
            "unused-extra-module",
        )
    }
    parse = False

    def test_ignores_unused_dependencies(self):
        if not hasattr(self, 'assertNoLogs'):
            raise unittest.SkipTest("Requires Python >= 3.10")
        with self.assertNoLogs(logger='dhpython', level=logging.INFO):
            self.d.parse(self.prepared_stats, self.options)
