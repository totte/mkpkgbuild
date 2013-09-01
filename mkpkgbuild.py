#!/usr/bin/env python3

# mkpkgbuild - An interactive utility to create PKGBUILDs
# Copyright (c) 2013 H W Tovetjärn (totte) <totte@tott.es>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program, see LICENSE in the root of the project directory.
# If not, see <http://www.gnu.org/licenses/>.

# TODO Download and read _hkgname.cabal file instead of scraping
# TODO Read .mkpkgbuild.conf for maintainer* data
# TODO Read .PKGBUILD.template and .pkgname.install.template for template data
# TODO 'haskell-hasktags' replaces 'hasktags'
# TODO 'haskell-cabal-install' replaces 'cabal-install'
# TODO 'xmonad' optdepends=('xorg-xmessage: for displaying visual error messages')
# TODO If entered pkgver != previous pkgver, pkgrel is to default to 1
# TODO Should '1.*' be interpreted as '>=1.0' and '<2.0' instead of only the former?

import os
import datetime
import urllib.request
import shutil
import hashlib
from bs4 import BeautifulSoup as bs


PKGBUILD_TEMPLATE = """# {repository} Packages for Chakra, part of www.chakra-project.org
# Maintainer: {maintainer_name} ({maintainer_alias}) <{maintainer_email}>
# Contributors: Stephen McIntosh <stephenmac7[at]gmail[dot]com>
#               Thomas Dziedzic <gostrc@gmail.com>
#               Vesa Kaihlavirta <vesa@archlinux.org>
#               Arch Haskell Team <arch-haskell@haskell.org>

_hkgname={_hkgname}
pkgname={pkgname}
pkgver={pkgver}
pkgrel={pkgrel}
pkgdesc="{pkgdesc}"
url="http://hackage.haskell.org/package/{_hkgname}"
license=('{license}')
arch=({arch})
makedepends=({makedepends})
depends=({depends})
options=({options})
source=("http://hackage.haskell.org/packages/archive/\
{_hkgname}/{pkgver}/{_hkgname}-{pkgver}.tar.gz")
install="{pkgname}.install"
sha512sums=('{checksum}')

build() {{
    cd "${{srcdir}}/{_hkgname}-{pkgver}"
    runhaskell Setup configure \\
        -O \\
        ${{PKGBUILD_HASKELL_ENABLE_PROFILING:+-p }} \\
        --enable-split-objs \\
        --enable-shared \\
        --prefix="/usr" \\
        --docdir="/usr/share/doc/{pkgname}" \\
        --libsubdir='$compiler/site-local/$pkgid'
    runhaskell Setup build
    runhaskell Setup haddock
    runhaskell Setup register   --gen-script
    runhaskell Setup unregister --gen-script
    sed -i -r -e "s|ghc-pkg.*unregister[^ ]* |&'--force' |" unregister.sh
}}

package() {{
    cd "${{srcdir}}/{_hkgname}-{pkgver}"
    install -D -m744 register.sh \\
        "${{pkgdir}}/usr/share/haskell/{pkgname}/register.sh"
    install -m744 unregister.sh \\
        "${{pkgdir}}/usr/share/haskell/{pkgname}/unregister.sh"
    install -d -m755 "${{pkgdir}}/usr/share/doc/ghc/html/libraries"

    # Documentation
    ln -s "/usr/share/doc/{pkgname}/html" \\
        "${{pkgdir}}/usr/share/doc/ghc/html/libraries/{_hkgname}"

    # License
    install -D -m644 LICENSE \\
        "${{pkgdir}}/usr/share/licenses/{pkgname}/LICENSE"
    rm -f "${{pkgdir}}/usr/share/doc/{pkgname}/LICENSE"

    runhaskell Setup copy --destdir="${{pkgdir}}"
}}
"""

