from pathlib import Path
import re
from setuptools import setup

ROOT = Path(__file__).resolve().parent

verstr = "unknown"
try:
    parentdir = str(ROOT) + '/'
    verstrline = open(parentdir + '/src/ntt/_version.py', "rt").read()
except EnvironmentError:
    pass  # Okay, there is no version file.
else:
    VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
    mo = re.search(VSRE, verstrline, re.M)
    if mo:
        verstr = mo.group(1)
    else:
        raise RuntimeError("unable to find version in " +
                           parentdir + "+src/ntt/_version.py")


setup(
    name='ntt',
    version=verstr,
    author='S. Valenti',
    author_email='stefano.valenti@oapd.inaf.it',
    scripts=['bin/PESSTOEFOSC1dSPEC', 'bin/PESSTOFASTSPEC',
                 'bin/PESSTOSOFI2dSPEC', 'bin/PESSTOEFOSC2dSPEC',
                 'bin/PESSTO', 'bin/PESSTOSOFIPHOT',
                 'bin/PESSTOEFOSCPHOT', 'bin/PESSTOSOFI1dSPEC',
                 'bin/PESSTOWISE', 'bin/PESSTOASTRO',
                 'bin/vizquery'],
    url='ftp.oapd.inaf.it',
    license='LICENSE.txt',
    description='NTT is a package to reduce efosc and sofi data',
    long_description=open('README.txt').read(),
    # ext_modules = [('standard',
    #   { 'include_dirs': ['standard'] }
    #  )]
    python_requires='>=3.11',
    install_requires=['numpy>=1.26,<2', 'astropy>=6,<7', 'scipy>=1.11,<1.15',
                      'matplotlib>=3.8,<3.10', 'pyraf==2.2.4'],
    packages=['ntt'],
    package_dir={'': 'src'},
    # include_package_data=True,
    package_data={'ntt' : ["standard/MAB/*", "standard/ident/*", "standard/cat/*", "standard/extinction/*",\
                           "standard/fits/*", "standard/sex/*", "standard/stdlist/*", "standard/flux/*",\
                           "archive/efosc/badpixels/*", "archive/efosc/arc/*/*/*/*fits", "archive/efosc/arc/*/*/*/*/id*",\
                           "archive/efosc/flat/*/*fits", "archive/efosc/sens/*/*/*fits", "archive/efosc/bias/*fits",\
                           "archive/sofi/illumination/*/*fits", "archive/sofi/flat/*/*fits",\
                           "archive/efosc/fringing/*/*fits", "archive/sofi/arc/*/*/*/*fits", "archive/sofi/arc/*/*/*/*/id*"]}
    #    data_files = [('',["standard/*.txt"])]
)
