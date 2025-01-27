"""CountESS Project"""

from pathlib import Path

from setuptools import setup

from countess import VERSION

long_description = (Path(__file__).parent / "README.md").read_text()


setup(
        name = 'countess',
        version = VERSION,
        author = 'CountESS Developers',
        maintainer = 'Nick Moore',
        maintainer_email = 'nick@zoic.org',
        packages = [ 'countess', 'countess.utils', 'countess.plugins', 'countess.core',
                    'countess.gui' ],
        entry_points = {
            'countess_plugins': [
                'load_fastq = countess.plugins.fastq:LoadFastqPlugin',
                'load_hdf = countess.plugins.hdf5:LoadHdfPlugin',
                'load_csv = countess.plugins.csv:LoadCsvPlugin',
                'log_score = countess.plugins.log_score:LogScorePlugin',
                'group_by = countess.plugins.group_by:GroupByPlugin',
                'embed_py = countess.plugins.embed_python:EmbeddedPythonPlugin',
                'pivot = countess.plugins.pivot:DaskPivotPlugin',
                'join = countess.plugins.join:DaskJoinPlugin',
                'save_csv = countess.plugins.csv:SaveCsvPlugin',
                'regex_tool = countess.plugins.regex:RegexToolPlugin',
                'regex_reader = countess.plugins.regex:RegexReaderPlugin',
            ],
            'gui_scripts': ['countess_gui = countess.gui.main:main'],
            'console_scripts': [ 'countess_cmd = countess.core.cmd:main'],
        },
        python_requires = '>=3.10',
        install_requires = [
            'dask>=2022.8.0',
            'distributed>=2022.8.0',
            'fqfa~=1.2.3',
            'more_itertools>=8.14.0',
            'numpy~=1.23',
            'pandas~=1.4',
            'tables~=3.7',
            'ttkthemes~=3.2',
        ],
        extras_require = {
            'dev': [
                'black<24',
                'mypy~=1.0.1',
                'pylint~=2.16',
                'types-ttkthemes~=3.2',
            ]
        },
        license = 'BSD',
        license_files = ('LICENSE.txt',),
        classifiers = [
            'Development Status :: 2 - Pre-Alpha',
            'Intended Audience :: Science/Research',
            'License :: OSI Approved :: BSD License',
            'Operating System :: OS Independent',
            'Topic :: Scientific/Engineering :: Bio-Informatics',
        ],
        long_description = long_description,
        long_description_content_type = "text/markdown",
)