INSTALL_TEMPLATE = """HS_DIR=usr/share/haskell/{pkgname}

#pre_install() {{
#  echo "insert pre_install routine here"
#}}

post_install() {{
  ${{HS_DIR}}/register.sh
  (cd usr/share/doc/ghc/html/libraries; ./gen_contents_index)
}}

pre_upgrade() {{
  ${{HS_DIR}}/unregister.sh
}}

post_upgrade() {{
  ${{HS_DIR}}/register.sh
  (cd usr/share/doc/ghc/html/libraries; ./gen_contents_index)
}}

pre_remove() {{
  ${{HS_DIR}}/unregister.sh
}}

post_remove() {{
  (cd usr/share/doc/ghc/html/libraries; ./gen_contents_index)
}}
"""

# TODO Make this inputable
GHC_INSTALLED_VERSION = "7.6.3-1"

# For debug/testing purposes
PACKAGES = ('transformers',
            'mtl',
            'text',
            'parsec',
            'network',
            'random',
            'zlib',
            'utf8-string',
            'extensible-exceptions',
            'terminfo',
            'haskeline',
            'mmap',
            'dataenc',
            'hashed-storage',
            'hslogger',
            'html',
            'HTTP',
            'primitive',
            'regex-base',
            'regex-posix',
            'regex-compat',
            'syb',
            'tar',
            'vector',
            'bytestring-show',
            'X11',
            'X11-xft',
            'cabal-install',
            'hasktags',
            'xmonad',
            'xmonad-contrib',
            'xmonad-utils')


class CancelledError(Exception): pass


def main():                           
    print("mkpkgbuild - From Hackage to Package!\n")
    information = dict(date             = datetime.date.today().isoformat(),
                       repository       = "Apps",
                       maintainer_name  = "H W Tovetjärn",
                       maintainer_alias = "totte",
                       maintainer_email = "totte@tott.es",
                       _hkgname         = None,
                       pkgname          = None,
                       pkgver           = None,
                       pkgrel           = None,
                       pkgdesc          = None,
                       arch             = None,
                       #url              = None,
                       license          = None,
                       groups           = None,
                       depends          = None,
                       optdepends       = None,
                       makedepends      = None,
                       checkdepends     = None,
                       provides         = None,
                       conflicts        = None,
                       replaces         = None,
                       options          = None,
                       #install          = None,
                       #changelog        = None,
                       #source           = None,
                       checksum         = None)

    while True:
        try:
            get_information(information)
            create_directory(information['pkgname'])
            write_pkgbuild(**information)
            write_install(**information)
        except CancelledError:
            print("Cancelled.")
        if (get_string("\nCreate another? (y/n)", default='y').lower()
                not in {'y', 'yes'}):
            break


def hashfile(filename, hasher, blocksize=65536):
    filebuffer = filename.read(blocksize)
    while len(filebuffer) > 0:
        hasher.update(filebuffer)
        filebuffer = filename.read(blocksize)
    return hasher.hexdigest()


# Return license
def scrape_license(url, match):
    with urllib.request.urlopen(url) as response:
        page = response.read()
        text = page.decode('utf-8')
        soup = bs(text)
        return soup.find('th', text=match).next_sibling.string


# Return latest version
def scrape_version(url, match):
    with urllib.request.urlopen(url) as response:
        page = response.read()
        text = page.decode('utf-8')
        soup = bs(text)
        one = soup.find('th', text=match).next_sibling
        return one.b.string


# Return dependencies for latest version
# TODO Return as lowercase
def scrape_dependencies(url):
    with urllib.request.urlopen(url) as response:
        page = response.read()
        text = page.decode('utf-8')
        soup = bs(text)

        result_dictionary = dict(ghc = '=' + GHC_INSTALLED_VERSION)

        # TODO Merge these somehow
        one = soup.find('th', text='Dependencies').next_sibling
        two = str(one).split(sep=' <b>or</b><br/>')
        three = two[-1]
        four = bs(three)
        dependencies = four.text.split(sep=', ')

        # # Debug
        # dependencies.append('foo (1.0)')
        # print("dependencies: ", dependencies, "\n")

        for d in dependencies:
            key, sep, value = d.partition(' ')
            key = key.strip()

            # For Haskell packages
            key = 'haskell-' + key

            if not sep:
                result_dictionary[key] = None

            value = value.strip('()').replace('≤', '<=').replace('≥', '>=')

            if value:
                if ' & ' in value:
                    min_value, sep, max_value = value.partition(' & ')
                    for m in [min_value, max_value]:
                        if '*' in m:
                            m = '>=' + m.replace('*', '0')
                        elif '=' not in m and '<' not in m:
                            m = '=' + m
                    value = min_value, max_value
                else:
                    if '*' in value:
                        value = '>=' + value.replace('*', '0')
                    elif '=' not in value and '<' not in value:
                        print(value)
                        value = '=' + value

            result_dictionary[key] = value
        
        result = ""
        for r in sorted(result_dictionary):
            if isinstance(result_dictionary[r], tuple):
                for v in result_dictionary[r]:
                    result += "'" + r + v + "' "
            else:
                result += "'" + r + result_dictionary[r] + "' "
        return result.strip()


# TODO Handle non-existent values, return a dict instead of separate values
# (only parse the file once)

def read_pkgbuild(pkgname):

    string_keys = {
        'pkgname',
        'pkgver',
        'pkgrel',
        'pkgdesc',
        'url',
        'install',
        'changelog',
    }

    array_keys = {
        'arch',
        'license',
        'groups',
        'depends',
        'optdepends',
        'makedepends',
        'checkdepends',
        'provides',
        'conflicts',
        'replaces',
        'options',
        'source',
    }

    pkgbuild = dict()
 
    with open(pkgname + '/PKGBUILD') as filebuffer:
        lines = filebuffer.readlines()
        # 'with' statement closes :)

    p = None

    for l in lines:
        # If a line ends with \, it continues on the next line
        if l.endswith('\\\n'):
            p = l.rstrip('\\\n')
            continue
        else:
            if p:
                l = p + l
                p = None

            key, sep, value = l.partition('=')
            if not sep:
                continue

            key = key.strip()
            value = value.strip()

            if key in string_keys:
                pkgbuild[key] = value.rstrip('\n').strip('"\'')
            elif key in array_keys:
                # This is... inaccurate?
                if not key.startswith('(') and key.endswith(')'):
                    raise ValueError('cannot parse array line %r' % (line,))
                pkgbuild[key] = value.rstrip('\n').strip('()"')
    
    missing_keys = (string_keys | array_keys) - set(pkgbuild)
    #if missing_keys:
        # This may not be necessary. I do not know.
        #raise ValueError('missing keys: %s' % (', '.join(missing_keys)))
        #print('missing keys: %s' % (', '.join(missing_keys)))

    return pkgbuild


def create_directory(path):
    try: 
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


# TODO: Iterate over the dict? Partially?
def get_information(information):

    # Single
    repository = get_string("Enter repository", 'repository',
            information['repository'])
    if not repository:
        raise CancelledError()

    # Single
    maintainer_name = get_string("Enter your name", 'maintainer_name',
            information['maintainer_name'])
    if not maintainer_name:
        raise CancelledError()

    # Single
    maintainer_alias = get_string("Enter your alias", 'maintainer_alias',
            information['maintainer_alias'])
    if not maintainer_alias:
        raise CancelledError()

    # Single
    maintainer_email = get_string("Enter your e-mail", 'maintainer_email',
            information['maintainer_email'])
    if not maintainer_email:
        raise CancelledError()

    # Single
    _hkgname = get_string("Enter Hackage name", '_hkgname',
            information['_hkgname'])
    if not _hkgname:
        raise CancelledError()

    # Single
    pkgname = get_string("Enter package name", 'pkgname',
            'haskell-' + _hkgname)
    if not pkgname:
        raise CancelledError()

    # Read existing PKGBUILD now!
    exists = read_pkgbuild(pkgname)
    if exists:
        print("  Existing PKGBUILD found in ./" + pkgname + "/PKGBUILD:")

    # Single
    if 'pkgver' in exists:
        print("  Previous version: ", exists['pkgver'])
    print("  Checking Hackage...")
    print("  Latest version: ", scrape_version('http://hackage.haskell.org/package/' + _hkgname, 'Versions'))
    pkgver = get_string("Enter package version", 'pkgver',
            scrape_version('http://hackage.haskell.org/package/' + _hkgname, 'Versions'))
    if not pkgver:
        raise CancelledError()

    # Single
    if 'pkgrel' in exists:
        print("  Previous release: ", exists['pkgrel'])
    pkgrel = get_string("Enter package release", 'pkgrel',
            int(exists['pkgrel']) + 1 if exists else 1)
    if not pkgrel:
        raise CancelledError()

    # Single
    if 'pkgdesc' in exists:
        print("  Previous description: ", exists['pkgdesc'])
    pkgdesc = get_string("Enter package description", 'pkgdesc',
            exists['pkgdesc'])
    if not pkgdesc:
        raise CancelledError()

    # Select
    if 'arch' in exists:
        print("  Previous architecture(s): ", exists['arch'])
    print("  Architectures:\n    1) x86_64 and i686\n    2) x86_64\n    3) i686\n    4) Any")
    while True:
        choice = input("Select architecture(s): ")
        if choice:
            try:
                number = int(choice)
                if number == 1:
                    arch = "'x86_64' 'i686'"
                    break
                elif number == 2:
                    arch = "'x86_64'"
                    break
                elif number == 3:
                    arch = "'i686'"
                    break
                elif number == 4:
                    arch = "'any'"
                    break
                else:
                    print("Not in range")
            except ValueError as err:
                print("ERROR", err)
                continue
    if not arch:
        raise CancelledError()

    # Single
    #url = get_string("Enter url", 'url')

    # Single
    if 'license' in exists:
        print("  Previous license: ", exists['license'])
    print("  Checking Hackage...")
    print("  License: ", scrape_license('http://hackage.haskell.org/package/' + _hkgname, 'License'))
    license = get_string("Enter license", 'license', scrape_license('http://hackage.haskell.org/package/' + _hkgname, 'License'))
    if not license:
        raise CancelledError()

    # Single, optional
    if 'groups' in exists:
        print("  Previous group(s): ", exists['groups'])
    groups = get_string("Enter group(s) (optional)", 'groups')

    # Single
    if 'depends' in exists:
        print("  Previous dependencies): ", exists['depends'])
    print("  Checking Hackage...")
    print("  Dependencies: ", scrape_dependencies('http://hackage.haskell.org/package/' + _hkgname))
    depends = get_string("Enter dependencies", 'dependencies', scrape_dependencies('http://hackage.haskell.org/package/' + _hkgname))
    if not depends:
        raise CancelledError()

    # Single, optional
    if 'optdepends' in exists:
        print("  Previous optional dependencies): ", exists['optdepends'])
    optdepends = get_string("Enter optional dependencies (optional)", 'optdepends')

    # Single, optional
    if 'makedepends' in exists:
        print("  Previous make-dependencies): ", exists['makedepends'])
    makedepends = get_string("Enter make-dependencies (optional)", 'makedepends')

    # Single, optional
    if 'checkdepends' in exists:
        print("  Previous check-dependencies): ", exists['checkdepends'])
    checkdepends = get_string("Enter check-dependencies (optional)", 'checkdepends')

    # Single, optional
    if 'provides' in exists:
        print("  Previous provides): ", exists['provides'])
    provides = get_string("Enter provides (optional)", 'provides')

    # Single, optional
    if 'conflicts' in exists:
        print("  Previous conflicts): ", exists['conflicts'])
    conflicts = get_string("Enter conflicts (optional)", 'conflicts')

    # Single, optional
    if 'replaces' in exists:
        print("  Previous replaces): ", exists['replaces'])
    replaces = get_string("Enter replaces (optional)", 'replaces')

    # Single, optional
    if 'options' in exists:
        print("  Previous options): ", exists['options'])
    options = get_string("Enter options (optional)", 'options',
            exists['options'] if 'options' in exists else None)

    # Single
    #install = get_string("Enter install-file", 'install')

    # Single, optional
    #changelog = get_string("Enter changelog-file (optional)", 'changelog')

    # Single
    #source = get_string("Enter source", 'replaces')

    # Download package and get checksum
    filename = _hkgname + '-' + pkgver + '.tar.gz'
    url = 'http://hackage.haskell.org/packages/archive/' + _hkgname + '/' + pkgver + '/' + _hkgname + '-' + pkgver + '.tar.gz'
    with urllib.request.urlopen(url) as response, open(filename, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)
    checksum = hashfile(open(filename, 'rb'), hashlib.sha512())
    os.remove(filename)
    if not checksum:
        raise CancelledError()

    information.update(repository       = repository,
                       maintainer_name  = maintainer_name,
                       maintainer_alias = maintainer_alias,
                       maintainer_email = maintainer_email,
                       _hkgname         = _hkgname,
                       pkgname          = pkgname,
                       pkgver           = pkgver,
                       pkgrel           = pkgrel,
                       pkgdesc          = pkgdesc,
                       arch             = arch,
                       #url              = url,
                       license          = license,
                       groups           = groups,
                       depends          = depends,
                       optdepends       = optdepends,
                       makedepends      = makedepends,
                       checkdepends     = checkdepends,
                       provides         = provides,
                       conflicts        = conflicts,
                       replaces         = replaces,
                       options          = options,
                       #install          = install,
                       #changelog        = changelog,
                       #source           = source,
                       checksum         = checksum)


def write_pkgbuild(date, repository, maintainer_name, maintainer_alias,
        maintainer_email, _hkgname, pkgname, pkgver, pkgrel, pkgdesc,
        arch, license, groups, depends, optdepends, makedepends, checkdepends,
        provides, conflicts, replaces, options, checksum):
    content = PKGBUILD_TEMPLATE.format(**locals())
    fh = None
    try:
        filename = pkgname + '/PKGBUILD'
        fh = open(filename, 'w', encoding='utf8')
        fh.write(content)
    except EnvironmentError as err:
        print("\nERROR", err)
    else:
        print("\nSaved", filename)
    finally:
        if fh is not None:
            fh.close()


def write_install(date, repository, maintainer_name, maintainer_alias,
        maintainer_email, _hkgname, pkgname, pkgver, pkgrel, pkgdesc,
        arch, license, groups, depends, optdepends, makedepends, checkdepends,
        provides, conflicts, replaces, options, checksum):
    content = INSTALL_TEMPLATE.format(**locals())
    fh = None
    try:
        filename = pkgname + '/' + pkgname + '.install'
        fh = open(filename, 'w', encoding='utf8')
        fh.write(content)
    except EnvironmentError as err:
        print("ERROR", err)
    else:
        print("Saved", filename)
    finally:
        if fh is not None:
            fh.close()


# TODO Print previous value\n, scraped value\n, input [default value]:
def get_string(message, name='string', default=None,
        minimum_length=0, maximum_length=128):
    message += ': ' if default is None else ' [{0}]: '.format(default)
    while True:
        try:
            line = input(message)
            if not line:
                if default is not None:
                    return default
                if minimum_length == 0:
                    return ''
                else:
                    raise ValueError("{0} may not be empty".format(name))
            if not (minimum_length <= len(line) <= maximum_length):
                raise ValueError("{name} must have at least "
                        "{minimum_length} and at most "
                        "{maximum_length} characters".format(**locals()))
            return line
        except ValueError as err:
            print("ERROR", err)


# for P in PACKAGES:
#     print(P + ':', scrape_dependencies('http://hackage.haskell.org/package/' + P))

# pkgname = 'haskell-x11'
# exists = read_pkgbuild(pkgname)
# if exists:
#     print("  Existing PKGBUILD found in ./" + pkgname + "/PKGBUILD:")
#     print(exists)

main()
